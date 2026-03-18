"""
Skrypt do automatycznego eksportu anotacji z Label Studio.
Użycie: python scripts/backup_labelstudio.py [--project-id ID]
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import requests


def export_labelstudio_project(
    project_id: int = 1, api_token: str = None, output_dir: str = "data/annotations/labelstudio_exports"
):
    """
    Eksportuje projekt Label Studio do pliku JSON.

    Args:
        project_id: ID projektu w Label Studio
        api_token: Token API (jeśli wymagany)
        output_dir: Katalog wyjściowy
    """
    import os

    base_url = "http://localhost:8082"

    # Token z argumentu lub zmiennej środowiskowej
    if api_token is None:
        api_token = os.environ.get("LABEL_STUDIO_API_TOKEN")

    # Nagłówki
    headers = {}
    if api_token:
        headers["Authorization"] = f"Token {api_token}"

    # Pobierz projekt
    project_url = f"{base_url}/api/projects/{project_id}"
    response = requests.get(project_url, headers=headers)

    if response.status_code != 200:
        print(f"❌ Błąd pobierania projektu: {response.status_code}")
        print(f"   Upewnij się, że Label Studio działa na {base_url}")
        sys.exit(1)

    project_info = response.json()
    project_title = project_info.get("title", f"project_{project_id}")

    # Eksportuj anotacje
    export_url = f"{base_url}/api/projects/{project_id}/export"
    params = {"exportType": "JSON"}

    response = requests.get(export_url, headers=headers, params=params)

    if response.status_code != 200:
        print(f"❌ Błąd eksportu: {response.status_code}")
        sys.exit(1)

    annotations = response.json()

    # Statystyki (do nazwy pliku)
    num_tasks = len(annotations)
    num_annotated = sum(1 for task in annotations if task.get("annotations"))

    # Przygotuj nazwę pliku
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = "".join(c for c in project_title if c.isalnum() or c in (" ", "-", "_")).strip()
    safe_title = safe_title.replace(" ", "_")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Dodaj metadata do nazwy: project_id, liczba zadań
    filename = output_path / f"{safe_title}_proj{project_id}_tasks{num_tasks}_{timestamp}.json"

    # Dodaj metadata do pliku JSON
    backup_data = {
        "export_metadata": {
            "project_id": project_id,
            "project_title": project_title,
            "export_timestamp": timestamp,
            "num_tasks": num_tasks,
            "num_annotated": num_annotated,
            "labelstudio_version": "label-studio",
            "notes": "Backup created by backup_labelstudio.py",
        },
        "tasks": annotations,
    }

    # Zapisz
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(backup_data, f, indent=2, ensure_ascii=False)

    print("✅ Eksport zakończony:")
    print(f"   📁 Plik: {filename}")
    print(f"   📊 Zadań: {num_tasks}")
    print(f"   ✓ Zanotowanych: {num_annotated}")
    print(f"   💾 Rozmiar: {filename.stat().st_size / 1024:.1f} KB")
    print("\n💡 Dodaj do repozytorium:")
    print(f"   git add {filename}")
    print(f'   git commit -m "Backup Label Studio annotations - {timestamp}"')
    print("   git push")

    return filename


def main():
    parser = argparse.ArgumentParser(description="Backup Label Studio annotations")
    parser.add_argument("--project-id", type=int, default=1, help="ID projektu Label Studio (domyślnie: 1)")
    parser.add_argument("--api-token", type=str, default=None, help="Token API Label Studio (jeśli wymagany)")
    parser.add_argument(
        "--output-dir", type=str, default="data/annotations/labelstudio_exports", help="Katalog wyjściowy dla backupu"
    )

    args = parser.parse_args()

    try:
        export_labelstudio_project(project_id=args.project_id, api_token=args.api_token, output_dir=args.output_dir)
    except requests.exceptions.ConnectionError:
        print("❌ Nie można połączyć się z Label Studio")
        print("   Sprawdź czy Label Studio jest uruchomione:")
        print("   label-studio start")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Błąd: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
