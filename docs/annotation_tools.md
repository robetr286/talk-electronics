# Specyfikacja narzędzi do anotacji

Ten dokument standaryzuje konfigurację Label Studio dla zbioru danych detekcji symboli.

## Workspace Label Studio
- **Projekt**: `TalkElectronic-Symbols` (spójna nazwa w całym repozytorium).
- **Konfiguracja etykiet**: użyj poniższego szablonu (zapisz jako `data/annotations/labelstudio_templates/schematic_hybrid_template.xml`).

**⚠️ WAŻNE**: Nowy template wspiera **hybrydowe podejście** (rotated rectangles + polygons). Zobacz `docs/ROTATED_BBOX_STRATEGY.md` dla pełnej dokumentacji.

```xml
<View>
  <Header value="Schematic Symbol Annotation - Hybrid (Rotated Rectangle + Polygon)"/>

  <!-- SECONDARY TOOL: Polygon (use 10-20% for edge cases) -->
  <PolygonLabels name="poly_label" toName="image" strokeWidth="3" opacity="0.6">
    <Label value="resistor" background="#e63946" hotkey="shift+1"/>
    <Label value="capacitor" background="#457b9d" hotkey="shift+2"/>
    <Label value="inductor" background="#45B7D1"/>
    <Label value="diode" background="#fb8500" hotkey="shift+3"/>
    <Label value="transistor" background="#023047" hotkey="shift+4"/>
    <Label value="op_amp" background="#1d3557" hotkey="shift+5"/>
    <Label value="ic" background="#F7DC6F"/>
    <Label value="connector" background="#ffb703" hotkey="shift+6"/>
    <Label value="power_rail" background="#8ecae6" hotkey="shift+7"/>
    <Label value="ground" background="#2a9d8f" hotkey="shift+8"/>
    <Label value="ic_pin" background="#219ebc" hotkey="shift+9"/>
    <Label value="net_label" background="#ff006e" hotkey="shift+0"/>
    <Label value="measurement_point" background="#8338ec" hotkey="shift+q"/>
    <Label value="misc_symbol" background="#3a86ff" hotkey="shift+w"/>
    <Label value="ignore_region" background="#6a4c93" hotkey="shift+e"/>
    <!-- Legacy support for starych anotacji -->
    <Label value="broken_line" background="#fff176" hotkey="shift+r"/>
  </PolygonLabels>

  <!-- PRIMARY TOOL: Rotated Rectangle (use 80-90% of time) -->
  <RectangleLabels name="rect_label" toName="image" canRotate="true" strokeWidth="3" opacity="0.6">
    <Label value="resistor" background="#e63946" hotkey="1"/>
    <Label value="capacitor" background="#457b9d" hotkey="2"/>
    <Label value="inductor" background="#45B7D1"/>
    <Label value="diode" background="#fb8500" hotkey="3"/>
    <Label value="transistor" background="#023047" hotkey="4"/>
    <Label value="op_amp" background="#1d3557" hotkey="5"/>
    <Label value="ic" background="#F7DC6F"/>
    <Label value="connector" background="#ffb703" hotkey="6"/>
    <Label value="edge_connector" background="#ffd600" hotkey="g"/>
    <Label value="power_rail" background="#8ecae6" hotkey="7"/>
    <Label value="ground" background="#2a9d8f" hotkey="8"/>
    <Label value="ic_pin" background="#219ebc" hotkey="9"/>
    <Label value="net_label" background="#ff006e" hotkey="0"/>
    <Label value="measurement_point" background="#8338ec" hotkey="q"/>
    <Label value="misc_symbol" background="#3a86ff" hotkey="w"/>
    <Label value="ignore_region" background="#6a4c93" hotkey="e"/>
    <Label value="broken_line" background="#fff176" hotkey="r"/>
  </RectangleLabels>

  <!-- Image to annotate -->
  <Image name="image" value="$image" zoom="true" zoomControl="true" rotateControl="false"/>

  <!-- Optional metadata fields -->
  <Header value="Quality Flags (Optional)"/>

  <Choices name="quality" toName="image" choice="single" showInline="true">
    <Choice value="clean" hint="Clear, unambiguous annotation"/>
    <Choice value="noisy" hint="Contains unwanted text/elements"/>
    <Choice value="partial" hint="Symbol partially visible"/>
    <Choice value="uncertain" hint="Unsure about class or bounds"/>
  </Choices>

  <TextArea name="notes" toName="image"
            placeholder="Optional: Why did you use polygon? Any special notes?"
            rows="2"
            maxSubmissions="1"/>
</View>
```

