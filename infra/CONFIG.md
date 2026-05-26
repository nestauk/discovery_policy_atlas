# Configuration Overview

Configuration for the deployment is stored between `db_config.json`, `pa_config.json` and `network_config.json`.

Each configuration file handles a separate piece of the deployment.

A full list of all keys present and their definition is below.

> [!NOTE]  
> Not every value is editable. Please see below for 'user editable' symbols and meanings:

| Symbol | Meaning | Description|
|--------|---------|------------|
| 🛑 | Not Editable | Should not be modified without consulting DevOps Engineer. |
| ⚠️ | Partially Editable | Can be edited if required, but may have dependencies or may need to be kept in sync in other areas. Consult the DevOps Engineer for more information. |
| ✅ | Editable | Can be edited freely as per needs. |
| ℹ️ | Irrelevant | This object is a container for other values. |

## Network Config (`network_config.json`)

| JSON Key | Value Type | Purpose | User Editable |
|----------|------------|---------|---------------|
| `aws_account_id` | `string` | Defines the AWS account this stack should be deployed in for the environment. | 🛑 |
| `aws_region` | `string` | Defines the AWS region this stack should be deployed in for the environment. | ⚠️ |
| `fck_nat` | [`dict`](#fck-nat-config) | Defines configuration options for the fck-nat deployment for the environment. | ℹ️ |
| `local_dns_zone_name` | `string (url)` | Defines the 'local DNS' name that should be provisioned, which is then used in later stacks. | ⚠️ |
| `azs` | `int` | Defines the number of AZs to spread networking over. Should generally match the maximum AZs available in the `aws_region`. (For EU London, this is 3.) Setting this to 1 will remove high availability. | ✅ |

### fck-nat Config

| JSON Key | Value Type | Purpose | User Editable |
|----------|------------|---------|---------------|
| `instance_type` | `string (ec2 instance type)` | Defines what size instance the fck-nat instances should use. Outside of extreme high bandwidth outbound traffic requirements, the default - `t4g.nano` - should suffice. | ✅ |

## Database Config (`db_config.json`)

> [!WARN]
> Changing of these values can result in data loss if the database requires recreation. Please consult the DevOps Engineer for a transition plan if this is required.

| JSON Key | Value Type | Purpose | User Editable |
|----------|------------|---------|---------------|
| `aws_account_id` | `string` | Defines the AWS account this stack should be deployed in for the environment. | 🛑 |
| `aws_region` | `string` | Defines the AWS region this stack should be deployed in for the environment. | ⚠️ |
| `writer_instance_size` | `string (db instance type)` | Defines what size instance the database cluster should use for its writer node. This is the core node, and will manage all writes to the database cluster, so size this accordingly. | ⚠️ |
| `reader_instance_size` | `string (db instance type)` | Defines what size instance the database cluster should use for its reader nodes. | ⚠️ |
| `readers` | `int` | Defines how many additional reader nodes should be provisioned in the cluster. Can range from 0-15. 0 will not deploy any reader nodes. | ✅ |
| `studio-meta` | [`dict`](#metabase-studio-config) | Defines configuration options for the Metabase Studio deployment alongside the database. | ℹ️ |
| `base_domain_name` | `url` | The core URL for Policy Atlas. Used to define the appropriate domain to configure for the Metabase Studio endpoint. This domain must exist in Route 53 ahead of time - please speak to DevOps Engineer for further assistance. | ⚠️ |
| `local_domain_name` | `url` | The local domain name to use for internal database endpoints. Must match the `local_domain_name` in the Network Config and Policy Atlas Config entries, or components will not be able to communicate effectively. | ⚠️ |
| `studio_subdomain` | `string` | The subdomain to provision the Metabase Studio tool on. Will be used as https://{`studio_subdomain`}.{`base_domain_name`} | ✅ |
| `postgres_meta_tag` | `string` | The postgres-meta image tag to deploy as part of Metabase Studio. Changing this will change the version of postgres-meta deployed.
| `studio_tag` | `string` | The metabase-studio image tag to deploy as part of Metabase Studio. Changing this will change the version of the studio deployed. | ✅ |
| `studio_whitelist_ips` | `list[IP Address CIDR]` | The IPs, or IP ranges, to allow access to Metabase Studio. Leaving this blank will open it to the world (0.0.0.0/32) - this is extremely unsafe. | ✅ |

### Metabase Studio Config

| JSON Key | Value Type | Purpose | User Editable |
|----------|------------|---------|---------------|
| `cpu` | `int` | Defines how many CPUs to allocate. Only certain CPU and memory pairs are allowed. Please see AWS Fargate documentation for further information. (Reference: 1024 = 1vCPU) | ✅ |
| `memory_limit_mb` | `int` | Defines the maximum amount of memory to allocate. Only certain CPU and memory pairs are allowed. Please see AWS Fargate documentation for further information. | ✅ |

## Policy Atlas Config (`pa_config.json`)

| JSON Key | Value Type | Purpose | User Editable |
|----------|------------|---------|---------------|
| `aws_account_id` | `string` | Defines the AWS account this stack should be deployed in for the environment. | 🛑 |
| `aws_region` | `string` | Defines the AWS region this stack should be deployed in for the environment. | ⚠️ |
| `policy_atlas_config` | [`dict`](#policy-atlas-subconfig) | Contains configuration for individual Policy Atlas components. | ℹ️ |

### Policy Atlas Subconfig

| JSON Key | Value Type | Purpose | User Editable |
|----------|------------|---------|---------------|
| `domain_name` | `url` | Defines the primary aplication base URL. This should match the base domain name used in the [Database Config](#database-config-db_configjson). This domain name must be registered in Route 53 ahead of time - please speak to DevOps Engineer for further assistance. | ⚠️ |
| `frontend_subdomain` | `string` | Defines an optional subdomain for the frontend. If not specified, the frontend will use the `domain_name` value - in most cases, this is what is intended. | ✅ |
| `backend_subdomain` | `string` | Defines the subdomain the backend endpoint will use to listen for requests. In most cases, this can remain as 'api'. | ✅ |
| `frontend` | [`dict`](#policy-atlas-container-config) | Contains container level configuration for the frontend containers. | ℹ️ | 
| `backend` | [`dict`](#policy-atlas-container-config) | Contains container level configuration for the backend containers. | ℹ️ |

#### Policy Atlas Container Config

| JSON Key | Value Type | Purpose | User Editable |
|----------|------------|---------|---------------|
| `cpu` | `int` | Defines how many CPUs to allocate. Only certain CPU and memory pairs are allowed. Please see AWS Fargate documentation for further information. (Reference: 1024 = 1vCPU) | ✅ |
| `memory_limit_mb` | `int` | Defines the maximum amount of memory to allocate. Only certain CPU and memory pairs are allowed. Please see AWS Fargate documentation for further information. | ✅ |
| `desired_count` | `int` | Defines the baseline number of containers to provision. Auto-scaling will modify this number as load changes. | ✅ |
| `min_capacity` | `int` | The absolute minimum capacity of the container cluster. Auto-scaling will never reduce the amount of containers below this amount. | ✅ |
| `max_capacity` | `int` | The absolute maximum capacity of the container cluster. Auto-scaling will never increase the amount of containers above this amount. | ✅ |
| `internal_port` | `int` | The internal port to map for outside traffic. This will only need to be modified should you change the ports listening in the applications themselves. Setting this incorrectly will inhibit traffic reaching the containers. | ✅ |
| `cpu_target_utilization_percent` | `int` | The 'expected' amount of CPU utilization for a given container instance. Auto-scaling will add instances up to `max_capacity` if this is breached, and remove instances down to `min_capacity` if it is lower. Consider it a 'CPU target'. Closer values to 100% will extract more value per container, but can result in resource strains when scaling if set too high or the surge of traffic is too rapid. Values above 100% will cause undefined behaviour with autoscaling, or deployment failures. | ✅ |
| `memory_target_utilization_percent` | `int` | The 'expected' amount of memory utilization for a given container instance. Auto-scaling will add instances up to `max_capacity` if this is breached, and remove instances down to `min_capacity` if it is lower. Consider it a 'CPU target'. Closer values to 100% will extract more value per container, but can result in resource strains when scaling if set too high or the surge of traffic is too rapid. Values above 100% will cause undefined behaviour with autoscaling, or deployment failures. | ✅ |
| `registry_tag` | `string` | No longer used, and will be removed in a later revision of the infrastructure code. | ✅ |
| `secret_name` | `string` | Name of the secret to use to pull environment variables in at container launch. This should not be modified without ensuring the secret exists ahead of time and has all relevant entries, as doing so will cause deployment failures. | ✅ |