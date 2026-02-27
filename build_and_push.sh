#!/usr/bin/env bash
# Used by LH to manually build and push images to ECR for testing. Not used in CI/CD, which uses GitHub Actions workflows.
# Invoke with ./build-and-push.sh from the repo root. Assumes a valid AWS CLI profile named "policy-atlas-staging" with permissions to access ECR and Secrets Manager.
set -euo pipefail

AWS_PROFILE="policy-atlas-staging"
ECR_REPO="policy-atlas/repo"
REGION=$(aws --profile "$AWS_PROFILE" configure get region)
ACCOUNT_ID=$(aws --profile "$AWS_PROFILE" sts get-caller-identity --query Account --output text)
ECR_BASE="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO}"

echo "==> Authenticating with ECR (account: ${ACCOUNT_ID}, region: ${REGION})"
aws ecr get-login-password --profile "$AWS_PROFILE" --region "$REGION" \
  | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

echo "==> Building backend image"
docker build -t "${ECR_BASE}:backend" ./backend

echo "==> Pushing backend image"
docker push "${ECR_BASE}:backend"

CLERK_PUBLISHABLE_KEY=$(aws secretsmanager get-secret-value --profile "$AWS_PROFILE" --region "$REGION" \
  --secret-id "policy_atlas/frontend" --query SecretString --output text | jq -r .NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY)

echo "==> Building frontend image"
docker build \
  --build-arg NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY="$CLERK_PUBLISHABLE_KEY" \
  -t "${ECR_BASE}:frontend" ./frontend

echo "==> Pushing frontend image"
docker push "${ECR_BASE}:frontend"

echo "==> Done. Images pushed:"
echo "    ${ECR_BASE}:backend"
echo "    ${ECR_BASE}:frontend"