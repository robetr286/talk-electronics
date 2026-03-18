terraform {
  backend "s3" {
    # Parametry backendu podawane w czasie `terraform init -backend-config=...`
    skip_region_validation      = true
    skip_credentials_validation = true
  }
}

# NOTE: DO Spaces does not provide state locking. For team/production use,
# consider Terraform Cloud or another backend with locking enabled.
# Important: the Spaces bucket used for Terraform state MUST be private and
# versioned. Do NOT enable a CDN or public-read on your state bucket.