### `ignore_region` – kiedy używać?
- Oznaczaj tą klasą każdy obszar, który nie jest częścią schematu, np. logo producenta, zbędne zdjęcia PCB, instrukcje tekstowe, artefakty skanu lub przyciemnione marginesy.
- Ramka/polygon `ignore_region` nie otrzymuje metadanych – służy wyłącznie do maskowania tych fragmentów w preprocessingach.
- Staraj się objąć całą „śmieciową” strukturę jedną ramką; nie mieszaj z innymi klasami, żeby exporter mógł łatwo odfiltrować region.

-### `broken_line` – zgłaszanie przerwanych ścieżek
- Użyj narzędzia Rectangle (`r`) i narysuj wąski prostokąt (3–4 px szerokości, 20–40 px długości) pokrywający brakujący fragment przewodu; jeśli przerw jest kilka, dodaj osobne regiony.
- W panelu Polygon wciąż widnieje `broken_line` (dla kompatybilności ze starszymi zadaniami) – **nie korzystaj** z niego przy nowych adnotacjach, chyba że trzeba poprawić starą figurę w tym samym formacie.
- Po zaznaczeniu wprowadź metadane w formacie `type=broken_line reason=<opis> severity=<minor|major|critical>` w `region_comment` (np. `reason=scan_gap_pin3 severity=major`).
- `reason` powinien mieć co najmniej 6 znaków i wyjaśniać kontekst, a `severity` określa wpływ na zrozumienie schematu przez AI (minor = kosmetyka, major = psuje jedną gałąź, critical = uniemożliwia analizę wielu gałęzi/zasilania).
- Dzięki temu walidator (`scripts/validate_annotation_metadata.py`) oraz pipeline generowania netlist otrzymują czytelną listę miejsc, które wymagają ręcznej naprawy.

-### `edge_connector` – kontynuacja sieci na innych stronach
- Gdy przewód wychodzi poza krawędź strony (wielostronicowy PDF), narysuj niewielki prostokąt (Rectangle tool `g`) obejmujący końcówkę linii i podpis (trzymaj szerokość do kilku pikseli, długość ~15–25 px). Polygon traktuj tylko awaryjnie.
- W `region_comment` wpisz minimum `type=edge_connector edge_id=<kod> page=<widoczny_numer>` oraz opcjonalne `note=<dokładniejsza wskazówka>`.
- `edge_id` stosuj według konwencji `<litera_krawędzi><dwucyfrowy_numer>` (np. `A05` – lewa krawędź, piąty punkt licząc od góry); docelowo ten sam identyfikator pojawia się na obu stronach połączenia.
- Pole `page` kopiuj z numeracji strony widocznej na schemacie (jeśli brak – użyj numeracji logicznej przyjętej w projekcie, np. 1-based według kolejności w PDF).
- `note` wykorzystaj do opisania docelowej strony/arkusza (np. `note=to_sheet3`, `note=section_B`), żeby QA mogło szybko odszukać kontynuację.

### Eksport z Label Studio
- Preferowany eksport: `COCO JSON` (Label Studio native export).
- **WAŻNE**: Export automatycznie zawiera informacje o rotation dla RectangleLabels!
- Zapisuj surowe eksporty w `data/annotations/labelstudio_exports/<timestamp>.json`.
- Pliki przeznaczone do commitów kopiuj (lub pozwól zrobić to skryptowi `backup_labelstudio_from_downloads.ps1`) do `data/annotations/committed_exports/` – tylko ten katalog jest śledzony w repo.
- Konwertuj do COCO instance segmentation używając:
  ```bash
  python scripts/export_labelstudio_to_coco_seg.py \
      --input data/annotations/labelstudio_exports/2025-11-06_1800.json \
      --output data/annotations/coco_seg/train.json \
      --images-dir data/images
  ```
