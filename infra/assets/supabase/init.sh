#!/usr/bin/env bash
# init.sh — Bootstrap script for Supabase on EC2 with RDS.
#
# Expected environment variables (set by CDK UserData before this script runs):
#   RDS_SECRET_ARN       — ARN of the CDK-managed RDS Secrets Manager secret
#   STORAGE_S3_BUCKET    — Name of the S3 bucket for Supabase Storage
#   AWS_DEFAULT_REGION   — AWS region (e.g. eu-west-2)
#
# Idempotent: safe to re-run. On first run it generates JWT secrets and stores
# them in Secrets Manager so they survive instance replacement.

set -euo pipefail

echo "==> Starting Supabase init script"
WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JWT_SECRET_NAME="${SUPABASE_JWT_SECRET_NAME}"

log() { echo "[init] $*"; }

# Resolve region — prefer env var, fall back to IMDSv2 instance metadata.
log "AWS_DEFAULT_REGION from environment: '${AWS_DEFAULT_REGION:-}'"
log "AWS_REGION from environment: '${AWS_REGION:-}'"
if [[ -z "${AWS_DEFAULT_REGION:-}" ]]; then
  log "AWS_DEFAULT_REGION not set — fetching from IMDSv2"
  IMDS_TOKEN=$(curl -sf -X PUT "http://169.254.169.254/latest/api/token" \
    -H "X-aws-ec2-metadata-token-ttl-seconds: 21600") || { log "ERROR: IMDSv2 token request failed (exit $?)"; exit 1; }
  log "IMDSv2 token acquired (length ${#IMDS_TOKEN})"
  AWS_DEFAULT_REGION=$(curl -sf \
    -H "X-aws-ec2-metadata-token: $IMDS_TOKEN" \
    "http://169.254.169.254/latest/meta-data/placement/region") || { log "ERROR: IMDSv2 region request failed (exit $?)"; exit 1; }
  export AWS_DEFAULT_REGION
  log "Region from IMDSv2: '${AWS_DEFAULT_REGION}'"
else
  log "Region inherited from environment"
fi

if [[ -z "${AWS_DEFAULT_REGION:-}" ]]; then
  log "ERROR: AWS_DEFAULT_REGION is empty after all resolution attempts"
  exit 1
fi
log "Using region: ${AWS_DEFAULT_REGION}"

# ── 1. Fetch RDS credentials ──────────────────────────────────────────────────
log "Fetching RDS credentials from Secrets Manager (${RDS_SECRET_ARN})"
RDS_JSON=$(aws secretsmanager get-secret-value \
  --secret-id "${RDS_SECRET_ARN}" \
  --query SecretString \
  --output text \
  --region "${AWS_DEFAULT_REGION}")

POSTGRES_HOST=$(echo "${RDS_JSON}" | python3 -c "import sys,json; print(json.load(sys.stdin)['host'])")
POSTGRES_PORT=$(echo "${RDS_JSON}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('port', 5432))")
POSTGRES_PASSWORD=$(echo "${RDS_JSON}" | python3 -c "import sys,json; print(json.load(sys.stdin)['password'])")

# ── 2. Fetch or populate JWT secrets ─────────────────────────────────────────
# The secret is pre-created by CDK with a placeholder value ({}).
# On first boot we generate real values and update it; on subsequent boots we
# read the already-populated value.
log "Fetching JWT secrets from Secrets Manager (${JWT_SECRET_NAME})"
JWT_JSON=$(aws secretsmanager get-secret-value \
  --secret-id "${JWT_SECRET_NAME}" \
  --query SecretString \
  --output text \
  --region "${AWS_DEFAULT_REGION}")

if ! echo "${JWT_JSON}" | python3 -c "import sys,json; json.load(sys.stdin)['jwt_secret']" &>/dev/null; then
  log "JWT secrets not yet initialised — generating and storing"
  JWT_JSON=$(python3 - <<'PYEOF'
import hmac, hashlib, base64, json, time, secrets as _secrets

def b64url(data):
    if isinstance(data, str):
        data = data.encode()
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()

def make_jwt(payload, secret):
    header = b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(',', ':')))
    body   = b64url(json.dumps(payload, separators=(',', ':')))
    msg    = f"{header}.{body}"
    sig    = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).digest()
    return f"{msg}.{b64url(sig)}"

jwt_secret     = _secrets.token_hex(32)
secret_key_base = _secrets.token_hex(64)
db_enc_key     = _secrets.token_hex(16)
now            = int(time.time())
far_future     = now + 315_360_000  # 10 years

