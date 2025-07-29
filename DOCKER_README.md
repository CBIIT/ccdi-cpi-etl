# CCDI CPI ETL Docker Setup

This repository contains Docker configuration for the CCDI CPI ETL pipeline, including support for `mysqldump` and AWS services.

## Prerequisites

- Docker and Docker Compose installed
- AWS CLI configured with appropriate credentials
- Access to the CCDI AWS account and ECR

## Docker Image Features

- Based on Python 3.9 slim
- Includes MySQL client tools (`mysqldump`)
- All Python dependencies from `requirements.txt`
- Non-root user for security
- Optimized for container environments

## Building the Image Locally

```bash
# Build the image
docker build -t ccdi-cpi-etl .

# Run the main ETL pipeline
docker run --rm \
  -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
  -e AWS_SESSION_TOKEN=$AWS_SESSION_TOKEN \
  ccdi-cpi-etl

# Run the database backup
docker run --rm \
  -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
  -e AWS_SESSION_TOKEN=$AWS_SESSION_TOKEN \
  ccdi-cpi-etl python db.py
```

## Using Docker Compose

For local development and testing:

```bash
# Run the main ETL pipeline
docker-compose up ccdi-cpi-etl

# Run the database backup
docker-compose up db-backup

# Build and run in detached mode
docker-compose up -d ccdi-cpi-etl
```

## Pushing to Amazon ECR

### Using the Build Script (Recommended)

```bash
# Build and push with 'latest' tag
./build-and-push.sh

# Build and push with custom tag
./build-and-push.sh v1.0.0
```

The script will:
1. Check AWS credentials
2. Create ECR repository if it doesn't exist
3. Login to ECR
4. Build the Docker image
5. Tag and push to ECR

### Manual ECR Push

```bash
# Get AWS account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Create ECR repository (if not exists)
aws ecr create-repository --repository-name ccdi-cpi-etl --region us-east-1

# Login to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

# Build image
docker build -t ccdi-cpi-etl .

# Tag for ECR
docker tag ccdi-cpi-etl:latest $AWS_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/ccdi-cpi-etl:latest

# Push to ECR
docker push $AWS_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/ccdi-cpi-etl:latest
```

## Running from ECR

```bash
# Pull from ECR
docker pull $AWS_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/ccdi-cpi-etl:latest

# Run from ECR
docker run --rm \
  -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
  -e AWS_SESSION_TOKEN=$AWS_SESSION_TOKEN \
  $AWS_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/ccdi-cpi-etl:latest
```

## Prefect Integration

The Docker image is compatible with Prefect 3 deployments. You can use the ECR image URI in your Prefect deployment configuration:

```yaml
# In your prefect.yaml or deployment config
work_pool:
  name: your-work-pool
  job_variables:
    image: "123456789012.dkr.ecr.us-east-1.amazonaws.com/ccdi-cpi-etl:latest"
    env:
      AWS_DEFAULT_REGION: "us-east-1"
```

## Security Notes

- The image runs as a non-root user (`app`)
- AWS credentials are passed as environment variables
- No sensitive data is baked into the image
- ECR repository is configured with encryption and vulnerability scanning

## Troubleshooting

### mysqldump not found
- Ensure you're using the provided Dockerfile which installs `default-mysql-client`

### AWS credentials issues
- Verify AWS CLI is configured: `aws sts get-caller-identity`
- Check environment variables are set correctly
- For local development, ensure `~/.aws` directory is mounted

### ECR login issues
- Verify you have ECR permissions
- Check your AWS region is set correctly
- Try re-authenticating: `aws ecr get-login-password --region us-east-1`

## Files Overview

- `Dockerfile`: Multi-stage build with MySQL client tools
- `docker-compose.yml`: Local development environment
- `build-and-push.sh`: Automated ECR build and push script
- `.dockerignore`: Files to exclude from Docker context