- Skrypt automatycznie:
  - ✅ Konwertuje rotated rectangles → 4-corner polygons
  - ✅ Zachowuje polygons bez zmian
  - ✅ Zapisuje kąt rotacji w `attributes.rotation` (metadata)
  - ✅ Generuje unified COCO segmentation format

## Workflow synchronizacji
1. Przydziel kolejki etykietowania w Label Studio; unikaj jednoczesnej edycji tych samych zasobów przez wielu anotatorów.
2. Po każdym sprincie zbierz eksporty, uruchom skrypty konwersji i wygeneruj ponownie podziały `train/val/test`.
3. Waliduj schemat przez `scripts/validate_annotations.py --schema docs/annotation_schema.json data/annotations/*.json` przed commitowaniem zmian.
4. Aktualizuj `class_mapping.json` przy dodawaniu/usuwaniu klas; regeneruj konfiguracje narzędzi używając `scripts/export_labels.py` aby zachować spójność palet kolorów.

## Generator syntetycznych danych

Obok ręcznych anotacji wykorzystujemy pipeline syntetycznych schematów do generowania danych treningowych z automatycznymi anotacjami.

### Struktura pipeline'u

```
data/synthetic/
├── images_raw/          # Czyste rendery z KiCad (300 DPI)
├── images_augmented/    # Obrazy po augmentacji
├── annotations/         # Pliki COCO JSON
└── metadata.csv         # Parametry generatora
```

### Workflow generowania

1. **Generowanie schematu** (`generate_schematic.py`)
   ```bash
   python scripts/synthetic/generate_schematic.py \
       --output data/synthetic/schematic_001.pdf \
       --metadata data/synthetic/schematic_001.json \
       --seed 42 --components 15
   ```
   Status: 🚧 W implementacji (wymaga KiCad API)

2. **Eksport do PNG** (`export_png.py`)
   ```bash
   python scripts/synthetic/export_png.py \
       --input data/synthetic/schematic_001.pdf \
       --output data/synthetic/images_raw/schematic_001.png \
       --dpi 300
   ```
   Status: ✅ Gotowe (PyMuPDF)

3. **Generowanie anotacji COCO** (`emit_annotations.py`)
   ```bash
   python scripts/synthetic/emit_annotations.py \
       --metadata data/synthetic/schematic_001.json \
       --image data/synthetic/images_raw/schematic_001.png \
       --output data/synthetic/annotations/raw.json
   ```
   Status: ✅ Gotowe

4. **Augmentacja datasetu** (`augment_dataset.py`)
   ```bash
   python scripts/synthetic/augment_dataset.py \
       --input data/synthetic/images_raw/ \
       --output data/synthetic/images_augmented/ \
       --annotations data/synthetic/annotations/raw.json \
       --profile scan
   ```
   Status: ✅ Gotowe (wymaga `albumentations`)

### Profile augmentacji

- **light**: Drobne artefakty (szum gaussowski, lekki blur)
- **scan**: Symulacja skanowania (artefakty ISO, rotacja ±5°, kontrast)
- **heavy**: Maksymalne zróżnicowanie (dropout, silny szum, rotacja ±10°)

### Kategorie komponentów

| ID | Nazwa | Symbol | Superkategoria |
|----|-------|--------|----------------|
| 1  | resistor | R | passive |
| 2  | capacitor | C | passive |
| 3  | inductor | L | passive |
| 4  | diode | D | semiconductor |
| 5  | transistor | Q | semiconductor |
| 6  | ic | U | integrated |
| 7  | connector | J | connector |
| 8  | node | node | connection |

### Walidacja

```bash
python scripts/validate_annotations.py data/synthetic/annotations/raw.json
```

Szczegóły implementacji: `scripts/synthetic/README.md`
