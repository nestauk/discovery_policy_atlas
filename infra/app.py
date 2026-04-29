#!/usr/bin/env python3
import os
import json
import aws_cdk as cdk
from aws_cdk import Environment

from infra.database_stack import DatabaseStack
from infra.policy_atlas_stack import PolicyAtlasStack
from infra.network_stack import NetworkStack

# Create CDK application instance, 
# and pull env_name from provided context. No default; if missing, abort.
app = cdk.App()

env_name = app.node.try_get_context("env_name")
if not env_name:
    raise ValueError("Context variable 'env_name' is required. Please provide it using '-c env_name=your_env'.")

with open('network_config.json') as f:
    config = json.load(f)
    network_config = config.get(env_name)
    if not network_config:
        raise ValueError(f"No network configuration found for environment '{env_name}' in network_config.json.")

with open('pa_config.json') as f:
    config = json.load(f)
    pa_config = config.get(env_name)
    if not pa_config:
        raise ValueError(f"No configuration found for environment '{env_name}' in pa_config.json.")

with open('db_config.json') as f:
    config = json.load(f)
    db_config = config.get(env_name)
    if not db_config:
        raise ValueError(f"No database configuration found for environment '{env_name}' in db_config.json.")

# Add 'VPCManaged': true tag to all resources recursively.
# Just in case we're looking manually and need to spot what this has built.
cdk.Tags.of(app).add("VPCManaged", "true", apply_to_launched_instances=True)

# Why three separate stacks?
# CDK will pick up on changes needed independently - so if
# we need to push Policy Atlas or Database updates independently, we can.
# The network stack will likely never need to change, but it's separate anyway for dependency.
net_env = Environment(
    account=network_config['aws_account_id'],
    region=network_config['aws_region']
)

NetworkStack(app, "NetworkStack", network_config=network_config, env=net_env,
             aws_region=network_config['aws_region'], env_name=env_name)

db_env = Environment(
    account=db_config['aws_account_id'],
    region=db_config['aws_region']
)

DatabaseStack(app, "DatabaseStack", db_config=db_config, env=db_env, env_name=env_name)

pa_env = Environment(
    account=pa_config['aws_account_id'],
    region=pa_config['aws_region']
)

PolicyAtlasStack(app, "PolicyAtlasStack", pa_config=pa_config, env=pa_env, env_name=env_name)

app.synth()