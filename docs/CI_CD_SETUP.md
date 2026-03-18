# Konfiguracja CI/CD

## GitHub Actions

Projekt używa GitHub Actions do automatycznego testowania każdego commitu i pull requesta.

### Przepływy pracy (Workflows)

#### `tests.yml` - Testy jednostkowe i sprawdzanie jakości kodu

**Wyzwalacz:** Push do `main`/`develop` lub Pull Request

**Zadania:**
1. **test** - Uruchamia pytest z pokryciem kodu
   - Strategia macierzowa: Python 3.11
   - Cache pakietów pip dla przyspieszenia
   - Generuje raport pokrycia (XML i terminal)
   - Opcjonalnie wysyła do Codecov

2. **lint** - Sprawdza jakość kodu
   - `black --check` - formatowanie
   - `isort --check` - sortowanie importów
   - `flake8` - analiza kodu z raportowaniem błędów

**Status:** `continue-on-error: true` dla sprawdzania jakości (nie blokuje CI)

---

## Hooki Pre-commit

Automatyczne sprawdzanie kodu **przed zatwierdzeniem (commit)** lokalnie.

### Instalacja

```bash
# Zainstaluj pre-commit
pip install pre-commit

# Zainstaluj hooki w repozytorium
pre-commit install
```

### Skonfigurowane hooki

1. **black** - Automatyczne formatowanie kodu (długość linii=120)
2. **isort** - Sortowanie importów (profil=black)
3. **flake8** - Analiza jakości kodu (max-line-length=120)
4. **trailing-whitespace** - Usuwa białe znaki na końcu linii
5. **end-of-file-fixer** - Dodaje znak nowej linii na końcu pliku
6. **check-yaml** - Walidacja składni YAML
7. **check-json** - Walidacja składni JSON
8. **check-added-large-files** - Blokuje pliki większe niż 1MB
9. **check-merge-conflict** - Wykrywa konflikty scalania
10. **mypy** - Sprawdzanie typów (opcjonalnie, ignoruje brakujące typy)

### Użycie

```bash
# Automatycznie przy zatwierdzeniu
git commit -m "wiadomość"

# Ręcznie na wszystkich plikach
pre-commit run --all-files

# Ręcznie na konkretnym hooku
pre-commit run black --all-files
```

### Pomiń hooki (wyjątkowo)

```bash
git commit -m "WIP: szybka poprawka" --no-verify
```

---

## Konfiguracja Pytest

Plik `pytest.ini` zawiera:

### Opcje uruchomienia
- `--verbose` - Szczegółowe komunikaty
- `--tb=short` - Skrócone ślady błędów
- `--strict-markers` - Wymagaj zdefiniowanych znaczników
- `-ra` - Pokaż podsumowanie wszystkich testów

### Pokrycie kodu (Coverage)
- Źródło: `talk_electronic/`
- Pomiń: testy, migracje, pamięć podręczna
- Precyzja: 2 miejsca po przecinku
- `show_missing = True` - Pokazuj nieprzetestowane linie

### Wykluczone linie (nie liczą się do pokrycia)
- `pragma: no cover`
- `def __repr__`
- `raise NotImplementedError`
- `if __name__ == .__main__.:`
- Bloki sprawdzania typów

---

## Lokalne uruchomienie CI

### Testy
```bash
# Wszystkie testy z pokryciem kodu
pytest --cov=talk_electronic --cov-report=term-missing

# Konkretny plik
pytest tests/test_pdf_renderer.py -v

# Z raportem HTML pokrycia
pytest --cov=talk_electronic --cov-report=html
# Otwórz: htmlcov/index.html
```

### Sprawdzanie jakości kodu
```bash
# Black
black --check talk_electronic/ scripts/ tests/
black talk_electronic/ scripts/ tests/  # Automatyczna naprawa

# isort
isort --check-only talk_electronic/ scripts/ tests/
isort talk_electronic/ scripts/ tests/  # Automatyczna naprawa

# flake8
flake8 talk_electronic/ scripts/ tests/ --max-line-length=120
```

### Wszystko razem
```bash
# Symulacja CI
black --check talk_electronic/ scripts/ tests/ && \
isort --check-only talk_electronic/ scripts/ tests/ && \
flake8 talk_electronic/ scripts/ tests/ --max-line-length=120 && \
pytest --cov=talk_electronic
```

---

## Rozwiązywanie problemów

### Pre-commit działa zbyt wolno
```bash
# Usuń pamięć podręczną i zainstaluj ponownie
pre-commit clean
pre-commit install-hooks
```

### GitHub Actions nie działa, lokalnie wszystko OK
- Sprawdź wersje Pythona (lokalna vs CI)
- Sprawdź zależności w `requirements.txt`
- Uruchom w czystym środowisku wirtualnym:
  ```bash
  python -m venv test_env
  test_env\Scripts\activate
  pip install -r requirements.txt
  pytest
  ```

### Pokrycie kodu zbyt niskie
- Dodaj testy dla nowych plików
- Sprawdź `coverage report --show-missing` dla brakujących linii
- Użyj `# pragma: no cover` dla martwego kodu

---

## Odznaki (opcjonalne)

Dodaj do `README.md`:

```markdown
![Tests](https://github.com/robetr286/Talk_electronic/workflows/Tests/badge.svg)
[![codecov](https://codecov.io/gh/robetr286/Talk_electronic/branch/main/graph/badge.svg)](https://codecov.io/gh/robetr286/Talk_electronic)
```

---

## Plan rozwoju

- [ ] Dodać tryb ścisły mypy po dodaniu adnotacji typów
- [ ] Integracja z Codecov dla publicznego repozytorium
- [ ] Przepływ wdrażania dla produkcji
- [ ] Testy wydajności w CI
- [ ] Skanowanie bezpieczeństwa (Bandit, Safety)
