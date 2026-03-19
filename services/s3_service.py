import os
from io import BytesIO

import boto3
from botocore.config import Config

S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", "")
S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "")
S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "")
S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME", "")


def _get_client():
    if not all([S3_ENDPOINT_URL, S3_ACCESS_KEY, S3_SECRET_KEY]):
        raise RuntimeError("S3 credentials are not configured")
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT_URL,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
        config=Config(signature_version="s3v4"),
    )


def s3_key_for_pdf(project_id: str, floor_id: str) -> str:
    return f"projects/{project_id}/floors/{floor_id}/plan.pdf"


def upload_pdf(project_id: str, floor_id: str, file_bytes: bytes) -> str:
    client = _get_client()
    key = s3_key_for_pdf(project_id, floor_id)
    client.put_object(
        Bucket=S3_BUCKET_NAME,
        Key=key,
        Body=file_bytes,
        ContentType="application/pdf",
    )
    return key


def get_presigned_url(key: str, expires_in: int = 3600) -> str:
    client = _get_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": S3_BUCKET_NAME, "Key": key},
        ExpiresIn=expires_in,
    )


def delete_pdf(key: str) -> None:
    client = _get_client()
    client.delete_object(Bucket=S3_BUCKET_NAME, Key=key)
