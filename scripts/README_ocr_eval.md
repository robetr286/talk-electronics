Instrukcja: przygotowanie zestawu OCR z eksportów Label Studio

Cel
----
Zamieniamy eksporty z Label Studio na ustandaryzowaną strukturę używaną do porównań OCR i testów (np. `ocr_eval/ci` i `ocr_eval/local`).

Ogólne zalecenia
----------------
- Eksportuj zadania **pojedynczo** (po jednym schemacie) — ułatwia to śledzenie i korektę metadanych.
- Każdy plik JSON powinien być nazwany tak samo jak obraz (np. `R001.png` + `R001.json`) albo mieć identyfikator, który zachowamy w polu `id`.
- Zrób eksporty różnych trudności (proste/średnie/złożone) oraz kilka edge-case'ów (niskie DPI, rotacje, ręczne dopiski).

Jak eksportować pojedynczy task z Label Studio
-----------------------------------------------
Opcja A — UI (szybkie, jeśli chcesz klikać):
1. Otwórz projekt w Label Studio.
2. Otwórz konkretny task (zadanie) z interesującym Cię schematem.
3. W menu taska (trzy kropki / opcje) wybierz opcję eksportu lub filtruj listę zadań tak, żeby widzieć tylko ten task i użyj eksportu z filtrem.
4. Pobierz JSON. Zapisz plik jako `ID.json` obok obrazu `ID.png`.

Opcja B — API (dokładne, powtarzalne):
- Pobranie jednego taska (daje info o tasku):
  curl -H "Authorization: Token <YOUR_TOKEN>" "http://<LABEL_STUDIO_HOST>/api/tasks/<TASK_ID>" -o task_<TASK_ID>.json

- Eksport z projektu z konkretnym task_id (jeśli dostępne):
  curl -H "Authorization: Token <YOUR_TOKEN>" "http://<LABEL_STUDIO_HOST>/api/projects/<PROJECT_ID>/export?task_ids=<TASK_ID>&format=JSON" -o export_<TASK_ID>.json

Uwaga: sprawdź konfigurację hosta / tokenu w Twoim środowisku Label Studio. W zależności od wersji API endpointy mogą się nieznacznie różnić (jeśli napotkasz problem, użyj `GET /api/tasks/<id>` i zapisz odpowiedź).

Obrazy
------
- Jeśli export JSON zawiera URL do obrazka (np. `http://.../uploads/abcd.png`), możesz go pobrać (np. `curl -o ID.png "<URL>"`) lub pozwolić, aby skrypt pobrał obraz (wymaga modułu `requests`).
- Jeśli export zawiera tylko lokalną ścieżkę (np. `data/local_files/.../img.png`), skopiuj tę nazwę do katalogu `--images-dir` albo umieść obraz obok JSON.

Format docelowy
----------------
Każdy przykład w `ocr_eval` będzie miał:
- `ID.png` (jeśli dostępny) oraz
- `ID.json` o uproszczonej strukturze:

{
  "id": "R001",
  "source": "label-studio",
  "original": "R001.json",
  "components": [
    { "id": "c1", "label": "R1", "value": "10k", "bbox": [x,y,width,height], "raw": {...} }
  ]
}

Uruchamianie skryptu
---------------------
Przykłady:
- Z katalogu z pojedyńczymi exportami (JSONy):
  python scripts/prepare_ocr_eval.py --single-exports-dir exports/ --images-dir images/ --out-dir ocr_eval --ci-count 20

- Z jednego dużego pliku eksportu:
  python scripts/prepare_ocr_eval.py --labelstudio-export full_export.json --out-dir ocr_eval

Skrypt:
- zapisze pierwsze `--ci-count` przykładów do `ocr_eval/ci` (do użycia w CI), resztę do `ocr_eval/local` (do lokalnych eksperymentów)
- spróbuje skopiować lokalne obrazy lub pobrać je z URL (jeśli `requests` jest zainstalowany)

Kolejne kroki
--------------
- Eksportuj kilka przykładowych tasków (20) i wrzuć je do `exports/` zgodnie z powyższą konwencją.
- Wywołam skrypt, przygotuję `ocr_eval/ci` i potwierdzę strukturę do użycia w CI.

Masz chęć, żebym przygotował od razu przykładowy zestaw 20 plików i dodał drobny test importu do CI? Jeśli tak — rozpocznę generowanie przykładowego zestawu (nie zawiera realnych obrazów, tylko szablony JSON do szybkiego testu).
