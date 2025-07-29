#!/bin/bash

# ECR Deployment Script for CCDI CPI ETL Prefect Flows
# This script handles the complete deployment process including ECR setup

set -e  # Exit on any error

# Configuration
AWS_REGION="us-east-1"
AWS_ACCOUNT_ID="893214465464"
ECR_REPOSITORY_NAME="cpi"
IMAGE_TAG=${1:-latest}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 CCDI CPI ETL Prefect Deployment with ECR${NC}"
echo -e "${YELLOW}======================================${NC}"

# Function to print status
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check prerequisites
print_status "Checking prerequisites..."

if ! command -v aws &> /dev/null; then
    print_error "AWS CLI is not installed"
    exit 1
fi

if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed"
    exit 1
fi

if ! command -v prefect &> /dev/null; then
    print_error "Prefect is not installed"
    exit 1
fi

# Check AWS credentials
print_status "Using pre-configured AWS Account ID: ${AWS_ACCOUNT_ID}"
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

print_success "Prerequisites check passed"
print_status "AWS Account ID: ${AWS_ACCOUNT_ID}"
print_status "ECR Registry: ${ECR_REGISTRY}"

# Step 3: Repository should already exist, just verify
print_status "Verifying ECR repository exists..."
if aws ecr describe-repositories --repository-names ${ECR_REPOSITORY_NAME} --region ${AWS_REGION} > /dev/null 2>&1; then
    print_success "ECR repository 'cpi' exists and is accessible"
else
    print_error "ECR repository 'cpi' not found or not accessible"
    print_error "Please ensure the repository exists and you have proper permissions"
    exit 1
fi

# Step 2: Login to ECR
print_status "Logging in to ECR..."
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_REGISTRY} > /dev/null 2>&1
print_success "Successfully logged in to ECR"

# Step 3: Set environment variable for Prefect
export AWS_ACCOUNT_ID=${AWS_ACCOUNT_ID}
print_status "Set AWS_ACCOUNT_ID environment variable for Prefect"

# Step 4: Install prefect-docker if not already installed
print_status "Checking prefect-docker installation..."
if ! python -c "import prefect_docker" 2>/dev/null; then
    print_status "Installing prefect-docker..."
    pip install prefect-docker>=0.3.0
    print_success "prefect-docker installed"
else
    print_success "prefect-docker already installed"
fi

# Step 5: Change to config directory and deploy
print_status "Changing to config directory..."
cd config

print_status "Deploying flows to Prefect..."
print_status "This will build the Docker image, push to ECR, and deploy both flows"

# Deploy with automatic answers to prompts
prefect deploy --all

if [ $? -eq 0 ]; then
    print_success "🎉 Deployment completed successfully!"
    echo
    print_status "📋 Deployed flows:"
    echo -e "  ${GREEN}•${NC} etl-pipeline (Flow: etl)"
    echo -e "  ${GREEN}•${NC} database-backup (Flow: db-backup)"
    echo
    print_status "🐳 Docker image pushed to:"
    echo -e "  ${BLUE}${ECR_REGISTRY}/${ECR_REPOSITORY_NAME}:${IMAGE_TAG}${NC}"
    echo
    print_status "🌐 Check your Prefect UI to see the deployed flows"
    print_status "Both flows will appear as dropdown options when creating flow runs"
else
    print_error "Deployment failed"
    exit 1
fi
