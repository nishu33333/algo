# AWS Deployment Guide: Flag & Pennant Trading System

## 📁 Project Structure

```
flag-pennant-trading/
├── flag_pennant_trading_system.py    # Main trading system
├── lambda_handler.py                 # AWS Lambda handler
├── fargate_runner.py                 # AWS Fargate runner
├── requirements.txt                  # Python dependencies
├── Dockerfile                        # Container definition
├── .env.example                      # Environment variables template
├── tests/                           # Unit tests
│   ├── test_patterns.py
│   └── test_filters.py
└── deployment/
    ├── lambda_deploy.sh             # Lambda deployment script
    ├── fargate_deploy.sh            # Fargate deployment script
    └── cloudformation/
        ├── lambda_template.yaml     # CloudFormation for Lambda
        └── fargate_template.yaml    # CloudFormation for Fargate
```

---

## 🔐 Prerequisites

### 1. Angel One Account Setup
- Create Angel One account at https://smartapi.angelbroking.com/
- Generate API credentials:
  - API Key
  - Client ID
  - Password
  - TOTP Secret (for 2FA)

### 2. AWS Account Setup
- AWS Account with appropriate permissions
- AWS CLI installed and configured
- Docker installed (for Fargate deployment)

### 3. Install Local Dependencies
```bash
pip install -r requirements.txt
```

---

## 🚀 Deployment Option 1: AWS Lambda (Serverless)

### Step 1: Create Lambda Deployment Package

```bash
# Create deployment directory
mkdir lambda_package
cd lambda_package

# Copy application files
cp ../flag_pennant_trading_system.py .
cp ../lambda_handler.py .
cp ../requirements.txt .

# Install dependencies
pip install -r requirements.txt -t .

# Create deployment package
zip -r ../lambda_deployment.zip .
```

### Step 2: Create Lambda Function via AWS CLI

```bash
# Create IAM role for Lambda
aws iam create-role \
  --role-name FlagPennantTradingLambdaRole \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "lambda.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }'

# Attach basic execution policy
aws iam attach-role-policy \
  --role-name FlagPennantTradingLambdaRole \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

# Create Lambda function
aws lambda create-function \
  --function-name flag-pennant-trading \
  --runtime python3.10 \
  --role arn:aws:iam::YOUR_ACCOUNT_ID:role/FlagPennantTradingLambdaRole \
  --handler lambda_handler.lambda_handler \
  --zip-file fileb://lambda_deployment.zip \
  --timeout 300 \
  --memory-size 512 \
  --environment Variables="{
    ANGEL_API_KEY=your_api_key,
    ANGEL_CLIENT_ID=your_client_id,
    ANGEL_PASSWORD=your_password,
    ANGEL_TOTP_SECRET=your_totp_secret
  }"
```

### Step 3: Set Up CloudWatch Events for Scheduling

```bash
# Create EventBridge rule to run daily at 9:30 AM IST (4:00 AM UTC)
aws events put-rule \
  --name flag-pennant-daily-scan \
  --schedule-expression "cron(0 4 * * ? *)" \
  --description "Daily scan for flag and pennant patterns"

# Add Lambda as target
aws events put-targets \
  --rule flag-pennant-daily-scan \
  --targets "Id"="1","Arn"="arn:aws:lambda:REGION:ACCOUNT_ID:function:flag-pennant-trading"

# Grant EventBridge permission to invoke Lambda
aws lambda add-permission \
  --function-name flag-pennant-trading \
  --statement-id flag-pennant-daily-scan \
  --action lambda:InvokeFunction \
  --principal events.amazonaws.com \
  --source-arn arn:aws:events:REGION:ACCOUNT_ID:rule/flag-pennant-daily-scan
```

### Step 4: Test Lambda Function

```bash
# Create test event
cat > test_event.json << EOF
{
  "watchlist": [
    {"symbol": "RELIANCE", "token": "2885"},
    {"symbol": "TCS", "token": "11536"}
  ],
  "dry_run": true
}
EOF

# Invoke Lambda
aws lambda invoke \
  --function-name flag-pennant-trading \
  --payload file://test_event.json \
  --cli-binary-format raw-in-base64-out \
  response.json

# View response
cat response.json
```

### Lambda Environment Variables

Set via AWS Console or CLI:
```
ANGEL_API_KEY=your_api_key_here
ANGEL_CLIENT_ID=your_client_id_here
ANGEL_PASSWORD=your_password_here
ANGEL_TOTP_SECRET=your_totp_secret_here
```

