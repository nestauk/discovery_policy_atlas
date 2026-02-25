#!/usr/bin/env python3
import os
import json
import aws_cdk as cdk

from infra.infra.policy_atlas_stack import PolicyAtlasStack
from infra.infra.supabase_stack import SupabaseStack

# Load config.json into memory.
with open("config.json") as config_file:
    config = json.load(config_file)

# Create CDK application instance, 
# and pull env_name from provided context. No default; if missing, abort.
app = cdk.App()

env_name = app.node.try_get_context("env_name")
if not env_name:
    raise ValueError("Context variable 'env_name' is required. Please provide it using '-c env_name=your_env'.")

env_config = config.get(env_name)
if not env_config:
    raise ValueError(f"Environment '{env_name}' not found in config.json. Please check your configuration.")

# Add 'VPCManaged': true tag to all resources recursively.
# Just in case we're looking manually and need to spot what this has built.
cdk.Tags.of(app).add("VPCManaged", "true", apply_to_launched_instances=True)

# Why two separate stacks?
# CDK will pick up on changes needed independently - so if
# Policy Atlas updates, then the Supabase stack will remain untouched
# if needed.
# This logic can be extended out for other additional components as needed.
SupabaseStack(app, f"SupabaseStack-{env_name}",
    supabase_config=env_config["supabase_config"],
    env=cdk.Environment(
        account=env_config["aws_account_id"],
        region=env_config["aws_region"]
    )
)

PolicyAtlasStack(app, f"PolicyAtlasStack-{env_name}",
    pa_config=env_config["policy_atlas_config"],
    supabase_config=env_config["supabase_config"],
    env=cdk.Environment(
        account=env_config["aws_account_id"],
        region=env_config["aws_region"]
    )
)

app.synth()
