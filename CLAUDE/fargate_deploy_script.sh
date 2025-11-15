#!/bin/bash

##############################################################################
# AWS Fargate Deployment Script for Flag & Pennant Trading System
##############################################################################

set -e

echo "===================================================="
echo "Flag & Pennant Trading System - Fargate Deployment"
echo "===================================================="

# Configuration
REGION="us-east-1"
CLUSTER_NAME="flag-pennant-cluster"
SERVICE_NAME="flag-pennant-service"
TASK_FAMILY="flag-pennant-trading"
ECR_REPO_NAME="flag-pennant-trading"
CONTAINER_NAME="trading-container"
LOG_GROUP="/ecs/flag-pennant-trading"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check prerequisites
echo -e "\n${YELLOW}Checking prerequisites...${NC}"

if ! command -v aws &> /dev/null; then
    echo -e "${RED}Error: AWS CLI not installed${NC}"
    exit 1
fi

if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker not installed${NC}"
    exit 1
fi

# Get AWS account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo -e "${GREEN}✓ AWS Account ID: $AWS_ACCOUNT_ID${NC}"

ECR_URI="$AWS_ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"
IMAGE_URI="$ECR_URI/$ECR_REPO_NAME:latest"

# Check credentials
if [ -z "$ANGEL_API_KEY" ] || [ -z "$ANGEL_CLIENT_ID" ] || [ -z "$ANGEL_PASSWORD" ] || [ -z "$ANGEL_TOTP_SECRET" ]; then
    echo -e "${YELLOW}⚠ Warning: Angel One credentials not set${NC}"
    echo "Set these environment variables before running:"
    echo "  export ANGEL_API_KEY='your_key'"
    echo "  export ANGEL_CLIENT_ID='your_id'"
    echo "  export ANGEL_PASSWORD='your_password'"
    echo "  export ANGEL_TOTP_SECRET='your_secret'"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Step 1: Create ECR repository
echo -e "\n${YELLOW}Step 1: Setting up ECR repository...${NC}"

REPO_EXISTS=$(aws ecr describe-repositories --repository-names $ECR_REPO_NAME --region $REGION 2>&1 | grep -c "RepositoryNotFoundException" || true)

if [ "$REPO_EXISTS" -eq 1 ]; then
    echo "Creating ECR repository: $ECR_REPO_NAME"
    aws ecr create-repository \
        --repository-name $ECR_REPO_NAME \
        --region $REGION
else
    echo "ECR repository already exists: $ECR_REPO_NAME"
fi

echo -e "${GREEN}✓ ECR repository ready${NC}"

# Step 2: Build Docker image
echo -e "\n${YELLOW}Step 2: Building Docker image...${NC}"

docker build -t $ECR_REPO_NAME:latest .

echo -e "${GREEN}✓ Docker image built${NC}"

# Step 3: Push to ECR
echo -e "\n${YELLOW}Step 3: Pushing image to ECR...${NC}"

# Login to ECR
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ECR_URI

# Tag image
docker tag $ECR_REPO_NAME:latest $IMAGE_URI

# Push image
docker push $IMAGE_URI

echo -e "${GREEN}✓ Image pushed to ECR: $IMAGE_URI${NC}"

# Step 4: Create CloudWatch log group
echo -e "\n${YELLOW}Step 4: Setting up CloudWatch logs...${NC}"

LOG_GROUP_EXISTS=$(aws logs describe-log-groups --log-group-name-prefix $LOG_GROUP --region $REGION 2>&1 | grep -c "$LOG_GROUP" || true)

if [ "$LOG_GROUP_EXISTS" -eq 0 ]; then
    echo "Creating CloudWatch log group: $LOG_GROUP"
    aws logs create-log-group --log-group-name $LOG_GROUP --region $REGION
else
    echo "Log group already exists: $LOG_GROUP"
fi

echo -e "${GREEN}✓ CloudWatch logs configured${NC}"

# Step 5: Create IAM roles
echo -e "\n${YELLOW}Step 5: Setting up IAM roles...${NC}"

# Execution role (for ECS to pull image and write logs)
EXECUTION_ROLE_NAME="ecsTaskExecutionRole"
EXECUTION_ROLE_ARN="arn:aws:iam::$AWS_ACCOUNT_ID:role/$EXECUTION_ROLE_NAME"

