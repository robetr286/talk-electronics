# Infra Troubleshooting — Spaces i SSH

Krótka checklist i polecane komendy diagnostyczne dla DigitalOcean Spaces (S3) oraz podstawowej diagnostyki SSH.

## Spaces (S3) — typowe problemy
- Użyto niewłaściwego tokenu: **Personal Access Token (DO API)** ≠ **Spaces Access Key/Secret (S3)**. Upewnij się, że generujesz Access Key w panelu DO → **Spaces → Access Keys**.
- Błędne zmienne środowiskowe: sprawdź `SPACES_KEY` / `SPACES_SECRET` (lub `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`) i `SPACES_ENDPOINT`.
- Brak uprawnień do bucketa: klucz może nie mieć write/read perms lub bucket ACL jest ustawiony na `private` (to jest ok — upewnij się tylko, że klucz ma dostęp).
- Brak versioningu dla bucketa stanu Terraform — włącz versioning w ustawieniach Space (dla `talk-electronic-terraform-state`).

Polecane komendy:

- Sprawdź widoczne bucket'y (użyj `SPACES_ENDPOINT`):

```bash
python scripts/infra/check_spaces_creds.py --endpoint https://fra1.digitaloceanspaces.com --buckets talk-electronic-terraform-state talk-electronic-artifacts
```

- Test listowania z awscli (jeśli masz skonfigurowane):

```bash
aws s3 ls --endpoint-url https://fra1.digitaloceanspaces.com
```

- Szybki test uploadu (jeśli masz `aws`):

```bash
aws s3 cp /path/to/file.txt s3://talk-electronic-artifacts/ --endpoint-url https://fra1.digitaloceanspaces.com
```

Jeśli widzisz `InvalidAccessKeyId` lub `SignatureDoesNotMatch`:
- Wygeneruj nowy Access Key/Secret w DO → Spaces → Access Keys i ustaw je w środowisku/CI.
- Upewnij się, że **nie** używasz Personal Access Token z DO → API.

## SSH — podstawowa diagnostyka (dostęp do dropletów)
- Sprawdź logi autoryzacji na droplecie:

```bash
sudo tail -f /var/log/auth.log
```

- Użyj verbose SSH, aby zobaczyć powód niepowodzenia:

```bash
ssh -v root@<IP>
```

- Usuń stary wpis znanego hosta, jeśli adres IP zmienił klucz:

```bash
ssh-keygen -R <IP>
```

- Upewnij się, że uprawnienia i konfiguracja SSH są poprawne (na droplecie):

```bash
ls -ld ~/.ssh && ls -l ~/.ssh/authorized_keys
# powinna być 700 dla ~/.ssh i 600 dla authorized_keys
sudo cat /etc/ssh/sshd_config | grep -E "PubkeyAuthentication|PermitRootLogin"
sudo systemctl restart sshd
```

## Co robić, jeśli nic nie pomaga
1. Wygeneruj nowy Access Key/Secret w panelu DO → Spaces → Access Keys.
2. Wklej klucze dokładnie (uważaj na spacje/oryginalne znaki) w lokalnym środowisku lub w GitHub Secrets.
3. Uruchom:

```bash
python scripts/infra/preflight_checks.py --endpoint https://fra1.digitaloceanspaces.com --buckets talk-electronic-terraform-state talk-electronic-artifacts --check-versioning --test-upload
```

4. Jeśli problem dotyczy SSH, prześlij wybrane linie z `ssh -v` i `tail -n 100 /var/log/auth.log` — to ułatwi diagnozę.

CI note: the repository contains a workflow `.github/workflows/preflight.yml` which runs a **dry-run** preflight on pull requests and a **full preflight** on `main` when `SPACES_KEY` and `SPACES_SECRET` are configured as repository secrets. To enable the full preflight on `main` add these secrets (`SPACES_KEY`, `SPACES_SECRET`, `SPACES_ENDPOINT`) in the repository Settings → Secrets and variables → Actions.

---

Dokument ten zawiera krótkie, praktyczne kroki — w razie potrzeby uzupełnię go o dodatkowe scenariusze lub komendy (np. `doctl`), jeśli chcesz.

[ci] Trigger full preflight run on main: 2025-12-16 (automated small docs push to activate workflow)

