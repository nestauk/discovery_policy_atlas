# Network stack. Deploys a VPC with all related items.
# Does not deploy anything compute related to the application itself.
# Stack manages:
# * A single VPC with public and private subnets across all AZs.
# * An Internet Gateway for public subnet access to the internet.
# * A single FCK-nat instance for cost-effective NAT.
# * A shared internet-facing ALB with wildcard TLS certificate.
# * A Cloud Map namespace for internal service discovery.

# Why fck-nat?
# Billing analysis shows that the a supermajority of the spend in the account
# is the NAT Gateway. fck-nat is equally as effective, but significantly cheaper.
from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_ssm as ssm,
    aws_route53 as route53,
    aws_elasticloadbalancingv2 as elbv2,
    aws_certificatemanager as acm,
    aws_servicediscovery as servicediscovery,
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

        # Output the VPC ID into SSM for reference later.
        ssm.StringParameter(self, "VPCIdParameter",
            parameter_name="/policy_atlas/vpc_id",
            string_value=vpc.vpc_id
        )

        public_domain = network_config['public_domain_name']

        hosted_zone = route53.HostedZone.from_lookup(self, "PublicHostedZone",
            domain_name=public_domain
        )

        shared_alb_sg = ec2.SecurityGroup(self, "SharedALBSecurityGroup",
            vpc=vpc,
            description="Shared ALB for all Policy Atlas public services",
            allow_all_outbound=True,
        )
        shared_alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(443))
        shared_alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80))

        shared_alb = elbv2.ApplicationLoadBalancer(self, "SharedALB",
            vpc=vpc,
            internet_facing=True,
            security_group=shared_alb_sg,
            load_balancer_name="policy-atlas-shared-alb",
        )

        # Wildcard certificate covers *.staging.policyatlas.uk + the apex.
        wildcard_cert = acm.Certificate(self, "WildcardCertificate",
            domain_name=f"*.{public_domain}",
            subject_alternative_names=[public_domain],
            validation=acm.CertificateValidation.from_dns(hosted_zone),
        )

        # HTTPS listener — consuming stacks add their own target groups and rules.
        https_listener = shared_alb.add_listener("SharedHTTPS",
            port=443,
            certificates=[wildcard_cert],
            open=False,
        )
        https_listener.add_action("DefaultAction",
            action=elbv2.ListenerAction.fixed_response(
                status_code=404,
                content_type="text/plain",
                message_body="Not Found",
            )
        )

        # HTTP -> HTTPS redirect.
        shared_alb.add_listener("SharedHTTP", port=80, open=False).add_action(
            "HTTPRedirect",
            action=elbv2.ListenerAction.redirect(protocol="HTTPS", port="443", permanent=True),
        )

        # Export ALB attributes so consuming stacks can import and attach targets.
        ssm.StringParameter(self, "SharedALBArnParameter",
            parameter_name="/policy_atlas/shared_alb/arn",
            string_value=shared_alb.load_balancer_arn,
        )
        ssm.StringParameter(self, "SharedALBSGParameter",
            parameter_name="/policy_atlas/shared_alb/security_group_id",
            string_value=shared_alb_sg.security_group_id,
        )
        ssm.StringParameter(self, "SharedALBDnsParameter",
            parameter_name="/policy_atlas/shared_alb/dns_name",
            string_value=shared_alb.load_balancer_dns_name,
        )
        ssm.StringParameter(self, "SharedALBZoneParameter",
            parameter_name="/policy_atlas/shared_alb/canonical_hosted_zone_id",
            string_value=shared_alb.load_balancer_canonical_hosted_zone_id,
        )
        ssm.StringParameter(self, "SharedHTTPSListenerArnParameter",
            parameter_name="/policy_atlas/shared_alb/https_listener_arn",
            string_value=https_listener.listener_arn,
        )
        
        domain_without_tld = public_domain.rsplit(".", 1)[0]
        cloud_map_namespace = servicediscovery.PrivateDnsNamespace(self, "CloudMapNamespace",
            name=f"svc.{domain_without_tld}.local",
            vpc=vpc,
            description="Internal service discovery for Policy Atlas",
        )

        ssm.StringParameter(self, "CloudMapNamespaceIdParameter",
            parameter_name="/policy_atlas/cloudmap/namespace_id",
            string_value=cloud_map_namespace.namespace_id,
        )
        ssm.StringParameter(self, "CloudMapNamespaceArnParameter",
            parameter_name="/policy_atlas/cloudmap/namespace_arn",
            string_value=cloud_map_namespace.namespace_arn,
        )
        ssm.StringParameter(self, "CloudMapNamespaceNameParameter",
            parameter_name="/policy_atlas/cloudmap/namespace_name",
            string_value=cloud_map_namespace.namespace_name,
        )
