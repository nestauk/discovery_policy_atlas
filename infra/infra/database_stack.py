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
                 db_config: dict, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # Get the VPC by ID.
        vpc = ec2.Vpc.from_lookup(self, "VPC", vpc_id=db_config["vpc_id"])

        # Create a security group for the RDS cluster.
        db_security_group = ec2.SecurityGroup(self, "DBSecurityGroup",
            vpc=vpc,
            description="Security group for PA DB cluster",
            allow_all_outbound=True
        )

        # Create the RDS Aurora cluster.
        cluster = rds.DatabaseCluster(self, "PolicyAtlasDBCluster",
            engine=rds.DatabaseClusterEngine.aurora_postgres(
                version=rds.AuroraPostgresEngineVersion.VER_14_6),
            instance_props=rds.InstanceProps(
                instance_type=ec2.InstanceType(db_config["instance_size"]),
                vpc=vpc,
                security_groups=[db_security_group],
                vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_NAT)
            ),
            instances=db_config["cluster_instances"],
            default_database_name="policy_atlas_db",
            credentials=rds.Credentials.from_generated_secret("dbadmin"),
            removal_policy=RemovalPolicy.SNAPSHOT,
            deletion_protection=False,
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

        # Allow inbound access to the RDS cluster from the Supabase Studio security group.
        db_security_group.add_ingress_rule(
            peer=studio_security_group,
            connection=ec2.Port.tcp(5432),
            description="Allow Supabase Studio access to RDS cluster"
        )

        # Store the RDS cluster's security group ID in SSM Parameter Store.
        ssm.StringParameter(self, "DBSecurityGroupIdParameter",
            parameter_name="/policy_atlas/db/security_group_id",
            string_value=db_security_group.security_group_id
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

        task_definition.add_container("SupabaseStudioContainer",
            image=ecs.ContainerImage.from_registry(f"public.ecr.aws/supabase/studio:{db_config['studio_tag']}"),
            port_mappings=[ecs.PortMapping(container_port=3000)],
            environment={
                "DB_HOST": cluster.cluster_endpoint.hostname,
                "DB_PORT": str(cluster.cluster_endpoint.port),
                "DB_NAME": "policy_atlas_db",
                "DB_USER": "dbadmin",
            },
            secrets={
                    "DB_PASSWORD": ecs.Secret.from_secrets_manager(cluster.secret, field="password")
            },
            logging=ecs.LogDrivers.aws_logs(stream_prefix="SupabaseStudio")
        ) 

        # This one only takes in a fully populated URL.
        # We give it one directly after synthesizing it so we don't expose secret data in logs.
        task_definition.add_container("PostgresMetaContainer",
            image=ecs.ContainerImage.from_registry(f"public.ecr.aws/supabase/postgres-meta:{db_config['postgres_meta_tag']}"),
            port_mappings=[ecs.PortMapping(container_port=3001)],
            secrets={
                "DATABASE_URL": ecs.Secret.from_secrets_manager(cluster.secret, field="db_connection_string")
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
        listener.add_targets("StudioTarget",
            port=3000,
            protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[studio_service.load_balancer_target(
                container_name="SupabaseStudioContainer",
                container_port=3000,
                protocol=ecs.Protocol.TCP
            )]
        )

        # Import R53 hosted zone.
        hosted_zone = r53.HostedZone.from_lookup(self, "HostedZone",
            domain_name=db_config["base_domain_name"]
        )

        # Add A record - for studio access.
        r53.ARecord(self, "StudioARecord",
            zone=hosted_zone,
            record_name=db_config["studio_subdomain"],
            target=r53.RecordTarget.from_alias(r53_targets.LoadBalancerTarget(alb))
        )

        # Request a certificate for the ALB.
        certificate = acm.Certificate(self, "StudioCertificate",
            domain_name=f"{db_config['studio_subdomain']}.{db_config['base_domain_name']}",
            validation=acm.CertificateValidation.from_dns(hosted_zone)
        )

        # Update the ALB listener to use the certificate.
        listener.add_certificates("StudioListenerCertificate", certificates=[certificate])






