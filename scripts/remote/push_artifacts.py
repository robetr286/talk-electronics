#!/usr/bin/env python3
"""Simple helper to upload artifacts.

Example: set `SPACES_KEY`, `SPACES_SECRET` and `SPACES_ENDPOINT` env vars and use `aws s3` or boto3.
Uploads are private by default; use `--public` to make objects public (discouraged).
"""

import argparse
import os
import subprocess


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dir", default="runs/segment")
    p.add_argument("--bucket", required=True)
    p.add_argument(
        "--public",
        action="store_true",
        help="Make uploaded objects public (use only if you really want public artifacts)",
    )
    p.add_argument("--dry-run", action="store_true", help="Print the upload command without executing it")
    p.add_argument("--retries", type=int, default=2, help="Number of retries on failure (default: 2)")
    p.add_argument("--wait", type=int, default=3, help="Base wait seconds for exponential backoff (default: 3)")
    args = p.parse_args()

    endpoint = os.environ.get("SPACES_ENDPOINT")
    if not endpoint:
        print(
            "Set SPACES_ENDPOINT env var to your DigitalOcean Spaces endpoint, e.g. https://nyc3.digitaloceanspaces.com"
        )
        return

    # Example using aws cli configured with endpoint
    print("Uploading", args.dir, "to bucket", args.bucket)

    acl_flag = ["--acl", "public-read"] if args.public else ["--acl", "private"]
    if args.public:
        print("WARNING: You are uploading artifacts as public. Make sure this is intended.")

    cmd = [
        "aws",
        "s3",
        "cp",
        args.dir,
        f"s3://{args.bucket}/",
        "--recursive",
        "--endpoint-url",
        endpoint,
    ] + acl_flag

    if args.dry_run:
        print("Dry-run mode: command not executed:\n", " ".join(cmd))
        return

    # Retry loop with exponential backoff
    import shlex
    import time

    attempts = args.retries + 1
    for attempt in range(1, attempts + 1):
        print(f"Attempt {attempt}/{attempts}: running: {shlex.join(cmd)}")
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0:
            print("Upload succeeded")
            return
        else:
            print("Upload failed (exit code", proc.returncode, ")")
            if proc.stdout:
                print("STDOUT:\n", proc.stdout)
            if proc.stderr:
                print("STDERR:\n", proc.stderr)

            # Provide helpful suggestions based on output
            stderr = (proc.stderr or "").lower()
            if "invalidaccesskeyid" in stderr or "signaturedoesnotmatch" in stderr:
                print("Suggestion: the provided credentials may be wrong or are not Spaces Access Key/Secret.")
                print(" - Verify env vars: SPACES_KEY / SPACES_SECRET or AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY")
                print(" - Check that you use an Access Key (Spaces) and not a Personal Access Token (DO API token)")
            elif "403" in stderr or "accessdenied" in stderr:
                print("Suggestion: access denied. Check bucket ACL/policy and ensure the key has write permissions.")
            else:
                print("Suggestion: check network/endpoint and run scripts/infra/check_spaces_creds.py for diagnostics.")

            if attempt < attempts:
                backoff = args.wait * (2 ** (attempt - 1))
                print(f"Retrying in {backoff}s...")
                time.sleep(backoff)
            else:
                print("All attempts failed. Aborting.")
                raise SystemExit(proc.returncode)


if __name__ == "__main__":
    main()
