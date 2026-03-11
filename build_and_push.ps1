# Used by LH to manually build and push images to ECR for testing. Not used in CI/CD.
# Invoke with .\build_and_push.ps1 from the repo root.
# Assumes a valid AWS CLI profile named "policy-atlas-staging" with ECR + Secrets Manager permissions.
$ErrorActionPreference = "Stop"

$AWS_PROFILE = "policy-atlas-staging"
$ECR_REPO    = "policy-atlas/repo"
$REGION      = aws --profile $AWS_PROFILE configure get region
$ACCOUNT_ID  = aws --profile $AWS_PROFILE sts get-caller-identity --query Account --output text
$ECR_BASE    = "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO}"

Write-Host "==> Authenticating with ECR (account: $ACCOUNT_ID, region: $REGION)"
aws ecr get-login-password --profile $AWS_PROFILE --region $REGION |
    docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

Write-Host "==> Building backend image"
docker build --platform linux/amd64 --provenance=false -t "${ECR_BASE}:backend" ./backend

Write-Host "==> Pushing backend image"
docker push "${ECR_BASE}:backend"

$SECRET_JSON = aws secretsmanager get-secret-value --profile $AWS_PROFILE --region $REGION `
    --secret-id "policy_atlas/frontend" --query SecretString --output text
$CLERK_PUBLISHABLE_KEY = ($SECRET_JSON | ConvertFrom-Json).NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY

Write-Host "==> Building frontend image"
docker build --platform linux/amd64 --provenance=false `
    --build-arg "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=$CLERK_PUBLISHABLE_KEY" `
    -t "${ECR_BASE}:frontend" ./frontend

Write-Host "==> Pushing frontend image"
docker push "${ECR_BASE}:frontend"

Write-Host "==> Done. Images pushed:"
Write-Host "    ${ECR_BASE}:backend"
Write-Host "    ${ECR_BASE}:frontend"
