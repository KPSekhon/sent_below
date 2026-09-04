"""
DynamoDB Table Setup - Model Registry
======================================
Creates the DynamoDB table used as a lightweight model registry.
Run once per AWS account/region to initialise the table.

The registry indexes model artefacts that live in S3. S3 stores the bytes
under an immutable, timestamped prefix; this table answers "what is the newest
version and how did it score" without listing the bucket or downloading
checkpoints to read their metrics.

Schema:
    model_name  (HASH)   Partition key, e.g. "enemy-brain"
    version     (RANGE)  Sort key, a UTC timestamp string. Sorting descending
                         and taking one row yields the newest version.

Usage:
    python deploy/setup_dynamodb.py

Environment variables:
    AWS_REGION              - AWS region (default: ca-central-1)
    MODEL_REGISTRY_TABLE    - Table name (default: AdaptiveDungeonModelRegistry)
"""

import os
import sys

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

region = os.getenv("AWS_REGION", "ca-central-1")
table_name = os.getenv("MODEL_REGISTRY_TABLE", "AdaptiveDungeonModelRegistry")

dynamodb = boto3.client("dynamodb", region_name=region)

print(f"Region:  {region}")
print(f"Table:   {table_name}")

try:
    dynamodb.create_table(
        TableName=table_name,
        KeySchema=[
            {"AttributeName": "model_name", "KeyType": "HASH"},
            {"AttributeName": "version", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "model_name", "AttributeType": "S"},
            {"AttributeName": "version", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    print(f"Created table: {table_name}")

except dynamodb.exceptions.ResourceInUseException:
    print(f"Table already exists: {table_name}")

except NoCredentialsError:
    print(
        "No AWS credentials found. Configure them with `aws configure`, or set\n"
        "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in the environment.",
        file=sys.stderr,
    )
    sys.exit(1)

except ClientError as e:
    print(f"Could not create table: {e}", file=sys.stderr)
    sys.exit(1)

# create_table returns as soon as the request is accepted, while the table is
# still CREATING and not yet writable. Anything that runs straight afterwards
# (such as the first training upload) would fail against it, so wait here.
print("Waiting for the table to become ACTIVE...")
try:
    dynamodb.get_waiter("table_exists").wait(
        TableName=table_name,
        WaiterConfig={"Delay": 2, "MaxAttempts": 30},
    )
except ClientError as e:
    print(f"Table did not become active: {e}", file=sys.stderr)
    sys.exit(1)

description = dynamodb.describe_table(TableName=table_name)["Table"]
print(f"Status:  {description['TableStatus']}")
print(f"Keys:    {', '.join(k['AttributeName'] for k in description['KeySchema'])}")
print(f"ARN:     {description['TableArn']}")
