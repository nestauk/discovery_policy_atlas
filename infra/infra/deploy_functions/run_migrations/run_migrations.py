import boto3
import json
import os
import glob
import logging

import pg8000.native
import sqlparse

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    secret_name = os.environ["SECRET_NAME"]
    secret = json.loads(
        boto3.client("secretsmanager")
        .get_secret_value(SecretId=secret_name)["SecretString"]
    )

    conn = pg8000.native.Connection(
        user=secret["username"],
        password=secret["password"],
        host=secret["host"],
        port=int(secret["port"]),
        database=secret["dbname"],
    )

    # If a JWT secret is configured, inject the authenticator password as a
    # session variable so the PostgREST roles migration can read it via
    # current_setting('app.authenticator_password').
    jwt_secret_name = os.environ.get("JWT_SECRET_NAME")
    if jwt_secret_name:
        jwt_secret = json.loads(
            boto3.client("secretsmanager")
            .get_secret_value(SecretId=jwt_secret_name)["SecretString"]
        )
        authenticator_password = jwt_secret.get("authenticator_password")
        if authenticator_password:
            conn.run(
                "SELECT set_config('app.authenticator_password', :pwd, false)",
                pwd=authenticator_password,
            )
            logger.info("Set session variable app.authenticator_password.")

    migrations_dir = os.path.join(os.path.dirname(__file__), "migrations")
    migration_files = sorted(glob.glob(os.path.join(migrations_dir, "*.sql")))

    if not migration_files:
        logger.warning("No migration files found in %s", migrations_dir)
        return {"status": "ok", "migrations_applied": 0}

    for migration_file in migration_files:
        filename = os.path.basename(migration_file)
        logger.info("Applying: %s", filename)
        with open(migration_file, "r") as f:
            sql = f.read()
        statements = [s.strip() for s in sqlparse.split(sql) if s.strip()]
        for stmt in statements:
            conn.run(stmt)
        logger.info("Done: %s (%d statements)", filename, len(statements))

    conn.close()
    logger.info("All %d migrations applied.", len(migration_files))
    return {"status": "ok", "migrations_applied": len(migration_files)}
