# Network stack. Deploys a VPC with all related items.
# Does not deploy anything compute related to the application itself.
# Stack manages:
# * A single VPC with public and private subnets across all AZs.
# * An Internet Gateway for public subnet access to the internet.
# * A single FCK-nat instance for cost-effective NAT.

# Why fck-nat?
# Billing analysis shows that the a supermajority of the spend in the account
# is the NAT Gateway. fck-nat is equally as effective, but significantly cheaper.
from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_ssm as ssm,
    aws_route53 as route53,
)

from cdk_fck_nat import FckNatInstanceProvider, FckNatInstanceProps

class NetworkStack(Stack):
    def __init__(self, scope: Stack, id: str,
                 network_config: dict, aws_region: str, env_name: str, **kwargs,) -> None:
        super().__init__(scope, id, **kwargs)

        fck_nat_config = network_config['fck_nat']

        fck_nat = FckNatInstanceProvider(
            instance_type=ec2.InstanceType(fck_nat_config['instance_type'])
        )

        # Get the AZ count for the region.

        vpc = ec2.Vpc(self, "PolicyAtlasVPC",
            max_azs=network_config['azs'],
            nat_gateway_provider=fck_nat,
            vpc_name=f"policy-atlas-vpc-{env_name}",
            enable_dns_hostnames=True,
            enable_dns_support=True,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="PublicSubnet",
                    subnet_type=ec2.SubnetType.PUBLIC,
                ),
                ec2.SubnetConfiguration(
                    name="PrivateSubnet",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                )
            ]
        )
        
        fck_nat.security_group.add_ingress_rule(peer=ec2.Peer.ipv4(vpc.vpc_cidr_block), connection=ec2.Port.all_traffic())

        local_dns_zone = route53.PrivateHostedZone(self, "LocalDNSZone",
            zone_name=network_config['local_dns_zone_name'],
            vpc=vpc
        )

        # Output the ID into SSM for reference later.
        ssm.StringParameter(self, "VPCIdParameter",
            parameter_name="/policy_atlas/vpc_id",
            string_value=vpc.vpc_id
        )