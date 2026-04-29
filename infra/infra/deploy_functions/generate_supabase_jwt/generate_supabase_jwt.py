import boto3
import json
import logging
import os
import secrets
import time

import jwt

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    jwt_secret_name = os.environ["JWT_SECRET_NAME"]
    db_secret_name = os.environ["DB_SECRET_NAME"]

    client = boto3.client("secretsmanager")

    # Idempotency: if the secret already contains a jwt_secret field, do nothing.
    try:
        existing = json.loads(
            client.get_secret_value(SecretId=jwt_secret_name)["SecretString"]
        )
        if existing.get("jwt_secret"):
            logger.info("JWT secret already populated — skipping generation.")
            return {"status": "ok", "action": "skipped"}
    except client.exceptions.ResourceNotFoundException:
        existing = {}
    except (json.JSONDecodeError, KeyError):
        existing = {}

    # Read RDS secret to build the PostgREST connection URI.
    db_secret = json.loads(
        client.get_secret_value(SecretId=db_secret_name)["SecretString"]
    )

    jwt_secret = secrets.token_urlsafe(48)  # 64 base64 chars
    authenticator_password = secrets.token_urlsafe(24)  # 32 base64 chars

    now = int(time.time())
    ten_years = 10 * 365 * 24 * 60 * 60

    anon_key = jwt.encode(
        {"role": "anon", "iss": "policy-atlas", "iat": now, "exp": now + ten_years},
        jwt_secret,
        algorithm="HS256",
    )

    service_role_key = jwt.encode(
        {
            "role": "service_role",
            "iss": "policy-atlas",
            "iat": now,
            "exp": now + ten_years,
        },
        jwt_secret,
        algorithm="HS256",
    )

    postgrest_db_uri = (
        f"postgresql://authenticator:{authenticator_password}"
        f"@{db_secret['host']}:{db_secret['port']}/{db_secret['dbname']}"
        f"?sslmode=require"
    )

    secret_value = {
        "jwt_secret": jwt_secret,
        "anon_key": anon_key,
        "service_role_key": service_role_key,
        "authenticator_password": authenticator_password,
        "postgrest_db_uri": postgrest_db_uri,
    }

    client.update_secret(
        SecretId=jwt_secret_name, SecretString=json.dumps(secret_value)
    )

    logger.info("JWT secret populated successfully.")
    return {"status": "ok", "action": "generated"}
