#!/bin/bash

# Configuration
AWS_REGION="us-east-1"
AWS_ACCOUNT_ID="893214465464"
ECR_REPOSITORY_NAME="cpi"
IMAGE_TAG=${1:-latest}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Building and pushing Docker image to ECR...${NC}"

# Check if AWS CLI is configured
if ! aws sts get-caller-identity > /dev/null 2>&1; then
    echo -e "${RED}Error: AWS CLI is not configured or credentials are invalid${NC}"
    exit 1
fi

# Get AWS Account ID
print_status "Using configured AWS Account ID: ${AWS_ACCOUNT_ID}"

ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
FULL_IMAGE_NAME="${ECR_REGISTRY}/${ECR_REPOSITORY_NAME}:${IMAGE_TAG}"

echo -e "${YELLOW}AWS Account ID: ${AWS_ACCOUNT_ID}${NC}"
echo -e "${YELLOW}ECR Registry: ${ECR_REGISTRY}${NC}"
echo -e "${YELLOW}Repository: ${ECR_REPOSITORY_NAME}${NC}"
echo -e "${YELLOW}Image Tag: ${IMAGE_TAG}${NC}"
echo -e "${YELLOW}Full Image Name: ${FULL_IMAGE_NAME}${NC}"

# Create ECR repository if it doesn't exist (repository should already exist)
echo -e "${YELLOW}Verifying ECR repository exists...${NC}"
if ! aws ecr describe-repositories --repository-names ${ECR_REPOSITORY_NAME} --region ${AWS_REGION} > /dev/null 2>&1; then
    echo -e "${RED}ECR repository '${ECR_REPOSITORY_NAME}' not found${NC}"
    echo -e "${RED}Please ensure the repository exists and you have proper permissions${NC}"
    exit 1
else
    echo -e "${GREEN}ECR repository exists and is accessible${NC}"
fi

# Login to ECR
echo -e "${YELLOW}Logging in to ECR...${NC}"
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_REGISTRY}

if [ $? -ne 0 ]; then
    echo -e "${RED}Failed to login to ECR${NC}"
    exit 1
fi

echo -e "${GREEN}Successfully logged in to ECR${NC}"

# Build Docker image
echo -e "${YELLOW}Building Docker image...${NC}"
docker build -t ${ECR_REPOSITORY_NAME}:${IMAGE_TAG} .

if [ $? -ne 0 ]; then
    echo -e "${RED}Failed to build Docker image${NC}"
    exit 1
fi

echo -e "${GREEN}Docker image built successfully${NC}"

# Tag image for ECR
echo -e "${YELLOW}Tagging image for ECR...${NC}"
docker tag ${ECR_REPOSITORY_NAME}:${IMAGE_TAG} ${FULL_IMAGE_NAME}

# Push image to ECR
echo -e "${YELLOW}Pushing image to ECR...${NC}"
docker push ${FULL_IMAGE_NAME}

if [ $? -eq 0 ]; then
    echo -e "${GREEN}Successfully pushed image to ECR!${NC}"
    echo -e "${GREEN}Image URI: ${FULL_IMAGE_NAME}${NC}"
    echo ""
    echo -e "${YELLOW}To pull this image:${NC}"
    echo "docker pull ${FULL_IMAGE_NAME}"
    echo ""
    echo -e "${YELLOW}To run this image:${NC}"
    echo "docker run --rm -e AWS_ACCESS_KEY_ID=\$AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY=\$AWS_SECRET_ACCESS_KEY -e AWS_SESSION_TOKEN=\$AWS_SESSION_TOKEN ${FULL_IMAGE_NAME}"
else
    echo -e "${RED}Failed to push image to ECR${NC}"
    exit 1
fi
