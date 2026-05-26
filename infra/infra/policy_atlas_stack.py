# Application stack. Deploys the following resources:
# * Policy Atlas frontend (Next.js) as an ECS Fargate service
# * Policy Atlas backend (FastAPI) as an ECS Fargate service
# * Route53 A records for both services (pointing to the shared ALB in NetworkStack)
# * Security groups: frontend and backend containers
# * DB security group ingress rule so backend can reach RDS (port 5432)
# * Listener rules on the shared ALB for host-header routing
#
# Pre-requisites (deployed separately):
# * NetworkStack (provides shared ALB, HTTPS listener, security group via SSM)
# * DatabaseStack (provides /policy_atlas/db/secret_name, /policy_atlas/db/security_group_id,
#   and /policy_atlas/supabase/jwt_secret_name in SSM)
# * Secrets Manager secret at app_secrets_name containing all application API keys
from aws_cdk import (
    Stack,
    Duration,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecr as ecr,
    aws_ecr_assets as ecr_assets,
    aws_iam as iam,
    aws_elasticloadbalancingv2 as elbv2,
    aws_secretsmanager as secretsmanager,
    aws_ssm as ssm,
    aws_route53 as r53,
    aws_route53_targets as r53_targets,
    aws_cloudwatch as cloudwatch,
    aws_logs as logs,
)


