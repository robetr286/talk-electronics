# Remote training – checklist anty-utrata metryk (DO + Spaces)

## Przed startem
- Ustaw zmienne: `TF_VAR_do_token`, `SPACES_KEY`, `SPACES_SECRET`, `SPACES_ENDPOINT=https://fra1.digitaloceanspaces.com`, `TF_VAR_state_bucket=talk-electronic-terraform-state`.
- Przygotuj prefix na artefakty: `s3://talk-electronic-artifacts/experiments/<run_name>/` (np. `exp_h100_2025-12-195`).
- Zapamiętaj lokalizację runu na serwerze: np. `/root/runs/remote/<run_name>`.

## Po treningu (na GPU, przed destroy)
1) **Sync pełnego runu do Spaces**
   ```bash
   aws s3 sync /root/runs/remote/<run_name>/ s3://talk-electronic-artifacts/experiments/<run_name>/full_run/ --endpoint-url https://fra1.digitaloceanspaces.com
   ```
2) **Kopia wag** (jeśli nie ma w sync):
   ```bash
   aws s3 cp /root/runs/remote/<run_name>/weights/best.pt s3://talk-electronic-artifacts/experiments/<run_name>/best.pt --endpoint-url https://fra1.digitaloceanspaces.com
   aws s3 cp /root/runs/remote/<run_name>/weights/last.pt s3://talk-electronic-artifacts/experiments/<run_name>/last.pt --endpoint-url https://fra1.digitaloceanspaces.com
   ```
3) **Sprawdzenie obecności metryk** (results/plots):
   ```bash
   aws s3 ls s3://talk-electronic-artifacts/experiments/<run_name>/full_run/ --recursive --endpoint-url https://fra1.digitaloceanspaces.com | head
   ```
4) **Opcjonalne archiwum** (szybszy upload):
   ```bash
   tar -czf /tmp/<run_name>.tgz -C /root/runs/remote <run_name>
   aws s3 cp /tmp/<run_name>.tgz s3://talk-electronic-artifacts/experiments/<run_name>/<run_name>.tgz --endpoint-url https://fra1.digitaloceanspaces.com
   ```
5) **Kopia lokalna** (z własnej maszyny, po SSH/SCP): pobierz `best.pt` oraz `results.csv` z Spaces lub bezpośrednio z serwera przed destroy.

## Przed destroy
- Zweryfikuj w Spaces, że `full_run/` zawiera `results.csv`, `results.png`, `confusion_matrix.png`, `labels.jpg`, `weights/` oraz ewentualne `events.out.tfevents*`.
- Jeśli czegoś brakuje – ponów `aws s3 sync` lub `tar` i `cp`.
- Dopiero potem uruchom `./scripts/do_gpu_apply.ps1 -Action destroy`.

## Po destroy
- Pobierz z Spaces metryki do repo (opcjonalnie katalog `runs/remote/<run_name>` w `reports/runs/`):
  ```bash
  aws s3 sync s3://talk-electronic-artifacts/experiments/<run_name>/full_run/ ./reports/runs/<run_name>/ --endpoint-url https://fra1.digitaloceanspaces.com
  ```
- Zaktualizuj `qa_training.md` o mAP, loss, datę, ścieżkę do artefaktów w Spaces.