EXECUTION_ROLE_EXISTS=$(aws iam get-role --role-name $EXECUTION_ROLE_NAME 2>&1 | grep -c "NoSuchEntity" || true)

if [ "$EXECUTION_ROLE_EXISTS" -gt 0 ]; then
    echo "Creating execution role: $EXECUTION_ROLE_NAME"
    
    cat > trust-policy-ecs.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

    aws iam create-role \
        --role-name $EXECUTION_ROLE_NAME \
        --assume-role-policy-document file://trust-policy-ecs.json
    
    aws iam attach-role-policy \
        --role-name $EXECUTION_ROLE_NAME \
        --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
    
    rm trust-policy-ecs.json
    
    echo "Waiting for IAM role to propagate..."
    sleep 10
fi

# EventBridge role (to run scheduled tasks)
EVENTS_ROLE_NAME="ecsEventsRole"
EVENTS_ROLE_ARN="arn:aws:iam::$AWS_ACCOUNT_ID:role/$EVENTS_ROLE_NAME"

EVENTS_ROLE_EXISTS=$(aws iam get-role --role-name $EVENTS_ROLE_NAME 2>&1 | grep -c "NoSuchEntity" || true)

if [ "$EVENTS_ROLE_EXISTS" -gt 0 ]; then
    echo "Creating EventBridge role: $EVENTS_ROLE_NAME"
    
    cat > trust-policy-events.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "events.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

    aws iam create-role \
        --role-name $EVENTS_ROLE_NAME \
        --assume-role-policy-document file://trust-policy-events.json
    
    cat > events-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecs:RunTask"
      ],
      "Resource": "*",
      "Condition": {
        "ArnLike": {
          "ecs:cluster": "arn:aws:ecs:$REGION:$AWS_ACCOUNT_ID:cluster/$CLUSTER_NAME"
        }
      }
    },
    {
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "*"
    }
  ]
}
EOF

    aws iam put-role-policy \
        --role-name $EVENTS_ROLE_NAME \
        --policy-name ECSEventsPolicy \
        --policy-document file://events-policy.json
    
    rm trust-policy-events.json events-policy.json
fi

echo -e "${GREEN}✓ IAM roles configured${NC}"

# Step 6: Create ECS cluster
echo -e "\n${YELLOW}Step 6: Setting up ECS cluster...${NC}"

CLUSTER_EXISTS=$(aws ecs describe-clusters --clusters $CLUSTER_NAME --region $REGION 2>&1 | grep -c "ACTIVE" || true)

if [ "$CLUSTER_EXISTS" -eq 0 ]; then
    echo "Creating ECS cluster: $CLUSTER_NAME"
    aws ecs create-cluster --cluster-name $CLUSTER_NAME --region $REGION
else
    echo "ECS cluster already exists: $CLUSTER_NAME"
fi

echo -e "${GREEN}✓ ECS cluster ready${NC}"

# Step 7: Register task definition
echo -e "\n${YELLOW}Step 7: Registering task definition...${NC}"

