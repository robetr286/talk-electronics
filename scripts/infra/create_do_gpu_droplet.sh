#!/usr/bin/env bash
# Simple helper to create a DigitalOcean GPU droplet using doctl
# Requires: doctl authenticated (`doctl auth init`) and SSH key already added to DO

set -euo pipefail

NAME=${1:-yolo-gpu-1}
REGION=${2:-ams3}
SIZE=${3:-g-2vcpu-8gb-gpu}
IMAGE=${4:-ubuntu-22-04-x64}
TAG=${5:-gpu,training}

echo "Creating droplet $NAME ($SIZE) in $REGION..."
doctl compute droplet create "$NAME" --region "$REGION" --size "$SIZE" --image "$IMAGE" --enable-backups=false --ssh-keys "$(doctl compute ssh-key list --no-header | awk '{print $1}' | paste -sd, -)" --tag-names "$TAG" --wait

echo "Droplet created. Use 'doctl compute ssh <droplet-name>' to connect."

echo "You may want to set up firewall rules and install Docker / NVIDIA drivers on the droplet."