---

## 🐳 Deployment Option 2: AWS Fargate (Containerized)

### Step 1: Build and Push Docker Image

```bash
# Login to AWS ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

# Create ECR repository
aws ecr create-repository --repository-name flag-pennant-trading

# Build Docker image
docker build -t flag-pennant-trading .

# Tag image
docker tag flag-pennant-trading:latest YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/flag-pennant-trading:latest

# Push to ECR
docker push YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/flag-pennant-trading:latest
```

### Step 2: Create ECS Task Definition

```bash
# Create task definition JSON
cat > task-definition.json << EOF
{
  "family": "flag-pennant-trading",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "containerDefinitions": [
    {
      "name": "trading-container",
      "image": "YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/flag-pennant-trading:latest",
      "environment": [
        {"name": "ANGEL_API_KEY", "value": "your_api_key"},
        {"name": "ANGEL_CLIENT_ID", "value": "your_client_id"},
        {"name": "ANGEL_PASSWORD", "value": "your_password"},
        {"name": "ANGEL_TOTP_SECRET", "value": "your_totp_secret"},
        {"name": "DRY_RUN", "value": "true"}
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/flag-pennant-trading",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ],
  "executionRoleArn": "arn:aws:iam::YOUR_ACCOUNT_ID:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::YOUR_ACCOUNT_ID:role/ecsTaskExecutionRole"
}
EOF

# Register task definition
aws ecs register-task-definition --cli-input-json file://task-definition.json
```

### Step 3: Create ECS Cluster

```bash
# Create cluster
aws ecs create-cluster --cluster-name flag-pennant-cluster

# Create CloudWatch log group
aws logs create-log-group --log-group-name /ecs/flag-pennant-trading
```

### Step 4: Set Up Scheduled Task

```bash
# Create EventBridge rule
aws events put-rule \
  --name flag-pennant-fargate-daily \
  --schedule-expression "cron(0 4 * * ? *)" \
  --description "Daily Fargate task for trading system"

# Create ECS task target
aws events put-targets \
  --rule flag-pennant-fargate-daily \
  --targets '[
    {
      "Id": "1",
      "Arn": "arn:aws:ecs:us-east-1:YOUR_ACCOUNT_ID:cluster/flag-pennant-cluster",
      "RoleArn": "arn:aws:iam::YOUR_ACCOUNT_ID:role/ecsEventsRole",
      "EcsParameters": {
        "TaskDefinitionArn": "arn:aws:ecs:us-east-1:YOUR_ACCOUNT_ID:task-definition/flag-pennant-trading:1",
        "TaskCount": 1,
        "LaunchType": "FARGATE",
        "NetworkConfiguration": {
          "awsvpcConfiguration": {
            "Subnets": ["subnet-xxxxx"],
            "SecurityGroups": ["sg-xxxxx"],
            "AssignPublicIp": "ENABLED"
          }
        }
      }
    }
  ]'
```

### Step 5: Run Task Manually (for testing)

```bash
aws ecs run-task \
  --cluster flag-pennant-cluster \
  --task-definition flag-pennant-trading:1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxxxx],securityGroups=[sg-xxxxx],assignPublicIp=ENABLED}"
```

---

## 📊 Monitoring and Logging

### CloudWatch Logs

**Lambda:**
- Log group: `/aws/lambda/flag-pennant-trading`
- View logs:
```bash
aws logs tail /aws/lambda/flag-pennant-trading --follow
```

**Fargate:**
- Log group: `/ecs/flag-pennant-trading`
- View logs:
```bash
aws logs tail /ecs/flag-pennant-trading --follow
```

### CloudWatch Alarms

```bash
# Create alarm for Lambda errors
aws cloudwatch put-metric-alarm \
  --alarm-name flag-pennant-lambda-errors \
  --alarm-description "Alert on Lambda function errors" \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --statistic Sum \
  --period 300 \
  --evaluation-periods 1 \
  --threshold 1 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=FunctionName,Value=flag-pennant-trading
```

---

## 🔒 Security Best Practices

### 1. Use AWS Secrets Manager (Recommended)

Instead of environment variables, store credentials in Secrets Manager:

