# Application stack. Deploys the following resources:
# * Policy Atlas frontend (Next.js) as an ECS Fargate service
# * Policy Atlas backend (FastAPI) as an ECS Fargate service
# * Internet-facing ALB per service (HTTPS:443, HTTP→HTTPS redirect)
# * ACM certificates + Route53 A records for both services
# * Security groups: frontend and backend ALBs + containers
# * DB security group ingress rule so backend can reach RDS (port 5432)
#
# Pre-requisites (deployed separately):
# * DatabaseStack (provides /policy_atlas/db/secret_arn and /policy_atlas/db/security_group_id in SSM)
# * Secrets Manager secret at app_secrets_name containing all application API keys
# * ECR repository containing frontend and backend images (ecr_repository_name CDK context)
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
    aws_certificatemanager as acm,
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

        vpc_id = ssm.StringParameter.value_from_lookup(self, parameter_name="/policy_atlas/vpc_id")

        vpc = ec2.Vpc.from_lookup(self, "VPC", vpc_id=vpc_id)

        ecr_registry = ecr.Repository.from_repository_name(self, "PolicyAtlasECRRepo",
            repository_name=self.node.try_get_context("@policy-atlas/ecr:repositoryName")
        )

        hosted_zone = r53.HostedZone.from_lookup(self, "HostedZone",
            domain_name=domain_name
        )

        # DB secret: ARN stored in SSM by DatabaseStack after its first deploy.
        db_secret_name = ssm.StringParameter.value_from_lookup(self,
            parameter_name="/policy_atlas/db/secret_name"
        )

        shared_log_group = logs.LogGroup(self, "PolicyAtlasLogGroup",
            log_group_name="/policy_atlas/application",
            retention=logs.RetentionDays.ONE_MONTH,
        )

        db_secret = secretsmanager.Secret.from_secret_name_v2(self, "DBSecret",
            secret_name=db_secret_name
        )

        # DB security group: stored in SSM by DatabaseStack.
        db_sg_id = ssm.StringParameter.value_from_lookup(self,
            parameter_name="/policy_atlas/db/security_group_id"
        )
        
        db_security_group = ec2.SecurityGroup.from_security_group_id(
            self, "DBSecurityGroup", security_group_id=db_sg_id,
            allow_all_outbound=False
        )

        # Frontend secret. Manually provisioned.
        fe_secret = secretsmanager.Secret.from_secret_name_v2(self, "AppSecret",
            secret_name=fe_config['secret_name']
        )
        
        # Backend secret. Manually provisioned.
        be_secret = secretsmanager.Secret.from_secret_name_v2(self, "BackendAppSecret",
            secret_name=be_config['secret_name']
        )

        cluster = ecs.Cluster(self, "PolicyAtlasCluster", vpc=vpc,
            cluster_name="policy-atlas-cluster"
        )

        # Frontend ALB: allow HTTPS and HTTP from the public internet.
        fe_alb_sg = ec2.SecurityGroup(self, "FrontendALBSG",
            vpc=vpc,
            description="Policy Atlas frontend ALB",
            allow_all_outbound=True
        )

        fe_alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(443))
        fe_alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80))

        # Frontend containers: allow traffic only from the frontend ALB.
        fe_sg = ec2.SecurityGroup(self, "FrontendSG",
            vpc=vpc,
            description="Policy Atlas frontend containers",
            allow_all_outbound=True
        )

        fe_sg.add_ingress_rule(fe_alb_sg, ec2.Port.tcp(fe_config["internal_port"]),
            "Allow frontend ALB to reach Next.js containers"
        )

        # Backend ALB: allow HTTPS and HTTP from the public internet.
        # PA, currently, uses public internet to invoke the API.
        # Future improvement: pivot to an internal call, and 
        # switch to an internal load balancer.
        be_alb_sg = ec2.SecurityGroup(self, "BackendALBSG",
            vpc=vpc,
            description="Policy Atlas backend ALB",
            allow_all_outbound=True
        )

        be_alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(443))
        be_alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80))

        # Backend containers: allow traffic only from the backend ALB.
        be_sg = ec2.SecurityGroup(self, "BackendSG",
            vpc=vpc,
            description="Policy Atlas backend containers",
            allow_all_outbound=True
        )

        be_sg.add_ingress_rule(be_alb_sg, ec2.Port.tcp(be_config["internal_port"]),
            "Allow backend ALB to reach FastAPI containers"
        )

        # Allow backend containers to connect to RDS on port 5432.
        db_security_group.add_ingress_rule(be_sg, ec2.Port.tcp(5432),
            "Allow Policy Atlas backend containers to connect to RDS"
        )

        fe_task_def = ecs.FargateTaskDefinition(self, "PolicyAtlasFrontendTaskDef",
            cpu=fe_config["cpu"],
            memory_limit_mib=fe_config["memory_limit_mib"],
            family="policy-atlas-frontend",
        )

        next_js_publishable_key = ssm.StringParameter.value_from_lookup(self, parameter_name="/policy_atlas/frontend/next_publishable_key")

        fe_task_def.add_container("policy-atlas-frontend-container",
            image=ecs.ContainerImage.from_asset("../frontend",
                platform=ecr_assets.Platform.LINUX_AMD64,
                build_args={
                    "NEXT_PUBLIC_API_URL": f"https://{be_domain}",
                    "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY": next_js_publishable_key,
                },
            ),
            cpu=fe_config["cpu"],
            memory_limit_mib=fe_config["memory_limit_mib"],
            logging=ecs.LogDrivers.aws_logs(stream_prefix="PolicyAtlasFrontend",
                                            log_group=shared_log_group),
            environment={
                # NEXT_PUBLIC_ vars must also be set as Docker build-args at image build time
                # to be available in client-side bundles. This env var covers server-side use.
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
                "NEXT_PUBLIC_CKERL_AFTER_SIGN_IN_URL": ecs.Secret.from_secrets_manager(
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

        fe_alb = elbv2.ApplicationLoadBalancer(self, "FrontendALB",
            vpc=vpc,
            internet_facing=True,
            security_group=fe_alb_sg,
            load_balancer_name="policy-atlas-frontend-alb"
        )

        # HTTP → HTTPS redirect.
        fe_alb.add_listener("FrontendHTTP", port=80, open=False).add_action(
            "FrontendHTTPRedirect",
            action=elbv2.ListenerAction.redirect(protocol="HTTPS", port="443", permanent=True)
        )

        fe_cert = acm.Certificate(self, "FrontendCertificate",
            domain_name=fe_domain,
            validation=acm.CertificateValidation.from_dns(hosted_zone)
        )

        fe_https_listener = fe_alb.add_listener("FrontendHTTPS",
            port=443,
            certificates=[fe_cert],
            open=False,
        )
        fe_https_listener.add_targets("FrontendTarget",
            port=fe_config["internal_port"],
            protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[fe_service.load_balancer_target(
                container_name="policy-atlas-frontend-container",
                container_port=fe_config["internal_port"],
                protocol=ecs.Protocol.TCP
            )],
            health_check=elbv2.HealthCheck(
                path="/",
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                healthy_threshold_count=2,
                unhealthy_threshold_count=5,
                healthy_http_codes="200-399",
            )
        )

        r53.ARecord(self, "FrontendARecord",
            zone=hosted_zone,
            record_name=fe_subdomain,  # None → zone apex
            target=r53.RecordTarget.from_alias(r53_targets.LoadBalancerTarget(fe_alb))
        )

        be_task_def = ecs.FargateTaskDefinition(self, "PolicyAtlasBackendTaskDef",
            cpu=be_config["cpu"],
            memory_limit_mib=be_config["memory_limit_mib"],
            family="policy-atlas-backend",
        )



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
            },
            secrets={
                # DB connection string written into the secret by LoadSecretTrigger in DatabaseStack.
                "DATABASE_URL": ecs.Secret.from_secrets_manager(db_secret, field="db_connection_string"),
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

        fe_secret.grant_read(be_task_def.task_role)
        db_secret.grant_read(be_task_def.task_role)

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

        be_alb = elbv2.ApplicationLoadBalancer(self, "BackendALB",
            vpc=vpc,
            internet_facing=True,
            security_group=be_alb_sg,
            load_balancer_name="policy-atlas-backend-alb"
        )

        # HTTP → HTTPS redirect.
        be_alb.add_listener("BackendHTTP", port=80, open=False).add_action(
            "BackendHTTPRedirect",
            action=elbv2.ListenerAction.redirect(protocol="HTTPS", port="443", permanent=True)
        )

        be_cert = acm.Certificate(self, "BackendCertificate",
            domain_name=be_domain,
            validation=acm.CertificateValidation.from_dns(hosted_zone)
        )

        be_https_listener = be_alb.add_listener("BackendHTTPS",
            port=443,
            certificates=[be_cert],
            open=False,
        )
        be_https_listener.add_targets("BackendTarget",
            port=be_config["internal_port"],
            protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[be_service.load_balancer_target(
                container_name="policy-atlas-backend-container",
                container_port=be_config["internal_port"],
                protocol=ecs.Protocol.TCP
            )],
            health_check=elbv2.HealthCheck(
                path="/",
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                healthy_threshold_count=2,
                unhealthy_threshold_count=5,
                healthy_http_codes="200-404",
            )
        )

        r53.ARecord(self, "BackendARecord",
            zone=hosted_zone,
            record_name=pa_app_config["backend_subdomain"],
            target=r53.RecordTarget.from_alias(r53_targets.LoadBalancerTarget(be_alb))
        )
