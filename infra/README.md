# Policy Atlas IAC

This CDK project manages and deploys a full build of the AWS environment for Policy Atlas, and handles the following tasks:

* Configuration of the environment
* Deployment and management of runtime containers

# Prerequisites

As some of the features I intend to use in AWS VPCs - such as Zonal NAT Gateways - are unavailable by the CDK, I've preconfigured a single VPC with required settings.

This is imported into the CDK as needed, but does require initial setup on new accounts or when building a new env within an account.

In addition, the DNS needs to be configured centrally - this is done via Route 53, but any hostname provider can be used: just add a new Hosted Zone in R53 for the given account, and then add the appropriate NS records as provided by DNS into the original provider DNS. Alternatively, domains can be registered directly into Route 53.

Lookup of the hosted zone is done automatically via the `domain_name` configuration parameter.

Subdomains - such as `staging.*` - should use their own zone with relevant delegation.

### How To Setup

Use the AWS Console to create a new VPC (and more), and specify the NAT type as 'Regional'. When done, add the VPC configuration into the "supabase_config" and "vpc_config" for the environment.

It is *possible* to share a VPC between environments, but this is not recommended.

## CDK Context

The CDK context is mostly unused - for ease of configuration, most configuration is moved out to `config.json`. The `cdk.json` file should not be modified.

## Configuration

Configuration is stored in the `config.json` file, and has the following structure:

```json
{
    "env_name": {
        ...
    },
    "env_name_2: {
        ...
    }
}
```

The `env_name` parameter is passed to the build process as a context variable (via `cdk deploy --c env_name="env_name"`) and the appropriate configuration is loaded.