resource "digitalocean_droplet" "gpu" {
  name   = var.droplet_name
  region = var.region
  size   = var.size
  image  = var.image
  tags   = ["gpu", "training"]

  ssh_keys = var.ssh_key_ids

  # Optional cloud-init / user_data to install NVIDIA drivers, docker, etc.
  user_data = <<-EOF
    #cloud-config
    packages:
      - curl
      - apt-transport-https
    runcmd:
      - curl -sSL https://get.docker.com | sh
      - apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y nvidia-driver-525
  EOF
}

output "droplet_id" {
  value = digitalocean_droplet.gpu.id
}

output "droplet_ipv4" {
  value = digitalocean_droplet.gpu.ipv4_address
}
