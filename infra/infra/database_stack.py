# Core database stack. Deploys the following resources:
# * RDS Aurora Provisioned Cluster
# * Supabase Studio, pointing to postgres-meta (supabase/studio)
# * Postgres Meta, pointing to the RDS cluster (supabase/postgres-meta)
# This also takes the following extra steps:
# * Creates a Secrets Manager secret to hold the database credentials
# * Stores the database security group ID in SSM Parameter Store for later use
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    BundlingOptions,
    aws_rds as rds,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_secretsmanager as secretsmanager,
    aws_ssm as ssm,
    aws_ecs as ecs,
    aws_elasticloadbalancingv2 as elbv2,
    aws_route53 as r53,
    aws_route53_targets as r53_targets,
    aws_certificatemanager as acm,
    aws_lambda as _lambda,
    triggers,
)

import json

class DatabaseStack(Stack):
    def __init__(self, scope: Stack, id: str,
                 db_config: dict, env_name: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # Get the VPC by ID.
        vpc_id = ssm.StringParameter.value_from_lookup(self, parameter_name="/policy_atlas/vpc_id")

        vpc = ec2.Vpc.from_lookup(self, "VPC", vpc_id=vpc_id)

        # Create a security group for the RDS cluster.
        db_security_group = ec2.SecurityGroup(self, "DBSecurityGroup",
            vpc=vpc,
            description="Security group for PA DB cluster",
            allow_all_outbound=True
        )

        if db_config["readers"] == 0:
            readers = None
        else:
            readers = []
            for _ in range(db_config["readers"]):
                readers.append(
                    rds.ClusterInstance.provisioned(
                        "PolicyAtlasDBReaderInstance" + str(_),
                        instance_type=ec2.InstanceType(db_config["reader_instance_size"]),
                        instance_identifier=f"policy-atlas-db-reader-{_}",
                    )
                )

        writer = rds.ClusterInstance.provisioned(
            "PolicyAtlasDBWriterInstance",
            instance_type=ec2.InstanceType(db_config["writer_instance_size"]),
            instance_identifier=f"policy-atlas-db-writer",
        )

        # Create the RDS Aurora cluster.
        cluster = rds.DatabaseCluster(self, "PolicyAtlasDBCluster",
            engine=rds.DatabaseClusterEngine.aurora_postgres(
                version=rds.AuroraPostgresEngineVersion.VER_17_7),
            writer=writer,
            readers=readers,
            default_database_name="policy_atlas_db",
            credentials=rds.Credentials.from_generated_secret("dbadmin"),
            removal_policy=RemovalPolicy.SNAPSHOT,
            deletion_protection=False,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            cluster_identifier="policy-atlas-db-cluster",
            security_groups=[db_security_group]
        )

        # Before we proceed, prepare a Lambda function for use within this deployment.
        # We will be using it to upload a connection string back into the database secret,
        # so that the Studio - which expects a database connection string and not a password -
        # can connect, without exposing the secret in CFN logs.
        # This function can be held inline, as it's quite simple.
        load_secret_function = _lambda.Function(self, "LoadSecretFunction",
            runtime=_lambda.Runtime.PYTHON_3_9,
            handler="load_secret.load_secret",
            code=_lambda.Code.from_asset("infra/deploy_functions/load_secret"),
            environment={
                "SECRET_NAME": cluster.secret.secret_name
            }
        )

        # Grant the Lambda permissions to read and write the secret.
        cluster.secret.grant_read(load_secret_function)
        cluster.secret.grant_write(load_secret_function)



        # Create a security group for Supabase Studio.
        studio_security_group = ec2.SecurityGroup(self, "StudioSecurityGroup",
            vpc=vpc,
            description="Security group for Supabase Studio",
            allow_all_outbound=True
        )

        whitelist_ips = db_config.get("studio_whitelist_ips", [])
        if not whitelist_ips:
            # Do nothing - open to world.
            pass
        else:
            for ip in whitelist_ips:
                studio_security_group.add_ingress_rule(
                    peer=ec2.Peer.ipv4(ip),
                    connection=ec2.Port.tcp(443),
                    description=f"Allow Supabase Studio access from {ip}"
                )


        # Allow inbound access to the RDS cluster from the Supabase Studio security group.
        db_security_group.add_ingress_rule(
            peer=studio_security_group,
            connection=ec2.Port.tcp(5432),
            description="Allow Supabase Studio access to RDS cluster"
        )

        # Set up an ECS cluster, via Fargate, to run the Supabase Studio container.
        studio_cluster = ecs.Cluster(self, "StudioCluster", vpc=vpc,
            cluster_name=f"policy-atlas-studio-cluster",
            enable_fargate_capacity_providers=True
        )

        # Create a task definition for both Supabase Studio and PG-Meta.
        task_definition = ecs.FargateTaskDefinition(self, "StudioTaskDef",
            cpu=db_config["studio-meta"]["cpu"],
            memory_limit_mib=db_config["studio-meta"]["memory_limit_mib"]
        )

        # Invoke the secret above using a trigger so it runs during deployment.
        triggers.Trigger(self, "LoadSecretTrigger",
                         handler=load_secret_function,
                         execute_after=[cluster],
                         execute_before=[task_definition]
        )

        # Create a security group for the migration Lambda.
        # Needs outbound access to reach RDS and Secrets Manager (via VPC endpoint or NAT).
        migration_sg = ec2.SecurityGroup(self, "MigrationLambdaSG",
            vpc=vpc,
            description="Security group for DB migration Lambda",
            allow_all_outbound=True
        )

        # Allow the migration Lambda to connect to RDS on port 5432.
        db_security_group.add_ingress_rule(
            peer=migration_sg,
            connection=ec2.Port.tcp(5432),
            description="Allow migration Lambda to connect to RDS"
        )

        # Lambda that applies all SQL migrations against the freshly provisioned RDS cluster.
        # Runs on every deploy; all migrations use IF NOT EXISTS / IF EXISTS so re-runs are safe.
        # Dependencies: pg8000 (pure-Python Postgres driver), sqlparse (splits multi-statement
        # SQL files correctly, including $$-quoted PL/pgSQL function bodies).
        migration_function = _lambda.Function(self, "RunMigrationsFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="run_migrations.handler",
            code=_lambda.Code.from_asset(
                "infra/deploy_functions/run_migrations"
            ),
            environment={"SECRET_NAME": cluster.secret.secret_name},
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[migration_sg],
            timeout=Duration.minutes(5),
            memory_size=256,
        )

        cluster.secret.grant_read(migration_function)

        # Trigger migrations after the cluster is ready, before the Studio comes up.
        # Runs in parallel with LoadSecretTrigger (no dependency between them).
        triggers.Trigger(self, "RunMigrationsTrigger",
            handler=migration_function,
            execute_after=[cluster],
            execute_before=[task_definition]
        )

        task_definition.add_container("SupabaseStudioContainer",
            image=ecs.ContainerImage.from_registry(f"public.ecr.aws/supabase/studio:{db_config['studio_tag']}"),
            port_mappings=[ecs.PortMapping(container_port=3000)],
            environment={
                # Studio communicates with postgres-meta (co-located in the same task) for all DB introspection.
                "STUDIO_PG_META_URL": "http://localhost:8080",
                "DEFAULT_ORGANIZATION_NAME": "Policy Atlas",
                "DEFAULT_PROJECT_NAME": "Policy Atlas",
                "NEXT_PUBLIC_ENABLE_LOGS": "false",
            },
            secrets={
                "POSTGRES_PASSWORD": ecs.Secret.from_secrets_manager(cluster.secret, field="password")
            },
            logging=ecs.LogDrivers.aws_logs(stream_prefix="SupabaseStudio"),
        )

        # postgres-meta provides the REST API that Studio uses for schema introspection.
        # Listens on port 8080 (default). Uses individual PG_META_DB_* vars (not DATABASE_URL).
        task_definition.add_container("PostgresMetaContainer",
            image=ecs.ContainerImage.from_registry(f"public.ecr.aws/supabase/postgres-meta:{db_config['postgres_meta_tag']}"),
            port_mappings=[ecs.PortMapping(container_port=8080)],
            environment={
                "PG_META_PORT": "8080",
                "PG_META_DB_NAME": "policy_atlas_db",
                "PG_META_DB_SSL_MODE": "require",
            },
            secrets={
                "PG_META_DB_HOST": ecs.Secret.from_secrets_manager(cluster.secret, field="host"),
                "PG_META_DB_PORT": ecs.Secret.from_secrets_manager(cluster.secret, field="port"),
                "PG_META_DB_USER": ecs.Secret.from_secrets_manager(cluster.secret, field="username"),
                "PG_META_DB_PASSWORD": ecs.Secret.from_secrets_manager(cluster.secret, field="password"),
            },
            logging=ecs.LogDrivers.aws_logs(stream_prefix="PostgresMeta")
        )



        # Create a Fargate service to run the task definition.
        studio_service = ecs.FargateService(self, "StudioService",
            cluster=studio_cluster,
            task_definition=task_definition,
            desired_count=1,
            security_groups=[studio_security_group],
            assign_public_ip=False
        )

        # Front it via ALB, so it can be accessed.
        # Only Studio should be exposed.
        alb = elbv2.ApplicationLoadBalancer(self, "StudioALB",
            vpc=vpc,
            internet_facing=True,
            security_group=studio_security_group,
            load_balancer_name=f"policy-atlas-studio-alb"
        )

        listener = alb.add_listener("StudioListener", port=443, protocol=elbv2.ApplicationProtocol.HTTPS)
        
        # Add a holding action for default routing.
        # Users should never see this unless they're trying to bypass
        # DNS, which they won't.
        listener.add_action("DefaultAction",
            action=elbv2.ListenerAction.fixed_response(
                status_code=404,
                content_type="text/plain",
                message_body="Not Found"
        ))

        listener.add_targets("StudioTarget",
            port=3000,
            protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[studio_service.load_balancer_target(
                container_name="SupabaseStudioContainer",
                container_port=3000,
                protocol=ecs.Protocol.TCP
            )],
            health_check=elbv2.HealthCheck(
                path="/",
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                healthy_threshold_count=2,
                unhealthy_threshold_count=5,
                healthy_http_codes="200-399"
            ),
            conditions=[elbv2.ListenerCondition.host_headers(
                [f"{db_config['studio_subdomain']}.{db_config['base_domain_name']}"])],
            priority=20
        )

        # Import R53 hosted zone.
        hosted_zone = r53.HostedZone.from_lookup(self, "HostedZone",
            domain_name=db_config["base_domain_name"]
        )

        # Import R53 local hosted zone.
        local_hosted_zone = r53.HostedZone.from_lookup(self, "LocalHostedZone",
            domain_name=db_config["local_domain_name"],
            private_zone=True,
            vpc_id=vpc.vpc_id                                
        )

        # Add A record - for studio access.
        r53.ARecord(self, "StudioARecord",
            zone=hosted_zone,
            record_name=db_config["studio_subdomain"],
            target=r53.RecordTarget.from_alias(r53_targets.LoadBalancerTarget(alb))
        )

        local_db_record = "db." + db_config["local_domain_name"]

        # Add internal A record - for easy database access.
        r53.CnameRecord(self, "DatabaseLocalEndpoint",
                    zone=local_hosted_zone,
                    record_name=local_db_record,
                    domain_name=cluster.cluster_endpoint.hostname
        )

        # Store the DNS name for the DB endpoint in SSM
        ssm.StringParameter(self, "DBEndpointParameter",
            parameter_name="/policy_atlas/db/endpoint",
            string_value=local_db_record
        )

        # Store the security group for the database in SSM
        ssm.StringParameter(self, "DBSecurityGroupParameter",
            parameter_name="/policy_atlas/db/security_group_id",
            string_value=db_security_group.security_group_id
        )

        # Store the DB secret ARN in SSM so PolicyAtlasStack can import it.
        ssm.StringParameter(self, "DBSecretNameParameter",
            parameter_name="/policy_atlas/db/secret_name",
            string_value=cluster.secret.secret_name
        )

        # Store the ALB ID in SSM for application connection.
        ssm.StringParameter(self, "ALBIdParameter",
            parameter_name="/policy_atlas/studio/alb_id",
            string_value=alb.load_balancer_arn
        )

        # Request a certificate for the ALB.
        certificate = acm.Certificate(self, "StudioCertificate",
            domain_name=f"{db_config['studio_subdomain']}.{db_config['base_domain_name']}",
            validation=acm.CertificateValidation.from_dns(hosted_zone)
        )

        # And store the certificate ARN in SSM for later use.
        ssm.StringParameter(self, "StudioCertificateArnParameter",
            parameter_name="/policy_atlas/studio/certificate_arn",
            string_value=certificate.certificate_arn
        )

        # Update the ALB listener to use the certificate.
        listener.add_certificates("StudioListenerCertificate", certificates=[certificate])






