import os

from aws_cdk import (
    SecretValue,
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_rds as rds,
    aws_route53 as r53,
    aws_s3 as s3,
    aws_s3_assets as s3_assets,
    aws_secretsmanager as secretsmanager,
    aws_ssm as ssm,
)
from constructs import Construct


class SupabaseStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, supabase_config: dict, env_name: str,
                 aws_region: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        # This stack manages:
        # * An EC2 instance acting as a Docker host for Supabase services.
        # * An RDS PostgreSQL instance as the Supabase database backend.
        # * An S3 bucket for Supabase Storage (file uploads).
        # * Security groups wiring the two together within the VPC.
        # * An internal Route 53 A record so other services can reach Supabase by name.

        self.vpc = ec2.Vpc.from_lookup(self, "SPA_VPC", vpc_id=supabase_config["vpc_id"])

        # EC2 host: allow inbound Kong port from within VPC, unrestricted outbound
        # (outbound needed to pull Docker images and reach RDS).
        ec2_sg = ec2.SecurityGroup(self, "SupabaseHostSG",
            vpc=self.vpc,
            description="Supabase Docker host",
            allow_all_outbound=True,
        )
        ec2_sg.add_ingress_rule(
            ec2.Peer.ipv4(self.vpc.vpc_cidr_block),
            ec2.Port.tcp(8000),
            "Kong API gateway from VPC",
        )

        # RDS: only accept connections from the EC2 host.
        rds_sg = ec2.SecurityGroup(self, "SupabaseRDSSG",
            vpc=self.vpc,
            description="Supabase RDS - EC2 host access only",
            allow_all_outbound=False,
        )
        rds_sg.add_ingress_rule(ec2_sg, ec2.Port.tcp(5432), "PostgreSQL from Supabase host")

        param_group = rds.ParameterGroup(self, "SupabaseRDSParamGroup",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_15
            ),
            parameters={
                # pg_tle is required for installing pgjwt (and other TLE extensions) on RDS.
                # pg_stat_statements is needed by Supabase for query insights.
                "shared_preload_libraries": "pg_tle,pg_stat_statements",
                "rds.logical_replication": "1",  # Required for realtime to work properly.
            },
        )

        self.db = rds.DatabaseInstance(self, "SupabaseDB",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_15
            ),
            instance_type=ec2.InstanceType(supabase_config["db_instance_type"]),
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[rds_sg],
            database_name="postgres",
            deletion_protection=True,
            storage_encrypted=True,
            multi_az=supabase_config["multi_az_db"],
            parameter_group=param_group,
        )

        # Creates a storage bucket. Bucket is read from env.
        self.storage_bucket = s3.Bucket(self, "SupabaseStorageBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
        )

        instance_role = iam.Role(self, "SupabaseHostRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
            ],
        )

        # Read the RDS auto-generated credentials secret.
        self.db.secret.grant_read(instance_role)

        # Read and write Supabase Storage objects.
        self.storage_bucket.grant_read_write(instance_role)

        # Pre-create the JWT secret with an empty placeholder. init.sh detects the
        # placeholder on first boot, generates real values, and updates it via
        # put-secret-value. Subsequent boots read the already-populated value.
        supabase_secret_name = supabase_config["jwt_secret_name"]
        self.jwt_secret = secretsmanager.Secret(self, "SupabaseJWTSecret",
            secret_name=supabase_secret_name,
            secret_string_value=SecretValue.unsafe_plain_text("{}"),
            description="Supabase JWT secrets — populated by init.sh on first boot",
        )
        self.jwt_secret.grant_read(instance_role)
        self.jwt_secret.grant_write(instance_role)

        supabase_assets = s3_assets.Asset(self, "SupabaseAssets",
            path=os.path.join(os.path.dirname(__file__), "../assets/supabase"),
            deploy_time=True,  # We need the S3 location at deploy time to bake into UserData.
            display_name=f"Supabase Assets - from infra/assets/supabase."
        )
        supabase_assets.grant_read(instance_role)


        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            "dnf update -y",
            "dnf install -y docker postgresql15 gettext unzip",
            "systemctl enable --now docker",
            "usermod -aG docker ec2-user",
            # Docker Compose plugin
            "mkdir -p /usr/local/lib/docker/cli-plugins",
            'curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m)"'
            ' -o /usr/local/lib/docker/cli-plugins/docker-compose',
            "chmod +x /usr/local/lib/docker/cli-plugins/docker-compose",
            # Extract Supabase config assets
            "mkdir -p /opt/supabase",
        )

        # CDK resolves the S3 location of the asset into the UserData at deploy time.
        user_data.add_s3_download_command(
            bucket=supabase_assets.bucket,
            bucket_key=supabase_assets.s3_object_key,
            local_file="/tmp/supabase-assets.zip",
            region=self.region,
        )

        user_data.add_commands(
            "unzip -o /tmp/supabase-assets.zip -d /opt/supabase",
            "chmod +x /opt/supabase/init.sh",
            # Pass deployment-time values as env vars for init.sh
            f"export RDS_SECRET_ARN='{self.db.secret.secret_arn}'",
            f"export STORAGE_S3_BUCKET='{self.storage_bucket.bucket_name}'",
            f"export AWS_DEFAULT_REGION={aws_region}",
            f"export SUPABASE_JWT_SECRET_NAME='{supabase_secret_name}'",
            "cd /opt/supabase && bash init.sh 2>&1 | tee /var/log/supabase-init.log",
        )

        self.ec2_instance = ec2.Instance(self, "SupabaseHost",
            vpc=self.vpc,
            instance_type=ec2.InstanceType(supabase_config["instance_type"]),
            machine_image=ec2.AmazonLinuxImage(
                generation=ec2.AmazonLinuxGeneration.AMAZON_LINUX_2023,
            ),
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_group=ec2_sg,
            role=instance_role,
            user_data=user_data,
        )

        # Private hosted zone already exists in the VPC; look it up rather than create.
        local_dns = r53.HostedZone.from_lookup(self, "LocalDNSZone",
            domain_name=supabase_config["internal_domain_name"],
            private_zone=True,
            vpc_id=supabase_config["vpc_id"],
        )

        # A record points straight at the EC2 private IP.
        # Kong on port 8000 is the single entry point for all Supabase traffic.
        r53.ARecord(self, "SupabaseInternalRecord",
            zone=local_dns,
            record_name=supabase_config["supabase_internal_domain"],
            target=r53.RecordTarget.from_ip_addresses(self.ec2_instance.instance_private_ip),
        )

        # Store the JWT secret name in SSM so PolicyAtlasStack can look it up.
        ssm.StringParameter(self, "SupabaseJWTSecretsParam",
            parameter_name="/supabase/jwt-secrets",
            string_value=supabase_secret_name,
        )

        ssm.StringParameter(self, "SupabaseStorageBucketParam",
            parameter_name="/supabase/storage-bucket",
            string_value=self.storage_bucket.bucket_name,
        )

        # This is a bit of a hack, but... store SG ARN for the server
        # into SSM so PolicyAtlasStack can look it up and allowlist it in the Backend SG for direct DB access.
        ssm.StringParameter(self, "SupabaseHostSGParam",
            parameter_name="/supabase/host-sg-arn",
            string_value=ec2_sg.security_group_id,
        )