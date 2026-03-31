"""
DynamoDB Table Setup - Model Registry
======================================
Creates the DynamoDB table used as a lightweight model registry.
Run once per AWS account/region to initialise the table.

Usage:
    python deploy/setup_dynamodb.py

Environment variables:
    AWS_REGION              - AWS region (default: ca-central-1)
    MODEL_REGISTRY_TABLE    - Table name (default: AdaptiveDungeonModelRegistry)
"""

import os

import boto3

region = os.getenv("AWS_REGION", "ca-central-1")
dynamodb = boto3.client("dynamodb", region_name=region)

table_name = os.getenv("MODEL_REGISTRY_TABLE", "AdaptiveDungeonModelRegistry")

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
