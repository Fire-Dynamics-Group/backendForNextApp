"""Tests for S3 service using moto mock."""
import boto3
import pytest
from moto import mock_aws

MOCK_BUCKET = "test-bucket"


def _patch_s3_module(s3_mod):
    """Replace _get_client and bucket name so moto intercepts everything."""
    original_client = s3_mod._get_client
    original_bucket = s3_mod.S3_BUCKET_NAME
    s3_mod._get_client = lambda: boto3.client("s3", region_name="us-east-1")
    s3_mod.S3_BUCKET_NAME = MOCK_BUCKET
    return original_client, original_bucket


def _restore_s3_module(s3_mod, original_client, original_bucket):
    s3_mod._get_client = original_client
    s3_mod.S3_BUCKET_NAME = original_bucket


@mock_aws
def test_upload_and_presigned_url():
    conn = boto3.client("s3", region_name="us-east-1")
    conn.create_bucket(Bucket=MOCK_BUCKET)

    import services.s3_service as s3_mod
    orig_client, orig_bucket = _patch_s3_module(s3_mod)

    try:
        key = s3_mod.upload_pdf("proj-123", "floor-456", b"%PDF-fake-content")
        assert key == "projects/proj-123/floors/floor-456/plan.pdf"

        obj = conn.get_object(Bucket=MOCK_BUCKET, Key=key)
        assert obj["Body"].read() == b"%PDF-fake-content"

        url = s3_mod.get_presigned_url(key)
        assert "plan.pdf" in url
    finally:
        _restore_s3_module(s3_mod, orig_client, orig_bucket)


@mock_aws
def test_delete_pdf():
    conn = boto3.client("s3", region_name="us-east-1")
    conn.create_bucket(Bucket=MOCK_BUCKET)
    conn.put_object(Bucket=MOCK_BUCKET, Key="projects/p/floors/f/plan.pdf", Body=b"data")

    import services.s3_service as s3_mod
    orig_client, orig_bucket = _patch_s3_module(s3_mod)

    try:
        s3_mod.delete_pdf("projects/p/floors/f/plan.pdf")
        with pytest.raises(Exception):
            conn.get_object(Bucket=MOCK_BUCKET, Key="projects/p/floors/f/plan.pdf")
    finally:
        _restore_s3_module(s3_mod, orig_client, orig_bucket)


# --- storage_available: the read-only probe behind /health -------------------
# The mobile app's bucket went down while its API kept answering 200. This is
# the check that lets /health see that failure, so it must never create or
# mutate anything - a probe that repairs the fault it is meant to report is
# worse than no probe.


@mock_aws
def test_storage_available_true_when_bucket_reachable():
    conn = boto3.client("s3", region_name="us-east-1")
    conn.create_bucket(Bucket=MOCK_BUCKET)

    import services.s3_service as s3_mod
    orig_client, orig_bucket = _patch_s3_module(s3_mod)

    try:
        assert s3_mod.storage_available() is True
    finally:
        _restore_s3_module(s3_mod, orig_client, orig_bucket)


@mock_aws
def test_storage_available_false_when_bucket_missing_and_does_not_create_it():
    conn = boto3.client("s3", region_name="us-east-1")

    import services.s3_service as s3_mod
    orig_client, orig_bucket = _patch_s3_module(s3_mod)

    try:
        assert s3_mod.storage_available() is False
        buckets = [b["Name"] for b in conn.list_buckets()["Buckets"]]
        assert MOCK_BUCKET not in buckets, "the probe must not create the bucket"
    finally:
        _restore_s3_module(s3_mod, orig_client, orig_bucket)


def test_storage_available_false_when_credentials_are_unconfigured():
    """_get_client raises when env vars are missing; that is 'not available',
    not a 500 on the health endpoint."""
    import services.s3_service as s3_mod

    original = s3_mod._get_client

    def boom():
        raise RuntimeError("S3 credentials are not configured")

    s3_mod._get_client = boom
    try:
        assert s3_mod.storage_available() is False
    finally:
        s3_mod._get_client = original