class PolicyAtlasStack(Stack):
    def __init__(self, scope: Stack, id: str, pa_config: dict, env_name: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        pa_app_config = pa_config["policy_atlas_config"]
        domain_name = pa_app_config["domain_name"]
        fe_config = pa_app_config["frontend"]
        be_config = pa_app_config["backend"]

        fe_subdomain = pa_app_config.get("frontend_subdomain")
        fe_domain = f"{fe_subdomain}.{domain_name}" if fe_subdomain else domain_name
        be_domain = f"{pa_app_config['backend_subdomain']}.{domain_name}"

        vpc = ec2.Vpc.from_lookup(self, "VPC", region=pa_config['aws_region'])

        hosted_zone = r53.HostedZone.from_lookup(self, "HostedZone",
            domain_name=domain_name
        )

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

        # --- Import DB resources from DatabaseStack ---
        db_secret_name = ssm.StringParameter.value_for_string_parameter(self,
            parameter_name="/policy_atlas/db/secret_name"
        )

        db_secret = secretsmanager.Secret.from_secret_name_v2(self, "DBSecret",
            secret_name=db_secret_name
        )

        db_sg_id = ssm.StringParameter.value_for_string_parameter(self,
            parameter_name="/policy_atlas/db/security_group_id"
        )

        db_security_group = ec2.SecurityGroup.from_security_group_id(
            self, "DBSecurityGroup", security_group_id=db_sg_id,
            allow_all_outbound=False
        )

        # --- Import JWT secret from DatabaseStack ---
        jwt_secret_name = ssm.StringParameter.value_for_string_parameter(self,
            parameter_name="/policy_atlas/supabase/jwt_secret_name"
        )

        jwt_secret = secretsmanager.Secret.from_secret_name_v2(self, "JWTSecret",
            secret_name=jwt_secret_name,
        )

        # --- Application secrets (manually provisioned) ---
        fe_secret = secretsmanager.Secret.from_secret_name_v2(self, "AppSecret",
            secret_name=fe_config['secret_name']
        )

        be_secret = secretsmanager.Secret.from_secret_name_v2(self, "BackendAppSecret",
            secret_name=be_config['secret_name']
        )

        shared_log_group = logs.LogGroup(self, "PolicyAtlasLogGroup",
            log_group_name="/policy_atlas/application",
            retention=logs.RetentionDays.ONE_MONTH,
        )

        cluster = ecs.Cluster(self, "PolicyAtlasCluster", vpc=vpc,
            cluster_name="policy-atlas-cluster"
        )

        # --- Security groups ---
        # Frontend and backend containers allow inbound only from the shared ALB.

        fe_sg = ec2.SecurityGroup(self, "FrontendSG",
            vpc=vpc,
            description="Policy Atlas frontend containers",
            allow_all_outbound=True
        )
        fe_sg.add_ingress_rule(shared_alb_sg, ec2.Port.tcp(fe_config["internal_port"]),
            "Allow shared ALB to reach Next.js containers"
        )

        be_sg = ec2.SecurityGroup(self, "BackendSG",
            vpc=vpc,
            description="Policy Atlas backend containers",
            allow_all_outbound=True
        )
        be_sg.add_ingress_rule(shared_alb_sg, ec2.Port.tcp(be_config["internal_port"]),
            "Allow shared ALB to reach FastAPI containers"
        )

        # Allow backend containers to connect to RDS on port 5432.
        db_security_group.add_ingress_rule(be_sg, ec2.Port.tcp(5432),
            "Allow Policy Atlas backend containers to connect to RDS"
        )

        # Allow backend containers to reach PostgREST (via Cloud Map) on port 8000.
        postgrest_sg_id = ssm.StringParameter.value_for_string_parameter(self,
            parameter_name="/policy_atlas/postgrest/security_group_id")
        postgrest_sg = ec2.SecurityGroup.from_security_group_id(
            self, "PostgRESTSecurityGroup", security_group_id=postgrest_sg_id,
            allow_all_outbound=False,
        )
        postgrest_sg.add_ingress_rule(be_sg, ec2.Port.tcp(8000),
            "Allow backend to reach PostgREST via Cloud Map"
        )

        # --- Frontend ---

        fe_task_def = ecs.FargateTaskDefinition(self, "PolicyAtlasFrontendTaskDef",
            cpu=fe_config["cpu"],
            memory_limit_mib=fe_config["memory_limit_mib"],
            family="policy-atlas-frontend",
        )

        next_js_publishable_key = ssm.StringParameter.value_from_lookup(self, parameter_name="/policy_atlas/frontend/next_publishable_key")
        next_js_enc_key = ssm.StringParameter.value_from_lookup(self, parameter_name="/policy_atlas/frontend/next_encryption_key")
        fe_task_def.add_container("policy-atlas-frontend-container",
            image=ecs.ContainerImage.from_asset("../frontend",
                platform=ecr_assets.Platform.LINUX_AMD64,
                build_args={
                    "NEXT_PUBLIC_API_URL": f"https://{be_domain}",
                    "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY": next_js_publishable_key,
                    "NEXT_SERVER_ACTIONS_ENCRYPTION_KEY": next_js_enc_key,
                },
            ),
            cpu=fe_config["cpu"],
            memory_limit_mib=fe_config["memory_limit_mib"],
            logging=ecs.LogDrivers.aws_logs(stream_prefix="PolicyAtlasFrontend",
                                            log_group=shared_log_group),
            environment={
                "NEXT_PUBLIC_API_URL": f"https://{be_domain}",
                "NODE_ENV": "production",
            },
            secrets={
                "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY": ecs.Secret.from_secrets_manager(
                    fe_secret, field="NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY"),
                "CLERK_SECRET_KEY": ecs.Secret.from_secrets_manager(
                    fe_secret, field="CLERK_SECRET_KEY"),
                "NEXT_PUBLIC_CLERK_SIGN_IN_URL": ecs.Secret.from_secrets_manager(
                    fe_secret, field="NEXT_PUBLIC_CLERK_SIGN_IN_URL"),
                "NEXT_PUBLIC_CLERK_SIGN_UP_URL": ecs.Secret.from_secrets_manager(
                    fe_secret, field="NEXT_PUBLIC_CLERK_SIGN_UP_URL"),
                "NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL": ecs.Secret.from_secrets_manager(
                    fe_secret, field="NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL"),
            },
            port_mappings=[ecs.PortMapping(
                container_port=fe_config["internal_port"],
                protocol=ecs.Protocol.TCP
            )],
        )

        fe_secret.grant_read(fe_task_def.task_role)

        fe_service = ecs.FargateService(self, "PolicyAtlasFrontendService",
            cluster=cluster,
            task_definition=fe_task_def,
            desired_count=fe_config["desired_count"],
            min_healthy_percent=100,
            max_healthy_percent=200,
            service_name="policy-atlas-frontend-service",
            security_groups=[fe_sg],
            assign_public_ip=False,
        )

        fe_autoscale = fe_service.auto_scale_task_count(
            min_capacity=fe_config["min_capacity"],
            max_capacity=fe_config["max_capacity"]
        )
        fe_autoscale.scale_on_cpu_utilization("FECpuScaling",
            target_utilization_percent=fe_config["cpu_target_utilization_percent"])
        fe_autoscale.scale_on_memory_utilization("FEMemoryScaling",
            target_utilization_percent=fe_config["memory_target_utilization_percent"])

        fe_tg = elbv2.ApplicationTargetGroup(self, "FrontendTargetGroup",
            vpc=vpc,
            target_group_name="policy-atlas-frontend-tg",
            port=fe_config["internal_port"],
            protocol=elbv2.ApplicationProtocol.HTTP,
            health_check=elbv2.HealthCheck(
                path="/",
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                healthy_threshold_count=2,
                unhealthy_threshold_count=5,
                healthy_http_codes="200-399",
            ),
            targets=[fe_service.load_balancer_target(
                container_name="policy-atlas-frontend-container",
                container_port=fe_config["internal_port"],
                protocol=ecs.Protocol.TCP
            )]
        )

        shared_listener.add_target_groups("FrontendListenerRule",
            priority=5,
            conditions=[elbv2.ListenerCondition.host_headers([fe_domain])],
            target_groups=[fe_tg]
        )

        r53.ARecord(self, "FrontendARecord",
            zone=hosted_zone,
            record_name=fe_subdomain,  # None -> zone apex
            target=r53.RecordTarget.from_alias(r53_targets.LoadBalancerTarget(shared_alb))
        )

        # --- Backend ---

        be_task_def = ecs.FargateTaskDefinition(self, "PolicyAtlasBackendTaskDef",
            cpu=be_config["cpu"],
            memory_limit_mib=be_config["memory_limit_mib"],
            family="policy-atlas-backend",
        )

        # Derive the Cloud Map namespace name for the SUPABASE_URL.
        cloud_map_ns_name = ssm.StringParameter.value_for_string_parameter(self,
            parameter_name="/policy_atlas/cloudmap/namespace_name")

        be_task_def.add_container("policy-atlas-backend-container",
            image=ecs.ContainerImage.from_asset("../backend",
                platform=ecr_assets.Platform.LINUX_AMD64,
                build_args={
                    "BACKEND_CORS_ORIGINS": f'["https://{fe_domain}"]',
                },
            ),
            cpu=be_config["cpu"],
            memory_limit_mib=be_config["memory_limit_mib"],
            logging=ecs.LogDrivers.aws_logs(stream_prefix="PolicyAtlasBackend",
                                            log_group=shared_log_group),
            environment={
                "BACKEND_CORS_ORIGINS": f'["https://{fe_domain}"]',
                "LOG_LEVEL": "INFO",
                "SUPABASE_URL": f"http://postgrest.{cloud_map_ns_name}:8000",
            },
            secrets={
                "SUPABASE_KEY": ecs.Secret.from_secrets_manager(jwt_secret, field="service_role_key"),
                # Application API keys.
                "OPENAI_API_KEY": ecs.Secret.from_secrets_manager(be_secret, field="OPENAI_API_KEY"),
                "CLERK_SECRET_KEY": ecs.Secret.from_secrets_manager(be_secret, field="CLERK_SECRET_KEY"),
                "CLERK_PUBLISHABLE_KEY": ecs.Secret.from_secrets_manager(be_secret, field="CLERK_PUBLISHABLE_KEY"),
                "CLERK_JWT_ISSUER": ecs.Secret.from_secrets_manager(be_secret, field="CLERK_JWT_ISSUER"),
                "OPENALEX_EMAIL": ecs.Secret.from_secrets_manager(be_secret, field="OPENALEX_EMAIL"),
                "OPENALEX_API_KEY": ecs.Secret.from_secrets_manager(be_secret, field="OPENALEX_API_KEY"),
                "OVERTON_API_KEY": ecs.Secret.from_secrets_manager(be_secret, field="OVERTON_API_KEY"),
                "LANGFUSE_SECRET_KEY": ecs.Secret.from_secrets_manager(be_secret, field="LANGFUSE_SECRET_KEY"),
                "LANGFUSE_PUBLIC_KEY": ecs.Secret.from_secrets_manager(be_secret, field="LANGFUSE_PUBLIC_KEY"),
                "LANGFUSE_HOST": ecs.Secret.from_secrets_manager(be_secret, field="LANGFUSE_HOST"),
                "LANGFUSE_USER_ID": ecs.Secret.from_secrets_manager(be_secret, field="LANGFUSE_USER_ID"),
                "DEMO_ORG_ID": ecs.Secret.from_secrets_manager(be_secret, field="DEMO_ORG_ID"),
            },
            port_mappings=[ecs.PortMapping(
                container_port=be_config["internal_port"],
                protocol=ecs.Protocol.TCP
            )],
        )

        # LH 08/05/2026: As per PR 172, removed this - backend probably doesn't need to read front-end secret values.
        # fe_secret.grant_read(be_task_def.task_role)
        db_secret.grant_read(be_task_def.task_role)
        jwt_secret.grant_read(be_task_def.task_role)

        be_service = ecs.FargateService(self, "PolicyAtlasBackendService",
            cluster=cluster,
            task_definition=be_task_def,
            desired_count=be_config["desired_count"],
            min_healthy_percent=100,
            max_healthy_percent=200,
            service_name="policy-atlas-backend-service",
            security_groups=[be_sg],
            assign_public_ip=False,
        )

        be_autoscale = be_service.auto_scale_task_count(
            min_capacity=be_config["min_capacity"],
            max_capacity=be_config["max_capacity"]
        )
        be_autoscale.scale_on_cpu_utilization("BECpuScaling",
            target_utilization_percent=be_config["cpu_target_utilization_percent"])
        be_autoscale.scale_on_memory_utilization("BEMemoryScaling",
            target_utilization_percent=be_config["memory_target_utilization_percent"])

        # Backend listener rule + DNS
        backend_tg = elbv2.ApplicationTargetGroup(self, "BackendTargetGroup",
            vpc=vpc,
            target_group_name="policy-atlas-backend-tg",
            port=be_config["internal_port"],
            protocol=elbv2.ApplicationProtocol.HTTP,
            health_check=elbv2.HealthCheck(
                path="/",
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                healthy_threshold_count=2,
                unhealthy_threshold_count=5,
                healthy_http_codes="200-399",
            ),
            targets=[be_service.load_balancer_target(
                container_name="policy-atlas-backend-container",
                container_port=be_config["internal_port"],
                protocol=ecs.Protocol.TCP
            )]
        )

        shared_listener.add_target_groups("BackendListenerRule",
            priority=10,
            conditions=[elbv2.ListenerCondition.host_headers([be_domain])],
            target_groups=[backend_tg]
        )

        r53.ARecord(self, "BackendARecord",
            zone=hosted_zone,
            record_name=pa_app_config["backend_subdomain"],
            target=r53.RecordTarget.from_alias(r53_targets.LoadBalancerTarget(shared_alb))
        )
