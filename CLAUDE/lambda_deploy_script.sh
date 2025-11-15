#!/bin/bash

##############################################################################
# AWS Lambda Deployment Script for Flag & Pennant Trading System
##############################################################################

set -e

echo "=================================================="
echo "Flag & Pennant Trading System - Lambda Deployment"
echo "=================================================="

# Configuration
FUNCTION_NAME="flag-pennant-trading"
RUNTIME="python3.10"
HANDLER="lambda_handler.lambda_handler"
TIMEOUT=300
MEMORY_SIZE=512
ROLE_NAME="FlagPennantTradingLambdaRole"
REGION="us-east-1"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo -e "${RED}Error: AWS CLI is not installed${NC}"
    exit 1
fi

# Check if credentials are set
if [ -z "$ANGEL_API_KEY" ] || [ -z "$ANGEL_CLIENT_ID" ] || [ -z "$ANGEL_PASSWORD" ] || [ -z "$ANGEL_TOTP_SECRET" ]; then
    echo -e "${YELLOW}Warning: Angel One credentials not set in environment${NC}"
    echo "Please set the following environment variables:"
    echo "  - ANGEL_API_KEY"
    echo "  - ANGEL_CLIENT_ID"
    echo "  - ANGEL_PASSWORD"
    echo "  - ANGEL_TOTP_SECRET"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Get AWS account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo -e "${GREEN}AWS Account ID: $AWS_ACCOUNT_ID${NC}"

# Step 1: Create deployment package
echo -e "\n${YELLOW}Step 1: Creating deployment package...${NC}"
rm -rf lambda_package lambda_deployment.zip
mkdir lambda_package

# Copy application files
cp flag_pennant_trading_system.py lambda_package/
cp lambda_handler.py lambda_package/
cp requirements.txt lambda_package/

# Install dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt -t lambda_package/ --quiet

# Create zip file
cd lambda_package
zip -r ../lambda_deployment.zip . -q
cd ..

echo -e "${GREEN}✓ Deployment package created (lambda_deployment.zip)${NC}"

# Step 2: Create or update IAM role
echo -e "\n${YELLOW}Step 2: Setting up IAM role...${NC}"

ROLE_EXISTS=$(aws iam get-role --role-name $ROLE_NAME 2>&1 | grep -c "NoSuchEntity" || true)

if [ "$ROLE_EXISTS" -eq 0 ]; then
    echo "Role $ROLE_NAME already exists"
else
    echo "Creating IAM role: $ROLE_NAME"
    
    cat > trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

    aws iam create-role \
        --role-name $ROLE_NAME \
        --assume-role-policy-document file://trust-policy.json \
        --description "Role for Flag & Pennant Trading Lambda"
    
    # Attach basic execution policy
    aws iam attach-role-policy \
        --role-name $ROLE_NAME \
        --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
    
    echo "Waiting 10 seconds for IAM role to propagate..."
    sleep 10
    
    rm trust-policy.json
fi

ROLE_ARN="arn:aws:iam::$AWS_ACCOUNT_ID:role/$ROLE_NAME"
echo -e "${GREEN}✓ IAM role ready: $ROLE_ARN${NC}"

# Step 3: Create or update Lambda function
echo -e "\n${YELLOW}Step 3: Deploying Lambda function...${NC}"

FUNCTION_EXISTS=$(aws lambda get-function --function-name $FUNCTION_NAME 2>&1 | grep -c "ResourceNotFoundException" || true)

if [ "$FUNCTION_EXISTS" -eq 0 ]; then
    echo "Updating existing Lambda function: $FUNCTION_NAME"
    
    aws lambda update-function-code \
        --function-name $FUNCTION_NAME \
        --zip-file fileb://lambda_deployment.zip \
        --region $REGION
    
    # Update configuration
    aws lambda update-function-configuration \
        --function-name $FUNCTION_NAME \
        --timeout $TIMEOUT \
        --memory-size $MEMORY_SIZE \
        --region $REGION
    
else
    echo "Creating new Lambda function: $FUNCTION_NAME"
    
    aws lambda create-function \
        --function-name $FUNCTION_NAME \
        --runtime $RUNTIME \
        --role $ROLE_ARN \
        --handler $HANDLER \
        --zip-file fileb://lambda_deployment.zip \
        --timeout $TIMEOUT \
        --memory-size $MEMORY_SIZE \
        --region $REGION \
        --description "Flag & Pennant swing trading system"
fi

echo -e "${GREEN}✓ Lambda function deployed${NC}"

# Step 4: Set environment variables
echo -e "\n${YELLOW}Step 4: Setting environment variables...${NC}"

