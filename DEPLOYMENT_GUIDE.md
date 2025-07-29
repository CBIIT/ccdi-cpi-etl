# CCDI CPI ETL - Prefect Deployment Guide

## Quick Command Line Deployment to ECR

Your ECR repository: `893214465464.dkr.ecr.us-east-1.amazonaws.com/cpi`

### Method 1: Using the automated script (Recommended)

```bash
# Make sure you're in the project root directory
./deploy_to_ecr.sh
```

### Method 2: Manual step-by-step deployment

```bash
# 1. Install prefect-docker if not already installed
pip install prefect-docker>=0.3.0

# 2. Set AWS Account ID for Prefect templates
export AWS_ACCOUNT_ID=893214465464

# 3. Login to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 893214465464.dkr.ecr.us-east-1.amazonaws.com

# 4. Deploy from config directory
cd config
prefect deploy --all
```

### Method 3: Deploy individual flows

```bash
cd config

# Deploy just the ETL pipeline
prefect deploy etl-pipeline

# Deploy just the database backup
prefect deploy database-backup
```

### Method 4: Build and push Docker image separately

```bash
# Use the build script
./build-and-push.sh

# Then deploy without building
cd config
prefect deploy --all --skip-build
```

## What will happen during deployment:

1. **Build Phase**: Docker image will be built using your Dockerfile
2. **Push Phase**: Image will be pushed to `893214465464.dkr.ecr.us-east-1.amazonaws.com/cpi:latest`
3. **Deploy Phase**: Two deployments will be created:
   - `etl-pipeline` (runs the main ETL flow)
   - `database-backup` (runs the MySQL backup flow)

## After deployment:

1. Go to your Prefect UI
2. Navigate to "Deployments"
3. You'll see two options in the dropdown:
   - **etl-pipeline** - CCDI CPI ETL data processing pipeline
   - **database-backup** - MySQL database backup using mysqldump

## Running the flows:

```bash
# Run ETL pipeline
prefect deployment run etl-pipeline/etl-pipeline

# Run database backup
prefect deployment run database-backup/database-backup
```

## Environment Variables needed:

The flows will need these AWS environment variables in your work pool:
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY` 
- `AWS_SESSION_TOKEN` (if using temporary credentials)
- `AWS_DEFAULT_REGION=us-east-1`

## Troubleshooting:

- **ECR login issues**: Make sure you have permissions to the `cpi` repository
- **Build fails**: Check that Docker is running and you're in the right directory
- **Deploy fails**: Ensure `prefect-docker` is installed and you're connected to Prefect Cloud/Server
