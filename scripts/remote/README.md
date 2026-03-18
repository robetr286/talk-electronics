Remote GPU runner (how to use)

Overview
- `sync_and_run.py` : sync local repo to remote droplet and start training command via `ssh`.
- `submit_to_gpu.sh` : convenience wrapper to call the Python helper.
- `push_artifacts.py` : helper to upload run artifacts to DigitalOcean Spaces (S3-compatible). Uploads are private by default; use `--public` only if you explicitly want public artifacts (discouraged). Example usage is included in the script.

Quick start (manual):
1. Create droplet (see `scripts/infra/create_do_gpu_droplet.sh`) and ensure SSH access.
2. From local machine run:

   python scripts/remote/sync_and_run.py --user <user> --host <ip> --remote-path ~/work/flask_gpt_codex --run-cmd "python scripts/experiments/run_retrain_with_args.py --name my_remote_run --epochs 50 --device 0"

3. Logs will be stored on remote under the `debug/` directory; to fetch results use `--fetch-results` flag.

Secrets and storage
- Store DO token and Spaces keys as environment variables or use CI secrets. See `scripts/infra` for provisioning hints.