if [ -n "$ANGEL_API_KEY" ]; then
    aws lambda update-function-configuration \
        --function-name $FUNCTION_NAME \
        --environment "Variables={
            ANGEL_API_KEY=$ANGEL_API_KEY,
            ANGEL_CLIENT_ID=$ANGEL_CLIENT_ID,
            ANGEL_PASSWORD=$ANGEL_PASSWORD,
            ANGEL_TOTP_SECRET=$ANGEL_TOTP_SECRET
        }" \
        --region $REGION > /dev/null
    
    echo -e "${GREEN}✓ Environment variables set${NC}"
else
    echo -e "${YELLOW}⚠ Skipping environment variables (credentials not provided)${NC}"
    echo "You can set them manually via AWS Console or CLI"
fi

# Step 5: Create EventBridge rule for scheduling
echo -e "\n${YELLOW}Step 5: Setting up scheduled execution...${NC}"

RULE_NAME="flag-pennant-daily-scan"
SCHEDULE="cron(0 4 * * ? *)"  # 9:30 AM IST = 4:00 AM UTC

# Check if rule exists
RULE_EXISTS=$(aws events describe-rule --name $RULE_NAME 2>&1 | grep -c "ResourceNotFoundException" || true)

if [ "$RULE_EXISTS" -eq 0 ]; then
    echo "Updating EventBridge rule: $RULE_NAME"
    aws events put-rule \
        --name $RULE_NAME \
        --schedule-expression "$SCHEDULE" \
        --state ENABLED \
        --description "Daily scan at 9:30 AM IST" \
        --region $REGION
else
    echo "Creating EventBridge rule: $RULE_NAME"
    aws events put-rule \
        --name $RULE_NAME \
        --schedule-expression "$SCHEDULE" \
        --state ENABLED \
        --description "Daily scan at 9:30 AM IST" \
        --region $REGION
fi

# Add Lambda as target
LAMBDA_ARN="arn:aws:lambda:$REGION:$AWS_ACCOUNT_ID:function:$FUNCTION_NAME"

aws events put-targets \
    --rule $RULE_NAME \
    --targets "Id=1,Arn=$LAMBDA_ARN" \
    --region $REGION

# Grant EventBridge permission to invoke Lambda
aws lambda add-permission \
    --function-name $FUNCTION_NAME \
    --statement-id $RULE_NAME \
    --action lambda:InvokeFunction \
    --principal events.amazonaws.com \
    --source-arn "arn:aws:events:$REGION:$AWS_ACCOUNT_ID:rule/$RULE_NAME" \
    --region $REGION 2>/dev/null || echo "Permission already exists"

echo -e "${GREEN}✓ Scheduled execution configured (9:30 AM IST daily)${NC}"

# Step 6: Test invocation
echo -e "\n${YELLOW}Step 6: Testing Lambda function...${NC}"

cat > test_event.json << EOF
{
  "watchlist": [
    {"symbol": "RELIANCE", "token": "2885"},
    {"symbol": "TCS", "token": "11536"}
  ],
  "dry_run": true
}
EOF

echo "Invoking Lambda with test event..."
aws lambda invoke \
    --function-name $FUNCTION_NAME \
    --payload file://test_event.json \
    --cli-binary-format raw-in-base64-out \
    --region $REGION \
    response.json > /dev/null

if [ -f response.json ]; then
    echo -e "${GREEN}✓ Lambda invoked successfully${NC}"
    echo -e "\n${YELLOW}Response:${NC}"
    cat response.json | python -m json.tool
    rm response.json test_event.json
else
    echo -e "${RED}✗ Lambda invocation failed${NC}"
fi

# Cleanup
echo -e "\n${YELLOW}Cleaning up...${NC}"
rm -rf lambda_package lambda_deployment.zip

# Summary
echo -e "\n=================================================="
echo -e "${GREEN}✓ DEPLOYMENT COMPLETE${NC}"
echo "=================================================="
echo ""
echo "Lambda Function: $FUNCTION_NAME"
echo "Region: $REGION"
echo "Schedule: Daily at 9:30 AM IST (4:00 AM UTC)"
echo ""
echo "Next steps:"
echo "  1. View logs: aws logs tail /aws/lambda/$FUNCTION_NAME --follow"
echo "  2. Invoke manually: aws lambda invoke --function-name $FUNCTION_NAME response.json"
echo "  3. Update code: Run this script again"
echo ""
echo -e "${YELLOW}Remember: Test thoroughly in dry_run mode before live trading!${NC}"
echo "=================================================="