anon_key    = make_jwt({"role": "anon",         "iss": "supabase", "iat": now, "exp": far_future}, jwt_secret)
service_key = make_jwt({"role": "service_role", "iss": "supabase", "iat": now, "exp": far_future}, jwt_secret)

print(json.dumps({
    "jwt_secret":      jwt_secret,
    "anon_key":        anon_key,
    "service_role_key": service_key,
    "secret_key_base": secret_key_base,
    "db_enc_key":      db_enc_key,
}))
PYEOF
  )
  aws secretsmanager put-secret-value \
    --secret-id "${JWT_SECRET_NAME}" \
    --secret-string "${JWT_JSON}" \
    --region "${AWS_DEFAULT_REGION}"
else
  log "Using existing JWT secrets"
fi

JWT_SECRET=$(echo "${JWT_JSON}"     | python3 -c "import sys,json; print(json.load(sys.stdin)['jwt_secret'])")
ANON_KEY=$(echo "${JWT_JSON}"       | python3 -c "import sys,json; print(json.load(sys.stdin)['anon_key'])")
SERVICE_ROLE_KEY=$(echo "${JWT_JSON}" | python3 -c "import sys,json; print(json.load(sys.stdin)['service_role_key'])")
SECRET_KEY_BASE=$(echo "${JWT_JSON}" | python3 -c "import sys,json; print(json.load(sys.stdin)['secret_key_base'])")
DB_ENC_KEY=$(echo "${JWT_JSON}"     | python3 -c "import sys,json; print(json.load(sys.stdin)['db_enc_key'])")

# ── 3. Run DB initialisation (once) ──────────────────────────────────────────
FLAG_FILE="/opt/supabase/.db_initialised"
if [ ! -f "${FLAG_FILE}" ]; then
  log "Installing pgjwt via TLE (db/pgjwt_tle.sql)"
  PGPASSWORD="${POSTGRES_PASSWORD}" psql \
    "host=${POSTGRES_HOST} port=${POSTGRES_PORT} dbname=postgres user=postgres sslmode=require" \
    -f "${WORKDIR}/db/pgjwt_tle.sql"

  log "Running DB role/schema initialisation (db/roles.sql)"
  PGPASSWORD="${POSTGRES_PASSWORD}" psql \
    "host=${POSTGRES_HOST} port=${POSTGRES_PORT} dbname=postgres user=postgres sslmode=require" \
    -v POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" \
    -f "${WORKDIR}/db/roles.sql"

  touch "${FLAG_FILE}"
else
  log "DB already initialised, skipping"
fi

# ── 4. Substitute kong.yml.template ──────────────────────────────────────────
log "Generating kong.yml from template"
export ANON_KEY SERVICE_ROLE_KEY
envsubst '${ANON_KEY} ${SERVICE_ROLE_KEY}' \
  < "${WORKDIR}/kong.yml.template" \
  > "${WORKDIR}/kong.yml"

# ── 5. Write .env ─────────────────────────────────────────────────────────────
log "Writing .env"
SITE_URL="${SITE_URL:-http://localhost:8000}"
API_EXTERNAL_URL="${API_EXTERNAL_URL:-${SITE_URL}}"
DASHBOARD_PASSWORD="${DASHBOARD_PASSWORD:-$(openssl rand -base64 16)}"

cat > "${WORKDIR}/.env" <<EOF
# Database — sourced from RDS Secrets Manager at boot
POSTGRES_HOST=${POSTGRES_HOST}
POSTGRES_PORT=${POSTGRES_PORT}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}

# JWT — generated on first boot and stored in Secrets Manager
JWT_SECRET=${JWT_SECRET}
ANON_KEY=${ANON_KEY}
SERVICE_ROLE_KEY=${SERVICE_ROLE_KEY}
JWT_EXPIRY=3600

# Realtime
SECRET_KEY_BASE=${SECRET_KEY_BASE}
DB_ENC_KEY=${DB_ENC_KEY}

# URLs
SITE_URL=${SITE_URL}
API_EXTERNAL_URL=${API_EXTERNAL_URL}

# Storage (S3 — credentials come from the EC2 instance role)
STORAGE_S3_BUCKET=${STORAGE_S3_BUCKET}
AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION}

# Studio basic-auth
DASHBOARD_PASSWORD=${DASHBOARD_PASSWORD}

# SMTP (optional — configure to enable email auth)
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASS=
SMTP_ADMIN_EMAIL=
SMTP_SENDER_NAME=Policy Atlas
EOF

# ── 6. Start services ─────────────────────────────────────────────────────────
log "Starting Supabase services"
docker compose --project-directory "${WORKDIR}" up -d

log "Done. Kong is listening on :8000"
