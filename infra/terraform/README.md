Terraform for provisioning GPU droplet (DigitalOcean)

Quickstart
1. Create a Spaces bucket for Terraform state and note `bucket` and `endpoint`.

Important: the state Space (bucket) must be private. Do NOT enable public read access or a CDN on the state bucket.
Enable bucket versioning and keep the bucket private to protect Terraform state. If you need to publish build artifacts,
create a separate artifacts Space and make decisions about CDN/public access for that bucket explicitly and separately.

2. Set environment variables or CI secrets:
   - `TF_VAR_do_token` (DigitalOcean token)
   - `TF_VAR_spaces_key`, `TF_VAR_spaces_secret`, `TF_VAR_spaces_endpoint`, `TF_VAR_state_bucket`
3. Initialize Terraform:

   terraform init

4. Review plan and apply:

   terraform plan
   terraform apply

Notes
- This repo uses DO Spaces (S3-compatible) as the Terraform backend. Spaces does not provide state locking,
  so avoid running parallel `terraform apply` operations.
- Ensure Spaces used for Terraform state are private and versioned; avoid enabling CDN on state buckets.
- For team/production usage consider Terraform Cloud (remote state with locking and run history).

## Troubleshooting

If you see authentication failures when interacting with Spaces (e.g. `InvalidAccessKeyId` or "Unable to authenticate"), check the following:

- Ensure you are using **S3-style Access Key/Secret** generated under **Spaces → Access Keys** in the DigitalOcean control panel, not a **Personal Access Token** from DO > API (these are different and incompatible with the S3 API).
- Verify the env vars used by Terraform/your scripts: `TF_VAR_spaces_key` / `TF_VAR_spaces_secret` or `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` match the Access Key/Secret exactly.
- Check that the Spaces endpoint (`TF_VAR_spaces_endpoint`) is correct (e.g. `https://fra1.digitaloceanspaces.com`).

SSH/remote access issues (if you also manage droplets):

- Check SSH file permissions: `~/.ssh` should be `700` and `~/.ssh/authorized_keys` should be `600`.
- Verify `sshd_config` on the droplet (`PubkeyAuthentication yes`) and restart the SSH daemon after changes.
- Remove stale known-host entries with `ssh-keygen -R <IP>` and re-try `ssh -v root@<IP>` for verbose debug output.

If problems persist, regenerate a new Access Key/Secret in the DO Spaces panel, set them into your environment/CI, and re-run the diagnostic script `scripts/infra/check_spaces_creds.py`.
