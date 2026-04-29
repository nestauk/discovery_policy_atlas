# Core database stack. Deploys the following resources:
# * RDS Aurora Provisioned Cluster
# * Supabase Studio, pointing to postgres-meta (supabase/studio)
# * Postgres Meta, pointing to the RDS cluster (supabase/postgres-meta)
# * PostgREST + nginx sidecar for Supabase SDK access (via Cloud Map)
# * JWT secret generation for PostgREST authentication
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
    aws_ecr_assets as ecr_assets,
    aws_elasticloadbalancingv2 as elbv2,
    aws_route53 as r53,
    aws_route53_targets as r53_targets,
    aws_lambda as _lambda,
    aws_servicediscovery as servicediscovery,
    triggers,
    aws_logs as logs,
)

from shutil import copytree, ignore_patterns

import json

class DatabaseStack(Stack):
    def __init__(self, scope: Stack, id: str,
                 db_config: dict, env_name: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # Get the VPC by ID.
        vpc_id = ssm.StringParameter.value_for_string_parameter(self, parameter_name="/policy_atlas/vpc_id")

        vpc = ec2.Vpc.from_lookup(self, "VPC", region=db_config['aws_region'])

        # --- Import shared ALB from NetworkStack ---
        shared_alb_arn = ssm.StringParameter.value_for_string_parameter(self,
            parameter_name="/policy_atlas/shared_alb/arn")
        shared_alb_sg_id = ssm.StringParameter.value_for_string_parameter(self,
            parameter_name="/policy_atlas/shared_alb/security_group_id")
        shared_alb_dns = ssm.StringParameter.value_for_string_parameter(self,
            parameter_name="/policy_atlas/shared_alb/dns_name")
        shared_alb_zone_id = ssm.StringParameter.value_for_string_parameter(self,
            parameter_name="/policy_atlas/shared_alb/canonical_hosted_zone_id")
        shared_listener_arn = ssm.StringParameter.value_for_string_parameter(self,
            parameter_name="/policy_atlas/shared_alb/https_listener_arn")

        shared_alb_sg = ec2.SecurityGroup.from_security_group_id(
            self, "SharedALBSG", security_group_id=shared_alb_sg_id,
            allow_all_outbound=False,
        )

        shared_alb = elbv2.ApplicationLoadBalancer.from_application_load_balancer_attributes(
            self, "SharedALB",
            load_balancer_arn=shared_alb_arn,
            security_group_id=shared_alb_sg_id,
            load_balancer_dns_name=shared_alb_dns,
            load_balancer_canonical_hosted_zone_id=shared_alb_zone_id,
        )

        shared_listener = elbv2.ApplicationListener.from_application_listener_attributes(
            self, "SharedHTTPSListener",
            listener_arn=shared_listener_arn,
            security_group=shared_alb_sg,
        )

        cloud_map_namespace_id = ssm.StringParameter.value_for_string_parameter(self,
            parameter_name="/policy_atlas/cloudmap/namespace_id")
        cloud_map_namespace_arn = ssm.StringParameter.value_for_string_parameter(self,
            parameter_name="/policy_atlas/cloudmap/namespace_arn")
        cloud_map_namespace_name = ssm.StringParameter.value_for_string_parameter(self,
            parameter_name="/policy_atlas/cloudmap/namespace_name")

        cloud_map_namespace = servicediscovery.PrivateDnsNamespace.from_private_dns_namespace_attributes(
            self, "CloudMapNamespace",
            namespace_id=cloud_map_namespace_id,
            namespace_arn=cloud_map_namespace_arn,
            namespace_name=cloud_map_namespace_name,
        )

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

        jwt_secret = secretsmanager.Secret(self, "SupabaseJWTSecret",
            secret_name="policy_atlas/supabase_jwt",
            description="PostgREST JWT secret, anon/service_role keys, and authenticator password",
        )

        generate_jwt_function = _lambda.Function(self, "GenerateSupabaseJWTFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="generate_supabase_jwt.handler",
            code=_lambda.Code.from_asset("infra/deploy_functions/generate_supabase_jwt"),
            environment={
                "JWT_SECRET_NAME": jwt_secret.secret_name,
                "DB_SECRET_NAME": cluster.secret.secret_name,
            },
            timeout=Duration.seconds(30),
            memory_size=128,
        )

        jwt_secret.grant_read(generate_jwt_function)
        jwt_secret.grant_write(generate_jwt_function)
        cluster.secret.grant_read(generate_jwt_function)

        # --- Load secret Lambda (writes db_connection_string into the RDS secret) ---
        load_secret_function = _lambda.Function(self, "LoadSecretFunction",
            runtime=_lambda.Runtime.PYTHON_3_9,
            handler="load_secret.load_secret",
            code=_lambda.Code.from_asset("infra/deploy_functions/load_secret"),
            environment={
                "SECRET_NAME": cluster.secret.secret_name
            }
        )

        cluster.secret.grant_read(load_secret_function)
        cluster.secret.grant_write(load_secret_function)

        # --- Studio + postgres-meta ---

        studio_security_group = ec2.SecurityGroup(self, "StudioSecurityGroup",
            vpc=vpc,
            description="Security group for Supabase Studio",
            allow_all_outbound=True,
        )

        # Allow Studio containers to reach RDS.
        db_security_group.add_ingress_rule(
            peer=studio_security_group,
            connection=ec2.Port.tcp(5432),
            description="Allow Supabase Studio access to RDS cluster"
        )

        # Allow shared ALB to reach Studio containers.
        studio_security_group.add_ingress_rule(
            peer=shared_alb_sg,
            connection=ec2.Port.tcp(3000),
            description="Allow shared ALB to reach Studio containers"
        )

        studio_cluster = ecs.Cluster(self, "StudioCluster", vpc=vpc,
            cluster_name="policy-atlas-studio-cluster",
            enable_fargate_capacity_providers=True
        )

        task_definition = ecs.FargateTaskDefinition(self, "StudioTaskDef",
            cpu=db_config["studio-meta"]["cpu"],
            memory_limit_mib=db_config["studio-meta"]["memory_limit_mib"]
        )

        # --- Triggers: ordering ---
        # LoadSecretTrigger and GenerateJWTTrigger both run after the cluster.
        # RunMigrationsTrigger runs after GenerateJWT (needs authenticator password).
        # All triggers complete before task definitions start.

        triggers.Trigger(self, "LoadSecretTrigger",
            handler=load_secret_function,
            execute_after=[cluster],
            execute_before=[task_definition]
        )

        generate_jwt_trigger = triggers.Trigger(self, "GenerateJWTTrigger",
            handler=generate_jwt_function,
            execute_after=[cluster],
            # execute_before updated below after postgrest_task_definition is created
        )

        # --- Migration Lambda ---
        migration_sg = ec2.SecurityGroup(self, "MigrationLambdaSG",
            vpc=vpc,
            description="Security group for DB migration Lambda",
            allow_all_outbound=True
        )

        db_security_group.add_ingress_rule(
            peer=migration_sg,
            connection=ec2.Port.tcp(5432),
            description="Allow migration Lambda to connect to RDS"
        )

        # Prebuild step: copy /backend/supabase/migrations to infra/deploy_functions/run_migrations/migrations
        copytree("../backend/supabase/migrations", "infra/deploy_functions/run_migrations/migrations",
            dirs_exist_ok=True, ignore=ignore_patterns("__pycache__"))

        migration_function = _lambda.Function(self, "RunMigrationsFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="run_migrations.handler",
            code=_lambda.Code.from_asset(
                "infra/deploy_functions/run_migrations"
            ),
            environment={
                "SECRET_NAME": cluster.secret.secret_name,
                "JWT_SECRET_NAME": jwt_secret.secret_name,
            },
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[migration_sg],
            timeout=Duration.minutes(5),
            memory_size=256,
        )

        cluster.secret.grant_read(migration_function)
        jwt_secret.grant_read(migration_function)

        migration_trigger = triggers.Trigger(self, "RunMigrationsTrigger",
            handler=migration_function,
            execute_after=[cluster, generate_jwt_trigger],
            execute_before=[task_definition]
        )


        log_group = logs.LogGroup(self, "StudioLogGroup",
            log_group_name="/policy_atlas/studio",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY)

        meta_log_group = logs.LogGroup(self, "PostgresMetaLogGroup",
            log_group_name="/policy_atlas/postgres_meta",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY)

        task_definition.add_container("SupabaseStudioContainer",
            image=ecs.ContainerImage.from_registry(f"public.ecr.aws/supabase/studio:{db_config['studio_tag']}"),
            port_mappings=[ecs.PortMapping(container_port=3000)],
            environment={
                "STUDIO_PG_META_URL": "http://localhost:8080",
                "DEFAULT_ORGANIZATION_NAME": "Policy Atlas",
                "DEFAULT_PROJECT_NAME": "Policy Atlas",
                "NEXT_PUBLIC_ENABLE_LOGS": "false",
            },
            secrets={
                "POSTGRES_PASSWORD": ecs.Secret.from_secrets_manager(cluster.secret, field="password")
            },
            logging=ecs.LogDrivers.aws_logs(stream_prefix="SupabaseStudio", log_group=log_group),
        )

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
            logging=ecs.LogDrivers.aws_logs(stream_prefix="PostgresMeta", log_group=meta_log_group)
        )

        studio_service = ecs.FargateService(self, "StudioService",
            cluster=studio_cluster,
            task_definition=task_definition,
            desired_count=1,
            security_groups=[studio_security_group],
            assign_public_ip=False
        )


        hosted_zone = r53.HostedZone.from_lookup(self, "HostedZone",
            domain_name=db_config["base_domain_name"]
        )

        studio_fqdn = f"{db_config['studio_subdomain']}.{db_config['base_domain_name']}"

        whitelist_ips = db_config.get("studio_whitelist_ips", [])
        studio_conditions = [elbv2.ListenerCondition.host_headers([studio_fqdn])]
        if whitelist_ips:
            studio_conditions.append(elbv2.ListenerCondition.source_ips(whitelist_ips))

        studio_tg = elbv2.ApplicationTargetGroup(self, "StudioTargetGroup",
            vpc=vpc,
            protocol=elbv2.ApplicationProtocol.HTTP,
            port=3000,
            target_type=elbv2.TargetType.IP,
            health_check=elbv2.HealthCheck(
                path="/",
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                healthy_threshold_count=2,
                unhealthy_threshold_count=5,
                healthy_http_codes="200-399"
            ),
            targets=[studio_service.load_balancer_target(
                container_name="SupabaseStudioContainer",
                container_port=3000,
                protocol=ecs.Protocol.TCP
            )],
        )

        shared_listener.add_target_groups("StudioListenerRule",
            priority=15,
            conditions=studio_conditions,
            target_groups=[studio_tg]
        )

        r53.ARecord(self, "StudioARecord",
            zone=hosted_zone,
            record_name=db_config["studio_subdomain"],
            target=r53.RecordTarget.from_alias(r53_targets.LoadBalancerTarget(shared_alb))
        )

        # --- PostgREST + nginx sidecar ---

        postgrest_log_group = logs.LogGroup(self, "PostgRESTLogGroup",
            log_group_name="/policy_atlas/postgrest",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY)

        nginx_log_group = logs.LogGroup(self, "PostgRESTNginxLogGroup",
            log_group_name="/policy_atlas/postgrest_nginx",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY)

        postgrest_task_definition = ecs.FargateTaskDefinition(self, "PostgRESTTaskDef",
            cpu=db_config["postgrest-proxy"]["cpu"],
            memory_limit_mib=db_config["postgrest-proxy"]["memory_limit_mib"],
        )

        postgrest_task_definition.add_container("PostgRESTContainer",
            image=ecs.ContainerImage.from_registry(
                f"postgrest/postgrest:{db_config['postgrest_tag']}"),
            port_mappings=[ecs.PortMapping(container_port=3000)],
            environment={
                "PGRST_DB_SCHEMAS": "public",
                "PGRST_DB_ANON_ROLE": "anon",
                "PGRST_DB_USE_LEGACY_GUCS": "false",
                "PGRST_SERVER_PORT": "3000",
            },
            secrets={
                "PGRST_DB_URI": ecs.Secret.from_secrets_manager(jwt_secret, field="postgrest_db_uri"),
                "PGRST_JWT_SECRET": ecs.Secret.from_secrets_manager(jwt_secret, field="jwt_secret"),
            },
            logging=ecs.LogDrivers.aws_logs(stream_prefix="PostgREST", log_group=postgrest_log_group),
        )

        postgrest_task_definition.add_container("PostgRESTNginxContainer",
            image=ecs.ContainerImage.from_asset("assets/postgrest-proxy",
                platform=ecr_assets.Platform.LINUX_AMD64,
            ),
            port_mappings=[ecs.PortMapping(container_port=8000)],
            essential=True,
            logging=ecs.LogDrivers.aws_logs(stream_prefix="PostgRESTNginx", log_group=nginx_log_group),
        )

        jwt_secret.grant_read(postgrest_task_definition.task_role)

        postgrest_sg = ec2.SecurityGroup(self, "PostgRESTSecurityGroup",
            vpc=vpc,
            description="Security group for PostgREST + nginx containers",
            allow_all_outbound=True,
        )

        db_security_group.add_ingress_rule(
            peer=postgrest_sg,
            connection=ec2.Port.tcp(5432),
            description="Allow PostgREST to connect to RDS"
        )

        postgrest_service = ecs.FargateService(self, "PostgRESTService",
            cluster=studio_cluster,
            task_definition=postgrest_task_definition,
            desired_count=1,
            security_groups=[postgrest_sg],
            assign_public_ip=False,
            cloud_map_options=ecs.CloudMapOptions(
                cloud_map_namespace=cloud_map_namespace,
                name="postgrest",
                dns_record_type=servicediscovery.DnsRecordType.A,
                container_port=8000,
            ),
        )

        # Now set execute_before on the JWT trigger to include both task definitions.
        generate_jwt_trigger.node.add_dependency(cluster)
        task_definition.node.add_dependency(generate_jwt_trigger)
        postgrest_task_definition.node.add_dependency(generate_jwt_trigger)
        postgrest_task_definition.node.add_dependency(migration_trigger)

        # --- SSM parameter exports ---

        ssm.StringParameter(self, "DBSecurityGroupParameter",
            parameter_name="/policy_atlas/db/security_group_id",
            string_value=db_security_group.security_group_id
        )

        ssm.StringParameter(self, "DBSecretNameParameter",
            parameter_name="/policy_atlas/db/secret_name",
            string_value=cluster.secret.secret_name
        )

        ssm.StringParameter(self, "JWTSecretNameParameter",
            parameter_name="/policy_atlas/supabase/jwt_secret_name",
            string_value=jwt_secret.secret_name,
        )

        ssm.StringParameter(self, "PostgRESTSecurityGroupParameter",
            parameter_name="/policy_atlas/postgrest/security_group_id",
            string_value=postgrest_sg.security_group_id,
        )
