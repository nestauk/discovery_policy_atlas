# Deployment Overview

Deployment for Policy Atlas is managed via the AWS CDK, with related deployment code being in this folder (`infra/`). The deployment process is automated as follows:

1. A change is made or a feature branch merged into the 'dev' branch.
2. This triggers a GitHub Action to run the deployment pipeline for the 'dev' environment, which deploys any changes to the 'staging' environment in AWS.
3. Once the changes are verified in staging, a pull request is made to merge 'dev' into 'main'.
4. When main is verified to contain what is expected, a release is created in GitHub.
5. When the release is finalized and published, this triggers a GitHub Action to run the deployment pipeline for the 'production' environment, which deploys any changes to the 'production' environment in AWS.