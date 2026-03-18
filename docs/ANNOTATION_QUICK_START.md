# Quick Start: Anotacja w Label Studio

## Workflow (krok po kroku)

### 1. Przygotowanie
- ✅ Label Studio uruchomione: `label-studio start` → http://localhost:8080
- ✅ Projekt utworzony: `TalkElectronic-Symbols`
- ✅ XML config wklejony z `docs/annotation_tools.md` (linie 24-47)
- ✅ 5-10 PNG schematów wyeksportowanych z aplikacji Flask

### 2. Import obrazów
1. W Label Studio: **Settings** → **Cloud Storage** lub po prostu **Import**
2. Wybierz PNGi z lokalnego dysku
3. Kliknij **Import** → obrazy pojawiają się w liście zadań

### 3. Anotacja (właściwy workflow)

**Dla każdego schematu:**

#### Krok 1: Zaznacz wszystkie symbole
```
POWTARZAJ:
  1. Kliknij label w lewym panelu (np. "resistor")
  2. Narysuj bbox wokół symbolu (przeciągnij myszką)
     - Obejmij cały symbol z pinami/nóżkami
     - Mała przestrzeń wokół (kilka pikseli marginesu)
  3. Jeśli inny symbol tego samego typu → powtórz krok 2
  4. Jeśli inny typ symbolu → wróć do kroku 1
```

**Przykład:**
- Klik `resistor` → rysuj bbox #1 → rysuj bbox #2 → rysuj bbox #3
- Klik `capacitor` → rysuj bbox #4 → rysuj bbox #5
- Klik `transistor` → rysuj bbox #6
- itd.

#### Krok 2: Metadane (na końcu, pod obrazem)
Po zaznaczeniu wszystkich symboli:

1. **confidence_hint** (WYMAGANE):
   - `high` = 100% pewności wszystkich bbox na tym schemacie
   - `medium` = ~80% pewności (kilka trudnych przypadków)
   - `low` = ~60% pewności (złej jakości schemat, dużo edge case'ów)

2. **comment** (OPCJONALNE, zazwyczaj PUSTE):
   - Używaj tylko dla całego schematu (nie dla regionów)
   - Przykłady: "Niska rozdzielczość", "Częściowo zakryty tekst", "Schemat syntetyczny"

3. **bbox_rotation** (ZOSTAW PUSTE):
   - Pole ignorowane w MVP
   - YOLOv8 używa axis-aligned boxes (kąt nie jest potrzebny)

#### Krok 3: Submit
Kliknij **Submit** → przechodź do następnego obrazu

### 4. Eksport anotacji

Po zakończeniu sesji:

1. W Label Studio: **Export** → format **COCO**
2. ✅ Zaznacz checkbox: **"Include metadata"**
3. Pobierz plik JSON
4. Zapisz jako: `data/annotations/labelstudio_exports/<timestamp>.json`
   - Przykład: `data/annotations/labelstudio_exports/2025-11-06_2230.json`
   - 💾 **Nowa praktyka**: skrypt `backup_labelstudio_from_downloads.ps1` zaraz po eksporcie kopiuje wybrane pliki do wersjonowanego katalogu `data/annotations/committed_exports/`. To właśnie z tego folderu dodajemy JSON-y do Gita; `labelstudio_exports/` nadal pełni rolę lokalnego bufora i pozostaje w `.gitignore`.

## Wskazówki praktyczne

### Jak rysować bbox?
- ✅ Obejmij cały symbol (korpus + piny/nóżki)
- ✅ Mały margines (2-5 pikseli) wokół
- ❌ Nie obejmuj opisów/oznaczeń (R1, C5, etc.) – tylko graficzny symbol
- ❌ Nie obejmuj wartości (10kΩ, 100nF, etc.)
- ✅ Fragmenty, które nie są częścią schematu (logo uczelni, legenda tekstowa, zdjęcie PCB) oznaczaj osobną ramką `ignore_region`.

### Które kategorie używać?
Dla MVP skupiamy się na:
- `resistor` (rezystor)
- `capacitor` (kondensator)
- `diode` (dioda)
- `transistor` (tranzystor)
- `inductor` (cewka) – jeśli występuje
- `misc` (różne) – dla symboli, których nie jesteś pewien
- `ignore_region` – całe obszary do zignorowania w preprocessingach (np. logotypy, instrukcje tekstowe, artefakty skanu)

**Ignoruj na razie:**
- `op_amp`, `ground`, `power_rail`, `connector`, `ic_pin`, `net_label`, `measurement`
- Dodamy je w kolejnych iteracjach

### Kiedy używać `misc`?
- Symbol wygląda jak komponent, ale nie wiesz jaki
- Nietypowa reprezentacja standardowego symbolu
- Edge case (rzadki przypadek)

### Cel pierwszej sesji (dziś, 2-3h)
- **2-3 schematy zanotowane**
- **20-30 bounding boxes total**
- **Zrozumienie workflow** (najważniejsze!)

### Cel drugiej sesji (jutro, 2-3h)
- **5 schematów total** (+ pozostałe 2-3)
- **50+ bounding boxes total** (avg 10 symboli/schemat)
- **Pierwszy eksport COCO JSON**

## Troubleshooting

### Label Studio nie startuje?
```powershell
# Sprawdź czy port 8080 jest zajęty
netstat -ano | findstr :8080

# Jeśli zajęty, użyj innego portu
label-studio start --port 8090
```

### Nie widzę pól comment/bbox_rotation?
- Mogą być zwinięte pod obrazem – przewiń w dół
- W MVP możesz je zignorować – nie są wymagane

### Pomyłka przy rysowaniu bbox?
- Kliknij bbox → **Delete** (ikona kosza) lub klawisz **Delete**
- Narysuj ponownie

### Jak edytować istniejący bbox?
- Kliknij bbox → przeciągnij narożniki/krawędzie
- Lub usuń i narysuj ponownie

## Następne kroki po anotacji

1. ✅ Eksport COCO JSON z Label Studio
2. 🔄 Walidacja: `python scripts/validate_annotations.py data/annotations/labelstudio_exports/<plik>.json`
3. 🔄 Normalizacja: `python scripts/labelstudio_to_coco.py --input ... --output data/annotations/train.json`
4. 🔄 Rozbudowa benchmarku: dodaj zanotowane schematy do `data/sample_benchmark/`
5. 🔄 Benchmark template_matching: `python scripts/run_inference_benchmark.py --detector template_matching`
6. 🔄 Dokumentacja baseline: zapisz wyniki w `reports/template_matching_baseline.md`

---

**Powodzenia z pierwszą sesją anotacyjną! 🎯**

Pamiętaj: **Jakość > Ilość** – lepiej 3 dokładnie zanotowane schematy niż 10 pośpiesznych.
