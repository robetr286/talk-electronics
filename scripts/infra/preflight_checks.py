#!/usr/bin/env python3
"""Preflight checks for DigitalOcean Spaces and environment.

Checks performed:
 - required env vars
 - endpoint reachability (list_buckets)
 - optional: provided buckets accessible
 - optional: versioning enabled (`--check-versioning`)
 - optional: test upload (`--test-upload`) to verify ACL/perm

Exit codes:
 0  success
 1  one or more checks failed
"""
import argparse
import os
import sys

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError


def check_env():
    missing = []
    if not (os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("SPACES_KEY")):
        missing.append("AWS_ACCESS_KEY_ID / SPACES_KEY")
    if not (os.environ.get("AWS_SECRET_ACCESS_KEY") or os.environ.get("SPACES_SECRET")):
        missing.append("AWS_SECRET_ACCESS_KEY / SPACES_SECRET")
    if not os.environ.get("SPACES_ENDPOINT"):
        missing.append("SPACES_ENDPOINT")

    if missing:
        print("Missing environment variables:")
        for m in missing:
            print(" -", m)
        return False
    return True


def make_client(key, secret, endpoint):
    return boto3.client(
        "s3",
        aws_access_key_id=key,
        aws_secret_access_key=secret,
        endpoint_url=endpoint,
        config=Config(signature_version="s3v4"),
    )


def check_buckets(s3, buckets):
    ok = True
    for b in buckets:
        try:
            s3.head_bucket(Bucket=b)
            print(f"OK: bucket '{b}' exists and is accessible")
        except ClientError as e:
            print(f"FAILED: cannot access bucket '{b}': {e}")
            ok = False
    return ok


def check_versioning(s3, buckets):
    ok = True
    for b in buckets:
        try:
            resp = s3.get_bucket_versioning(Bucket=b)
            status = resp.get("Status")
            if status != "Enabled":
                print(f"WARNING: bucket '{b}' versioning not enabled (Status={status})")
                ok = False
            else:
                print(f"OK: bucket '{b}' versioning enabled")
        except ClientError as e:
            print(f"FAILED: cannot check versioning for '{b}': {e}")
            ok = False
    return ok


def test_upload(s3, bucket):
    key = "preflight_test_object.txt"
    try:
        s3.put_object(Bucket=bucket, Key=key, Body=b"ok")
        s3.delete_object(Bucket=bucket, Key=key)
        print(f"OK: test upload/delete to bucket '{bucket}' succeeded")
        return True
    except ClientError as e:
        print(f"FAILED: test upload to '{bucket}': {e}")
        return False


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--endpoint", required=True)
    p.add_argument("--buckets", nargs="*", default=[])
    p.add_argument("--check-versioning", action="store_true")
    p.add_argument("--test-upload", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="Dry-run: allow invocation without credentials and skip live S3 calls")
    args = p.parse_args()

    if args.dry_run:
        print("Dry-run: no credentials required. Would check endpoint and buckets:", ", ".join(args.buckets))
        print("Exiting (dry-run).")
        sys.exit(0)

    ok = True
    if not check_env():
        ok = False

    key = os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("SPACES_KEY")
    secret = os.environ.get("AWS_SECRET_ACCESS_KEY") or os.environ.get("SPACES_SECRET")

    if not key or not secret:
        print("ERROR: missing keys, aborting further checks")
        sys.exit(1)

    s3 = make_client(key, secret, args.endpoint)

    try:
        print("Listing buckets...")
        resp = s3.list_buckets()
        buckets = [b["Name"] for b in resp.get("Buckets", [])]
        print("Buckets visible to these credentials:")
        for b in buckets:
            print(" -", b)
    except ClientError as e:
        print("ERROR listing buckets:", e)
        print("Check that you are using a S3-style Access Key/Secret from DO Spaces, not an API token.")
        ok = False

    if args.buckets:
        ok = check_buckets(s3, args.buckets) and ok

    if args.check_versioning and args.buckets:
        ok = check_versioning(s3, args.buckets) and ok

    if args.test_upload and args.buckets:
        # do test upload only to first bucket in list
        ok = test_upload(s3, args.buckets[0]) and ok

    if ok:
        print("Preflight checks passed")
        sys.exit(0)
    else:
        print("Preflight checks failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
