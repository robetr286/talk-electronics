#!/usr/bin/env python3
"""Validate DigitalOcean Spaces credentials and endpoint.

Usage:
  python scripts/infra/check_spaces_creds.py \
    --endpoint https://fra1.digitaloceanspaces.com \
    --buckets talk-electronic-terraform-state \
    talk-electronic-artifacts

It reads `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` from the
environment by default.
"""
import argparse
import os
import sys

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError


def mask(s):
    if not s:
        return None
    if len(s) <= 6:
        return "*" * len(s)
    return s[:3] + "..." + s[-3:]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--endpoint", required=True)
    p.add_argument("--buckets", nargs="*", default=[])
    p.add_argument(
        "--check-versioning", action="store_true", help="Check whether versioning is enabled on provided buckets"
    )
    p.add_argument(
        "--test-upload", action="store_true", help="Perform a temporary upload+delete to verify write access"
    )
    args = p.parse_args()

    key = os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("SPACES_KEY")
    secret = os.environ.get("AWS_SECRET_ACCESS_KEY") or os.environ.get("SPACES_SECRET")

    print("Endpoint:", args.endpoint)
    print("Access Key:", mask(key))
    print("Secret:    ", mask(secret))

    if not key or not secret:
        print("ERROR: Missing credentials in environment.")
        print("Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY (or" " SPACES_KEY/SPACES_SECRET).")
        sys.exit(2)

    s3 = boto3.client(
        "s3",
        aws_access_key_id=key,
        aws_secret_access_key=secret,
        endpoint_url=args.endpoint,
        config=Config(signature_version="s3v4"),
    )

    try:
        print("Listing buckets...")
        resp = s3.list_buckets()
        buckets = [b["Name"] for b in resp.get("Buckets", [])]
        print("Buckets visible to these credentials:")
        for b in buckets:
            print(" -", b)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        print("ERROR listing buckets:", code, e)
        if code in ("InvalidAccessKeyId", "SignatureDoesNotMatch"):
            print("Wygląda na to, że podane poświadczenia nie są kluczem S3/Spaces.")
            print(
                "Upewnij się, że używasz Access Key/Secret z panelu DO -> Spaces ->"
                " Access Keys, a nie Personal Access Token (API token)."
            )
            print("Sprawdź także poprawność zmiennych środowiskowych i endpointu.")
        else:
            print("ClientError:", e.response.get("Error", {}).get("Message", str(e)))
        print(
            "Dodatkowo sprawdź sieć / firewall oraz, jeśli dotyczy, ustawienia SSH"
            " (perms ~/.ssh, sshd_config, known_hosts)."
        )
        sys.exit(1)
    except Exception as e:
        print("ERROR listing buckets:", type(e).__name__, e)
        print("Common causes: wrong key/secret, network issue, or keys belong to a different account.")
        sys.exit(1)

    # Check provided buckets
    def check_bucket(b):
        try:
            print(f"Checking bucket '{b}'...")
            s3.head_bucket(Bucket=b)
            print(" OK: bucket exists and is accessible")
            return True
        except Exception as e:
            print(f" FAILED: cannot access bucket '{b}':", type(e).__name__, e)
            return False

    def check_versioning(b):
        try:
            resp = s3.get_bucket_versioning(Bucket=b)
            status = resp.get("Status")
            if status == "Enabled":
                print(f" OK: versioning enabled for '{b}'")
                return True
            else:
                print(f" WARNING: versioning not enabled for '{b}' (Status={status})")
                return False
        except Exception as e:
            print(f" FAILED: cannot check versioning for '{b}':", type(e).__name__, e)
            return False

    def test_upload(b):
        key = "check_spaces_creds_temp_object.txt"
        try:
            s3.put_object(Bucket=b, Key=key, Body=b"ok")
            s3.delete_object(Bucket=b, Key=key)
            print(f" OK: test upload/delete succeeded for '{b}'")
            return True
        except Exception as e:
            print(f" FAILED: test upload to '{b}':", type(e).__name__, e)
            return False

    overall_ok = True
    for bucket in args.buckets:
        ok = check_bucket(bucket)
        overall_ok = overall_ok and ok
        if args.check_versioning:
            overall_ok = overall_ok and check_versioning(bucket)
        if args.test_upload:
            overall_ok = overall_ok and test_upload(bucket)

    if not overall_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
