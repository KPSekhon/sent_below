"""
AWS Integration - S3 Model Storage & DynamoDB Model Registry
=============================================================
Provides helpers for uploading trained model artefacts to Amazon S3
and registering model versions in a DynamoDB table.

Environment variables:
    AWS_REGION              - AWS region (default: ca-central-1)
    MODEL_BUCKET            - S3 bucket for model files
    MODEL_REGISTRY_TABLE    - DynamoDB table name for the model registry
"""

import json
import os
from decimal import Decimal

import boto3


AWS_REGION = os.getenv("AWS_REGION", "ca-central-1")
MODEL_BUCKET = os.getenv("MODEL_BUCKET", "")
MODEL_REGISTRY_TABLE = os.getenv("MODEL_REGISTRY_TABLE", "")

s3_client = boto3.client("s3", region_name=AWS_REGION)
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)


# ---------------------------------------------------------------------------
# S3 helpers
# ---------------------------------------------------------------------------
def upload_file_to_s3(local_path: str, bucket: str, key: str):
    """Upload a local file to S3."""
    s3_client.upload_file(local_path, bucket, key)


def download_file_from_s3(bucket: str, key: str, local_path: str):
    """Download a file from S3 to a local path."""
    os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
    s3_client.download_file(bucket, key, local_path)


# ---------------------------------------------------------------------------
# DynamoDB helpers
# ---------------------------------------------------------------------------
def put_model_registry_item(item: dict):
    """Write a model version record to the DynamoDB registry table."""
    table = dynamodb.Table(MODEL_REGISTRY_TABLE)
    table.put_item(Item=_to_dynamo(item))


def get_latest_model(model_name: str):
    """Query the latest model version by name (sorted descending by version)."""
    table = dynamodb.Table(MODEL_REGISTRY_TABLE)
    response = table.query(
        KeyConditionExpression="model_name = :m",
        ExpressionAttributeValues={":m": model_name},
        ScanIndexForward=False,
        Limit=1,
    )
    items = response.get("Items", [])
    return items[0] if items else None


def _to_dynamo(value):
    """Recursively convert Python floats to Decimal for DynamoDB."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _to_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_dynamo(v) for v in value]
    return value