cat > task-definition.json << EOF
{
  "family": "$TASK_FAMILY",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "$EXECUTION_ROLE_ARN",
  "taskRoleArn": "$EXECUTION_ROLE_ARN",
  "containerDefinitions": [
    {
      "name": "$CONTAINER_NAME",
      "image": "$IMAGE_URI",
      "essential": true,
      "environment": [
        {"name": "ANGEL_API_KEY", "value": "${ANGEL_API_KEY:-your_api_key}"},
        {"name": "ANGEL_CLIENT_ID", "value": "${ANGEL_CLIENT_ID:-your_client_id}"},
        {"name": "ANGEL_PASSWORD", "value": "${ANGEL_PASSWORD:-your_password}"},
        {"name": "ANGEL_TOTP_SECRET", "value": "${ANGEL_TOTP_SECRET:-your_totp_secret}"},
        {"name": "DRY_RUN", "value": "true"}
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "$LOG_GROUP",
          "awslogs-region": "$REGION",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
EOF

aws ecs register-task-definition \
    --cli-input-json file://task-definition.json \
    --region $REGION

TASK_DEF_ARN=$(aws ecs describe-task-definition --task-definition $TASK_FAMILY --region $REGION --query 'taskDefinition.taskDefinitionArn' --output text)

echo -e "${GREEN}✓ Task definition registered: $TASK_DEF_ARN${NC}"

rm task-definition.json

# Step 8: Set up scheduled task
echo -e "\n${YELLOW}Step 8: Setting up scheduled execution...${NC}"

RULE_NAME="flag-pennant-fargate-daily"
SCHEDULE="cron(0 4 * * ? *)"  # 9:30 AM IST = 4:00 AM UTC

# Get default VPC and subnet
DEFAULT_VPC=$(aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" --query 'Vpcs[0].VpcId' --output text --region $REGION)
DEFAULT_SUBNET=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$DEFAULT_VPC" --query 'Subnets[0].SubnetId' --output text --region $REGION)
DEFAULT_SG=$(aws ec2 describe-security-groups --filters "Name=vpc-id,Values=$DEFAULT_VPC" "Name=group-name,Values=default" --query 'SecurityGroups[0].GroupId' --output text --region $REGION)

echo "Using VPC: $DEFAULT_VPC"
echo "Using Subnet: $DEFAULT_SUBNET"
echo "Using Security Group: $DEFAULT_SG"

# Create or update EventBridge rule
aws events put-rule \
    --name $RULE_NAME \
    --schedule-expression "$SCHEDULE" \
    --state ENABLED \
    --description "Daily Fargate task at 9:30 AM IST" \
    --region $REGION

# Add ECS task as target
cat > targets.json << EOF
[
  {
    "Id": "1",
    "Arn": "arn:aws:ecs:$REGION:$AWS_ACCOUNT_ID:cluster/$CLUSTER_NAME",
    "RoleArn": "$EVENTS_ROLE_ARN",
    "EcsParameters": {
      "TaskDefinitionArn": "$TASK_DEF_ARN",
      "TaskCount": 1,
      "LaunchType": "FARGATE",
      "NetworkConfiguration": {
        "awsvpcConfiguration": {
          "Subnets": ["$DEFAULT_SUBNET"],
          "SecurityGroups": ["$DEFAULT_SG"],
          "AssignPublicIp": "ENABLED"
        }
      }
    }
  }
]
EOF

aws events put-targets \
    --rule $RULE_NAME \
    --targets file://targets.json \
    --region $REGION

rm targets.json

echo -e "${GREEN}✓ Scheduled task configured (9:30 AM IST daily)${NC}"

# Step 9: Run test task
echo -e "\n${YELLOW}Step 9: Running test task...${NC}"

TASK_ARN=$(aws ecs run-task \
    --cluster $CLUSTER_NAME \
    --task-definition $TASK_FAMILY \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[$DEFAULT_SUBNET],securityGroups=[$DEFAULT_SG],assignPublicIp=ENABLED}" \
    --region $REGION \
    --query 'tasks[0].taskArn' \
    --output text)

echo "Task started: $TASK_ARN"
echo "Waiting for task to complete (this may take a few minutes)..."

# Wait for task to complete
aws ecs wait tasks-stopped \
    --cluster $CLUSTER_NAME \
    --tasks $TASK_ARN \
    --region $REGION

TASK_STATUS=$(aws ecs describe-tasks \
    --cluster $CLUSTER_NAME \
    --tasks $TASK_ARN \
    --region $REGION \
    --query 'tasks[0].lastStatus' \
    --output text)

echo -e "${GREEN}✓ Test task completed with status: $TASK_STATUS${NC}"

# Summary
echo -e "\n===================================================="
echo -e "${GREEN}✓ FARGATE DEPLOYMENT COMPLETE${NC}"
echo "===================================================="
echo ""
echo "Cluster: $CLUSTER_NAME"
echo "Task Definition: $TASK_FAMILY"
echo "Image: $IMAGE_URI"
echo "Region: $REGION"
echo "Schedule: Daily at 9:30 AM IST (4:00 AM UTC)"
echo ""
echo "Next steps:"
echo "  1. View logs: aws logs tail $LOG_GROUP --follow --region $REGION"
echo "  2. Run task manually:"
echo "     aws ecs run-task --cluster $CLUSTER_NAME --task-definition $TASK_FAMILY --launch-type FARGATE \\"
echo "       --network-configuration \"awsvpcConfiguration={subnets=[$DEFAULT_SUBNET],securityGroups=[$DEFAULT_SG],assignPublicIp=ENABLED}\" \\"
echo "       --region $REGION"
echo "  3. Update image: docker build, push to ECR, then run this script again"
echo ""
echo -e "${YELLOW}Remember: Test thoroughly with DRY_RUN=true before live trading!${NC}"
echo "===================================================="
