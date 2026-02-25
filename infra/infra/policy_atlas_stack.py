from aws_cdk import (
    Stack,
    aws_ecs as ecs,
    aws_ecr as ecr,
    aws_secretsmanager as secrets,
    aws_ssm as ssm,
    aws_s3 as s3,
    aws_elasticloadbalancingv2 as elbv2,
    aws_route53 as r53,
    aws_route53_targets as r53_targets,
    aws_elasticloadbalancingv2_targets as targets,
    aws_ec2 as ec2,
    aws_certificatemanager as certs,
)
from constructs import Construct

class PolicyAtlasStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, 
                 pa_config: dict, supabase_config: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        ecs.Cluster(self, "PolicyAtlasFECluster",
            cluster_name="PolicyAtlasFECluster",
        )

        # Pull ECR repository by name. This is in context as it's not a value
        # that should be changed.
        repo = ecr.Repository.from_repository_name(self, "PolicyAtlasECRRepo",
            repository_name=self.node.try_get_context("@policy-atlas/ecr:repositoryName")
        )

        self.task_def = ecs.TaskDefinition(self, "PolicyAtlasFETaskDef",
            compatibility=ecs.Compatibility.FARGATE,
        )

        # Retrieve Supabase secrets from SSM parameters.
        jwt_secrets_param = ssm.StringParameter.from_string_parameter_name(self, "SupabaseJWTSecretsParam",
            string_parameter_name="/supabase/jwt-secrets"
        )
        storage_bucket_name = ssm.StringParameter.from_string_parameter_name(self, "SupabaseStorageBucketParam",
            string_parameter_name="/supabase/storage-bucket"
        )

        jwt_secret = secrets.Secret.from_secret_name_v2(self, "SupabaseJWTSecretFE",
            secret_name=jwt_secrets_param.string_value
        )

        storage_bucket = s3.Bucket.from_bucket_name(self, "SupabaseStorageBucketFE",
            bucket_name=storage_bucket_name.string_value
        )

        self.task_def.add_container("PolicyAtlasFEContainer",
            image=ecs.ContainerImage.from_ecr_repository(repo),
            environment={
                "SUPABASE_URL": f"http://{supabase_config['supabase_internal_domain']}:8000",
            },
            secrets={
                "SUPABASE_JWT_SECRET": ecs.Secret.from_secrets_manager(jwt_secret)
            },
            cpu=pa_config["cpu"],
            memory_limit_mib=pa_config["memory_limit_mib"],
        )

        # Grant the task read access to the JWT secret and storage bucket.
        jwt_secret.grant_read(self.task_def.task_role)
        storage_bucket.grant_read_write(self.task_def.task_role)

        # Front it all with a load balancer to enable autoscaling.
        self.alb = elbv2.ApplicationLoadBalancer(self, "PolicyAtlasALB",
            vpc=ec2.Vpc.from_lookup(self, "VPC", vpc_id=pa_config["vpc_id"]),
            internet_facing=True,
        )

        # Register the task with the load balancer. CDK will take care of the rest.
        listener = self.alb.add_listener("Listener", port=80)
        listener.add_targets("ECS",
            port=80,
            targets=[targets.EcsTask(
                task_definition=self.task_def,
                container_name="PolicyAtlasFEContainer",
                container_port=80,
            )]
        )

        self.public_dns = r53.HostedZone.from_lookup(self, "PublicHostedZone",
            domain_name=pa_config["public_hosted_zone"],
        )

        # Add an R53 domain record for the ALB.
        r53.ARecord(self, "PolicyAtlasALBRecord",
            zone=self.public_dns,
            record_name=pa_config["policy_atlas_public_domain"],
            target=r53.RecordTarget.from_alias(r53_targets.LoadBalancerTarget(self.alb)),
        )

        # SSL.
        certificate = certs.Certificate(self, "PolicyAtlasCertificate",
            domain_name=pa_config["policy_atlas_public_domain"],
            validation=certs.CertificateValidation.from_dns(self.public_dns),
        )

        listener.add_certificates("ListenerCertificate", [certificate])

        # Add SSL 443 routing.
        listener.add_targets("ECS-SSL",
            port=443,
            targets=[targets.EcsTask(
                task_definition=self.task_def,
                container_name="PolicyAtlasFEContainer",
                container_port=80,
            )],
            priority=10,  # Ensure this takes precedence over the default HTTP listener.
        )

        

