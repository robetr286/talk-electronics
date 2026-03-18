variable "do_token" {
  description = "DigitalOcean API token"
  type        = string
  sensitive   = true
}

variable "ssh_key_ids" {
  description = "List of SSH key IDs to provision on droplet"
  type        = list(string)
}

variable "droplet_name" {
  type    = string
  default = "yolo-gpu"
}

variable "region" {
  type    = string
  default = "ams3"
}

variable "size" {
  type    = string
  default = "g-2vcpu-8gb-gpu"
}

variable "image" {
  type    = string
  default = "ubuntu-22-04-x64"
}

variable "state_bucket" {
  description = "Spaces bucket name for terraform state"
  type        = string
}

variable "state_key" {
  type    = string
  default = "infra/terraform.tfstate"
}

variable "state_region" {
  type    = string
  default = "us-east-1"
}

variable "spaces_endpoint" {
  description = "DigitalOcean Spaces endpoint, e.g. https://nyc3.digitaloceanspaces.com"
  type        = string
}

variable "spaces_key" {
  type      = string
  sensitive = true
}

variable "spaces_secret" {
  type      = string
  sensitive = true
}
