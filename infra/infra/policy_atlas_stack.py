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
                 pa_config: dict, supabase_config: dict, env_name: str, 
                 aws_region: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vpc = ec2.Vpc.from_lookup(self, "PAS_VPC", vpc_id=pa_config["vpc_id"])

        self.fe_ecs_cluster = ecs.Cluster(self, "PolicyAtlasFECluster",
            cluster_name="PolicyAtlasFECluster",
            vpc=vpc,
            enable_fargate_capacity_providers=True,
        )

        self.be_ecs_cluster = ecs.Cluster(self, "PolicyAtlasBECluster",
            cluster_name="PolicyAtlasBECluster",
            vpc=vpc,
            enable_fargate_capacity_providers=True,
        )

        # Pull ECR repository by name. This is in context as it's not a value
        # that should be changed.
        repo = ecr.Repository.from_repository_name(self, "PolicyAtlasECRRepo",
            repository_name=self.node.try_get_context("@policy-atlas/ecr:repositoryName")
        )

        self.fe_task_def = ecs.TaskDefinition(self, "PolicyAtlasFETaskDef",
            compatibility=ecs.Compatibility.FARGATE,
            # Why are we 'str'ing these files? CDK context, by default, loads everything
            # as strings; the custom config file does not, so this is needed to
            # ensure the types are correct.
            cpu=str(pa_config["cpu"]),
            memory_mib=str(pa_config["memory_limit_mib"]),
        )

        self.be_task_def = ecs.TaskDefinition(self, "PolicyAtlasBETaskDef",
            compatibility=ecs.Compatibility.FARGATE,
            cpu=str(pa_config["cpu"]),
            memory_mib=str(pa_config["memory_limit_mib"]),
        )

        storage_bucket_name = ssm.StringParameter.from_string_parameter_name(self, "SupabaseStorageBucketParam",
            string_parameter_name="/supabase/storage-bucket"
        )

        storage_bucket = s3.Bucket.from_bucket_name(self, "SupabaseStorageBucketFE",
            bucket_name=storage_bucket_name.string_value
        )

        fe_config = pa_config['frontend']
        be_config = pa_config['backend']

        # Pull the Supabase secret.
        supabase_config_secret = secrets.Secret.from_secret_name_v2(self, "SupabaseConfigSecret",
            secret_name=be_config["supabase_secret_name"]
        )


        self.fe_task_def.add_container("PolicyAtlasFEContainer",
            image=ecs.ContainerImage.from_ecr_repository(repo),
            port_mappings=[
                ecs.PortMapping(container_port=80, protocol=ecs.Protocol.TCP,
                                host_port=80)
                ],
        )

        self.be_task_def.add_container("PolicyAtlasBEContainer",
            image=ecs.ContainerImage.from_ecr_repository(repo),
            environment={
                "SUPABASE_URL": f"http://{supabase_config['supabase_internal_domain']}:8000",
            },
            port_mappings=[
                ecs.PortMapping(container_port=be_config["internal_port"], protocol=ecs.Protocol.TCP, 
                                host_port=8000)
            ]
        )

        # Configure flow for the network based on the following:
        # * Frontend serves HTTP on port 80. HTTPS on 443, via ALB with ACM certificate.
        # * Backend serves HTTP on port 8000, but is not exposed outside the cluster.
        # * Only Backend needs to be able to reach Supabase directly. Frontend talks to Backend.
        fe_sg = ec2.SecurityGroup(self, "FESecurityGroup",
            vpc=vpc,
            security_group_name="PolicyAtlasFE_SG",
            description="Allow HTTP/HTTPS from ALB",
            allow_all_outbound=True,
        )

        be_sg = ec2.SecurityGroup(self, "BESecurityGroup",
            vpc=vpc,
            security_group_name="PolicyAtlasBE_SG",
            description="Allow HTTP from FE, no outbound",
            allow_all_outbound=False,
        )

        alb_sg = ec2.SecurityGroup(self, "ALBSecurityGroup",
            vpc=vpc,
            security_group_name="PolicyAtlasALB_SG",
            description="Allow HTTP/HTTPS from anywhere",
            allow_all_outbound=True,
        )
        alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80), "Allow HTTP from anywhere")
        alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(443), "Allow HTTPS from anywhere")

        fe_sg.add_ingress_rule(alb_sg, ec2.Port.tcp(80), "HTTP from ALB")

        be_sg.add_ingress_rule(ec2.Peer.security_group_id(fe_sg.security_group_id), ec2.Port.tcp(8000))

        # Time for some shenanigans; allow Backend SG to talk to Supabase SG on Kong port (8000) by looking up the SG ARN from SSM and importing it here.
        supabase_sg_ref = ssm.StringParameter.from_string_parameter_name(self, "SupabaseHostSGParamRef",
            string_parameter_name="/supabase/host-sg-arn"
        )

        supabase_sg = ec2.SecurityGroup.from_security_group_id(self, "SupabaseHostSG",
            security_group_id=supabase_sg_ref.string_value,
            mutable=True,
        )

        be_sg.add_egress_rule(supabase_sg, ec2.Port.tcp(8000), "Allow BE to talk to Supabase on Kong port")


        # Grant the task read access to the JWT secret and storage bucket.

        storage_bucket.grant_read_write(self.fe_task_def.task_role)

        # Front it all with a load balancer to enable autoscaling.
        self.alb = elbv2.ApplicationLoadBalancer(self, "PolicyAtlasALB",
            vpc=ec2.Vpc.from_lookup(self, "VPC", vpc_id=pa_config["vpc_id"]),
            internet_facing=True,
        )

        self.fe_service = ecs.FargateService(self, "PolicyAtlasFEService",
            cluster=self.fe_ecs_cluster,
            task_definition=self.fe_task_def,
            desired_count=pa_config["desired_count"],
        )

        self_be_service = ecs.FargateService(self, "PolicyAtlasBEService",
            cluster=self.be_ecs_cluster,
            task_definition=self.be_task_def,
            desired_count=pa_config["desired_count"],
        )

        # Set task limits as definition
        fe_scaling = self.fe_service.auto_scale_task_count(
            max_capacity=fe_config["max_capacity"],
            min_capacity=fe_config["min_capacity"],
        )

        be_scaling = self_be_service.auto_scale_task_count(
            max_capacity=be_config["max_capacity"],
            min_capacity=be_config["min_capacity"],
        )

        # Set CPU scaling based on configuration
        fe_scaling.scale_on_cpu_utilization("FECpuScaling",
            target_utilization_percent=fe_config["cpu_target_utilization_percent"],
        )

        be_scaling.scale_on_cpu_utilization("BECpuScaling",
            target_utilization_percent=be_config["cpu_target_utilization_percent"],
        )

        # Set memory scaling based on configuration
        fe_scaling.scale_on_memory_utilization("FEMemoryScaling",
            target_utilization_percent=fe_config["memory_target_utilization_percent"],
        )

        be_scaling.scale_on_memory_utilization("BEMemoryScaling",
            target_utilization_percent=be_config["memory_target_utilization_percent"],
        )

        # Register the task with the load balancer. CDK will take care of the rest.
        listener = self.alb.add_listener("Listener", port=80)

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

        # Add HTTP 80 routing to the task.
        listener.add_targets("ECS-HTTP",
            port=80,
            targets=[self.fe_service],
        )

        # Add SSL 443 routing.
        listener.add_targets("ECS-SSL",
            port=443,
            targets=[self.fe_service],
        )

        

