# Policy Atlas IAC

This CDK project manages and deploys a full build of the AWS environment for Policy Atlas, and handles the following tasks:

* Configuration of the environment
* Deployment and management of runtime containers

# Prerequisites

The DNS needs to be configured centrally per account - this is done via Route 53, but any hostname provider can be used: just add a new Hosted Zone in R53 for the given account, and then add the appropriate NS records as provided by DNS into the original provider DNS. Alternatively, domains can be registered directly into Route 53.

Lookup of the hosted zone is done automatically via the `domain_name` configuration parameter.

Subdomains - such as `staging.*` - should use their own zone with relevant delegation.

## CDK Context

The CDK context is mostly unused - for ease of configuration, most configuration is moved out to `pa_config.json` and `db_config.json`. The `cdk.json` file should not be modified.

## Configuration

Configuration is stored in the `pa_config.json`, `db_config.json` and `network_config.json` files, and has the following structure:

```json
{
    "env_name": {
        ...
    },
    "env_name_2": {
        ...
    }
}
```

The `env_name` parameter is passed to the build process as a context variable (via `cdk deploy --c env_name="env_name"`) and the appropriate configuration is loaded.

[Detailed information on the config entries can be found here.](./CONFIG.md)