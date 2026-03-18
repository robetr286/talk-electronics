# Konfiguracja Środowisk Python

## Przegląd

Projekt używa **dwóch oddzielnych środowisk conda**:

1. **Talk_flask** - główne środowisko aplikacji Flask
2. **label-studio** - środowisko dla narzędzia do adnotacji Label Studio

## Talk_flask (Główne Środowisko Aplikacji)

### Python Version
- Python 3.11.14

### Kluczowe Zależności

#### Web Framework
- Flask 3.0.0
- Flask-CORS 5.0.0

#### Przetwarzanie Obrazów
- opencv-python-headless 4.12.0.88 (wersja bez GUI, lepsza dla CI/CD)
- Pillow 10.1.0
- PyMuPDF (fitz) 1.25.2

#### Augmentacja Danych
- albumentations 2.0.8
- numpy 2.2.6
- scipy 1.16.3

#### Testowanie
- pytest 8.2.2
- pytest-flask 1.3.0
- pytest-cov 7.0.0

#### Code Quality
- black 25.11.0
- isort 7.0.0
- flake8 7.3.0
- pre-commit 4.4.0

#### Inne
- requests
- python-dotenv

### Instalacja

```bash
# Aktywuj środowisko
conda activate Talk_flask

# Zainstaluj zależności
pip install -r requirements.txt

# Zainstaluj pre-commit hooks
pre-commit install
```

### Uwagi
- **opencv-python vs opencv-python-headless**: Używamy wersji headless, która nie wymaga GUI dependencies (np. Qt). To zmniejsza rozmiar środowiska i ułatwia CI/CD.
- **TensorFlow usunięty**: Wcześniej był TensorFlow 2.15.0 (~2GB), ale nie był używany. Usunięto dla optymalizacji.
- **numpy 2.x**: Zaktualizowano do numpy 2.2.6 (albumentations wymaga >=1.24.4, TensorFlow wymagał <2.0.0, ale został usunięty).

## label-studio (Środowisko Adnotacji)

### Python Version
- Python 3.11.x

### Kluczowe Zależności
- label-studio 1.21.0
- Django 5.x
- djangorestframework
- numpy 1.26.4
- pandas

### Uwagi
- **opencv-python usunięty**: Początkowo było opencv-python 4.11.0.86, ale nie jest potrzebne w środowisku Label Studio. Usunięto duplikację.
- **Separacja środowisk**: Label Studio ma własny, rozbudowany zestaw zależności (160+ pakietów). Trzymanie go w osobnym środowisku zapobiega konfliktom.

## Czyszczenie Środowisk - Best Practices

### Jak wykryć niepotrzebne pakiety

```bash
# Sprawdź wszystkie zainstalowane pakiety
pip list

# Sprawdź konkretny pakiet
pip show nazwa_pakietu

# Sprawdź rozmiar środowiska (PowerShell)
Get-ChildItem C:\Users\robet\miniforge3\envs\Talk_flask -Recurse | Measure-Object -Property Length -Sum | Select-Object @{Name="Size(MB)"; Expression={[math]::Round($_.Sum / 1MB, 2)}}
```

### Typowe problemy

#### Problem: Duplikacja opencv-python i opencv-python-headless
**Rozwiązanie**: Usuń opencv-python, zostaw headless
```bash
pip uninstall opencv-python
```

#### Problem: TensorFlow/Keras nie używany ale zainstalowany
**Rozwiązanie**: Usuń wszystkie pakiety TensorFlow
```bash
pip uninstall tensorflow tensorflow-intel keras tensorboard tensorflow-estimator tensorflow-io-gcs-filesystem tensorboard-data-server
```

#### Problem: Pakiet zainstalowany w złym środowisku
**Rozwiązanie**: Usuń z niewłaściwego, zainstaluj we właściwym
```bash
conda activate niewlasciwe_srodowisko
pip uninstall nazwa_pakietu

conda activate wlasciwe_srodowisko
pip install nazwa_pakietu
```

## Eksport i Synchronizacja

### Eksport requirements.txt

```bash
# W Talk_flask
conda activate Talk_flask
pip freeze > requirements.txt
```

### Import na innej maszynie

```bash
# Utwórz nowe środowisko
conda create -n Talk_flask python=3.11

# Aktywuj
conda activate Talk_flask

# Zainstaluj zależności
pip install -r requirements.txt
```

## Weryfikacja Środowiska

### Sprawdź czy wszystkie kluczowe pakiety są dostępne

```bash
# Test importów
python -c "import flask, cv2, albumentations, PIL, fitz; print('✓ All imports OK')"

# Test pytest
pytest tests/test_pdf_renderer.py -v

# Test pre-commit
pre-commit run --all-files
```

### Sprawdź wersje

```bash
# Python
python --version

# Kluczowe pakiety
pip show flask opencv-python-headless albumentations pytest
```

## Historia Zmian Środowiska

### 2025-11-19
- ✅ Ponownie uruchomiono `pip install -r requirements.txt` po odinstalowaniu całego stosu TensorFlow – brak ostrzeżeń o `protobuf`/`wrapt`.
- ✅ Usunięto z aktywnego środowiska pakiety: `tensorflow`, `tensorflow-intel`, `keras`, `tensorboard`, `tensorflow-estimator`, `tensorflow-io-gcs-filesystem`, `tensorboard-data-server` (zgodnie z instrukcją z sekcji „Typowe problemy”).

### 2025-11-13
- ✅ Dodano albumentations 2.0.8 (wcześniej brakowało)
- ✅ Dodano pytest-cov 7.0.0 (pokrycie kodu w testach)
- ✅ Dodano black, isort, flake8 (pre-commit hooks)
- ✅ Usunięto TensorFlow 2.15.0 (~2GB oszczędności)
- ✅ Zaktualizowano numpy 1.24.3 → 2.2.6
- ✅ Przełączono opencv-python → opencv-python-headless
- ✅ Usunięto opencv-python z label-studio (duplikacja)
- ✅ Zaktualizowano requirements.txt

### Przed czyszczeniem
- Talk_flask: ~72 pakiety, ~X GB
- label-studio: ~160 pakietów

### Po czyszczeniu
- Talk_flask: ~XX pakietów, ~Y GB (oszczędność ~2GB przez usunięcie TensorFlow)
- label-studio: ~XX pakietów

## FAQ

**Q: Dlaczego dwa środowiska?**
A: Label Studio ma bardzo dużo zależności (Django, DRF, storage backends). Separacja zapobiega konfliktom i ułatwia zarządzanie.

**Q: Czy mogę używać venv zamiast conda?**
A: Tak, ale conda jest zalecane dla Windows i łatwiejszej instalacji niektórych pakietów (np. opencv).

**Q: Co zrobić jeśli pip install zawiesza się?**
A: Sprawdź połączenie internetowe, użyj `pip install --verbose nazwa_pakietu` dla diagnostyki, lub użyj `pip install --use-deprecated=legacy-resolver`.

**Q: Czy powinienem commitować requirements.txt?**
A: Tak! requirements.txt powinien być w repo, żeby inni mogli odtworzyć środowisko.

**Q: Jak zaktualizować wszystkie pakiety?**
A: **NIE ZALECANE** - może złamać kompatybilność. Lepiej aktualizować selektywnie:
```bash
pip install --upgrade nazwa_pakietu
pip freeze > requirements.txt
```