```bash
# Store Angel One credentials
aws secretsmanager create-secret \
  --name angel-one-credentials \
  --secret-string '{
    "api_key": "your_api_key",
    "client_id": "your_client_id",
    "password": "your_password",
    "totp_secret": "your_totp_secret"
  }'

# Update IAM role to allow access
aws iam put-role-policy \
  --role-name FlagPennantTradingLambdaRole \
  --policy-name SecretsManagerAccess \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": ["secretsmanager:GetSecretValue"],
      "Resource": "arn:aws:secretsmanager:REGION:ACCOUNT_ID:secret:angel-one-credentials-*"
    }]
  }'
```

Modify code to fetch from Secrets Manager:
```python
import boto3
import json

def get_credentials():
    client = boto3.client('secretsmanager')
    response = client.get_secret_value(SecretId='angel-one-credentials')
    return json.loads(response['SecretString'])
```

### 2. Use VPC for Fargate Tasks

Place Fargate tasks in private subnets with NAT Gateway for outbound access.

### 3. Enable CloudTrail

Monitor all API calls for auditing:
```bash
aws cloudtrail create-trail \
  --name flag-pennant-trail \
  --s3-bucket-name your-cloudtrail-bucket
```

---

## 📈 Scaling Considerations

### Lambda Concurrent Executions
- Default: 1000 concurrent executions per region
- Request increase if needed via AWS Support

### Fargate Task Limits
- Default: 500 tasks per cluster
- Adjust based on watchlist size

### Cost Optimization
- Lambda: Free tier includes 1M requests/month
- Fargate: ~$0.04/hour for 0.5 vCPU, 1GB memory
- Consider Reserved Capacity for Fargate if running 24/7

---

## 🧪 Testing

### Local Testing

```bash
# Set environment variables
export ANGEL_API_KEY="your_key"
export ANGEL_CLIENT_ID="your_id"
export ANGEL_PASSWORD="your_password"
export ANGEL_TOTP_SECRET="your_secret"

# Run main script
python flag_pennant_trading_system.py

# Test Lambda handler locally
python lambda_handler.py

# Test Fargate runner locally
python fargate_runner.py
```

### Docker Testing

```bash
# Build image
docker build -t flag-pennant-trading .

# Run container with environment variables
docker run -e ANGEL_API_KEY="your_key" \
           -e ANGEL_CLIENT_ID="your_id" \
           -e ANGEL_PASSWORD="your_password" \
           -e ANGEL_TOTP_SECRET="your_secret" \
           -e DRY_RUN="true" \
           flag-pennant-trading
```

---

## 🔄 CI/CD Pipeline (GitHub Actions Example)

```yaml
# .github/workflows/deploy.yml
name: Deploy to AWS

on:
  push:
    branches: [main]

jobs:
  deploy-lambda:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.10'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt -t package/
          cp *.py package/
      
      - name: Package Lambda
        run: |
          cd package
          zip -r ../lambda.zip .
      
      - name: Deploy to Lambda
        run: |
          aws lambda update-function-code \
            --function-name flag-pennant-trading \
            --zip-file fileb://lambda.zip
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          AWS_DEFAULT_REGION: us-east-1
```

---

## 📞 Support and Troubleshooting

### Common Issues

**1. Login Failures**
- Verify TOTP secret is correct
- Check if 2FA is enabled on Angel One account
- Ensure system time is synchronized

**2. Historical Data Issues**
- Verify symbol tokens are correct
- Check Angel One API rate limits
- Ensure sufficient historical data available

**3. Lambda Timeout**
- Increase timeout (max 15 minutes)
- Reduce watchlist size per invocation
- Consider parallel processing

**4. Fargate Task Failures**
- Check CloudWatch logs
- Verify network connectivity
- Ensure sufficient memory allocation

### Debug Mode

Enable verbose logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

---

## 📜 License and Disclaimer

**IMPORTANT DISCLAIMER:**
- This trading system is for educational purposes only
- Past performance does not guarantee future results
- Always test in dry-run mode before live trading
- Use proper risk management
- Consult with financial advisors before making investment decisions

---

## 🎯 Next Steps

1. ✅ Test locally with dry_run=True
2. ✅ Deploy to AWS Lambda or Fargate
3. ✅ Monitor for 1-2 weeks in dry-run mode
4. ✅ Analyze signals and adjust parameters
5. ⚠️ Switch to live trading only after thorough testing
6. 📊 Set up alerting and monitoring
7. 🔄 Continuously optimize and refine strategy

---

**Happy Trading! 🚀📈**
