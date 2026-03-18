# Plan: Integracja Parts List z Service Manual

**Status:** 🔮 Przyszłość (do realizacji gdy model symbol detection będzie działał dobrze)

**Data utworzenia:** 13 listopada 2025

---

## 🎯 Cel

Wykorzystanie tabel "Parts List" z końca service manuali do:
1. Weryfikacji wartości komponentów odczytanych OCR
2. Uzupełnienia brakujących danych (napięcie, tolerancja, moc)
3. Rozwiązywania niejednoznaczności (gdy brak jednostki na schemacie)

---

## 📖 Kontekst

### Typowa struktura Service Manual:
```
1. Cover page
2. Safety warnings
3. Specifications
4. Block diagram
5. Circuit diagrams (schematy) ← OCR + symbol detection
6. PCB layout
7. Adjustment procedures
8. Parts List ← KLUCZOWA TABELA
9. Exploded views
```

### Przykład Parts List:

```
┌──────────────┬────────────┬─────────────┬──────────────┬─────────────┐
│ Designator   │ Part No.   │ Description │ Value        │ Remarks     │
├──────────────┼────────────┼─────────────┼──────────────┼─────────────┤
│ C12          │ EC0039M50  │ Capacitor   │ 0.039µF/50V  │ Electrolytic│
│ C13          │ CC100N50   │ Capacitor   │ 100nF/50V    │ Ceramic     │
│ R5           │ CF47K025   │ Resistor    │ 4.7kΩ 1/4W   │ 5%          │
│ R12          │ CF470R025  │ Resistor    │ 470Ω 1/4W    │ 5%          │
│ D1           │ 1N4148     │ Diode       │ -            │ Switching   │
│ Q2           │ 2SC1815    │ Transistor  │ NPN          │ -           │
└──────────────┴────────────┴─────────────┴──────────────┴─────────────┘
```

### Konwencje bez jednostki (często w Parts List):
- Kondensatory < 1: bez jednostki = µF (np. `0.039` = `0.039µF`)
- Kondensatory małe: `100` = `100pF`, `0.1` = `0.1µF`
- Rezystory: liczba = Ω, `4.7K`, `1M`

---

## 🔧 Architektura rozwiązania

### Faza 1: Ekstrakcja Parts List z PDF

```python
# talk_electronic/services/parts_list_extractor.py

class PartsListExtractor:
    """Extract and parse component tables from service manual PDFs."""

    def extract_tables_from_pdf(self, pdf_path: str) -> List[pd.DataFrame]:
        """Find and extract all tables from PDF (using pdfplumber or camelot)."""

    def identify_parts_list_page(self, pages: List) -> Optional[int]:
        """Heuristics to find Parts List page:
        - Keywords: "Parts List", "Component List", "Bill of Materials"
        - Table with columns: Designator, Value, Description
        - Usually near end of document (last 20% of pages)
        """

    def parse_parts_table(self, table_df: pd.DataFrame) -> Dict[str, ComponentSpec]:
        """Parse table into structured component specifications.

        Returns:
            {
                "C12": ComponentSpec(
                    designator="C12",
                    type="capacitor",
                    value="0.039µF",
                    voltage="50V",
                    part_number="EC0039M50",
                    description="Electrolytic capacitor"
                ),
                ...
            }
        """
```

### Faza 2: Matching z wykrytymi komponentami

```python
# talk_electronic/services/component_matcher.py

class ComponentMatcher:
    """Match detected components with Parts List data."""

    def __init__(self, parts_list: Dict[str, ComponentSpec]):
        self.parts_list = parts_list

    def enrich_component(
        self,
        detected: DetectedComponent,
        ocr_value: Optional[str]
    ) -> EnrichedComponent:
        """
        1. Match by designator (C12, R5, etc.)
        2. If OCR value conflicts with Parts List:
           - Parts List ma priorytet (bardziej niezawodne)
           - Log warning o rozbieżności
        3. Uzupełnij brakujące dane (voltage, tolerance, power)

        Returns enriched component with full specifications.
        """
```

### Faza 3: Rozwiązywanie konfliktów

```python
# talk_electronic/services/value_resolver.py

class ComponentValueResolver:
    """Resolve ambiguous or conflicting component values."""

    def resolve_value(
        self,
        designator: str,
        ocr_value: Optional[str],
        parts_list_value: Optional[str],
        component_type: str,
    ) -> ComponentValue:
        """
        Strategia rozwiązywania:

        1. Parts List available + OCR available:
           - Jeśli zgodne: ✓ użyj
           - Jeśli różne: ⚠️  Parts List ma priorytet, log warning

        2. Only Parts List available:
           - ✓ Użyj bezpośrednio

        3. Only OCR available:
           - Parsuj z domyślnymi założeniami jednostek
           - Oznacz jako "uncertain"

        4. Neither available:
           - Wartość "unknown"
           - Pozycja w schemacie + topologia może sugerować typ
        """
```

### Faza 4: Walidacja i confidence scoring

```python
# talk_electronic/services/component_validator.py

class ComponentValidator:
    """Validate component data and assign confidence scores."""

    def validate_component(
        self,
        component: EnrichedComponent
    ) -> ValidationResult:
        """
        Confidence scoring:

        - 1.0: Parts List + OCR zgodne
        - 0.9: Parts List dostępny (OCR brak lub ignored)
        - 0.7: OCR z jednostką (100n, 4.7K)
        - 0.5: OCR bez jednostki (470, 0.039)
        - 0.3: Symbol detection only (brak wartości)
        - 0.0: Konflikt nie rozwiązany

        Flags:
        - needs_manual_review: konflikt lub bardzo niska pewność
        - value_assumed: użyto domyślnych konwencji jednostek
        - parts_list_override: Parts List zastąpił OCR
        """
```

---

## 📊 Workflow integracji

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Upload Service Manual PDF                                     │
└────────────────────┬────────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. Parallel Processing:                                          │
│    ├─ Extract schematic pages → Symbol Detection → OCR values   │
│    └─ Extract Parts List pages → Parse tables → Build lookup    │
└────────────────────┬────────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. Component Enrichment:                                         │
│    For each detected component:                                  │
│      • Match designator with Parts List                          │
│      • Resolve value conflicts                                   │
│      • Add missing specs (voltage, tolerance, power)             │
│      • Calculate confidence score                                │
└────────────────────┬────────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. User Review Interface:                                        │
│    • Show components with confidence < 0.8 for manual review     │
│    • Highlight conflicts: OCR vs Parts List                      │
│    • Allow user override                                         │
└────────────────────┬────────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. Export:                                                       │
│    • Netlist with full component specs                           │
│    • SPICE with accurate values                                  │
│    • BOM (Bill of Materials) ready for ordering                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Technologie

### OCR dla tabel:
- **pdfplumber** - najlepszy dla tabel tekstowych
- **camelot-py** - dla bardziej złożonych layoutów
- **tabula-py** - alternatywa

### Parsowanie tabel:
- **pandas** - analiza i czyszczenie danych
- **regex** - ekstrakcja wartości i jednostek
- **fuzzywuzzy** - fuzzy matching designatorów (C12 vs C-12)

### Storage:
```python
# Struktura danych dla Parts List
{
    "source_pdf": "service_manual_sony_ta-f500.pdf",
    "parts_list_page": 47,
    "extraction_method": "pdfplumber",
    "extraction_confidence": 0.95,
    "components": {
        "C12": {
            "designator": "C12",
            "type": "capacitor",
            "value": "0.039µF",
            "value_si": 3.9e-8,
            "voltage": "50V",
            "polarity": "electrolytic",
            "part_number": "EC0039M50",
            "tolerance": "20%",
            "description": "Electrolytic capacitor",
            "location": "Main PCB",
            "remarks": "Low ESR"
        },
        # ...
    },
    "parsing_warnings": [
        {"row": 45, "issue": "ambiguous_value", "designator": "C99"}
    ]
}
```

---

## 🎨 UI/UX Mockup

### Component Review Panel:

```
╔═══════════════════════════════════════════════════════════════╗
║ Component: C12                                   Confidence: ⚠️ 75%  ║
╠═══════════════════════════════════════════════════════════════╣
║ Detected on Schematic (OCR):                                  ║
║   Value: 0.039  (no unit)                                     ║
║   Polarity: unknown                                           ║
║                                                               ║
║ Parts List (Service Manual p.47):                             ║
║   Value: 0.039µF / 50V                                        ║
║   Part#: EC0039M50                                            ║
║   Type: Electrolytic capacitor                                ║
║                                                               ║
║ ⚙️ Auto-resolved:                                              ║
║   ✓ Value: 0.039µF (from Parts List)                          ║
║   ✓ Voltage: 50V (from Parts List)                            ║
║   ✓ Polarity: polarized (from Parts List: "Electrolytic")    ║
║                                                               ║
║ [ Accept ✓ ]  [ Edit manually ]  [ Mark for review ]         ║
╚═══════════════════════════════════════════════════════════════╝
```

---

## 📈 Korzyści

### 1. **Dokładność**
- ✅ Eliminacja niejednoznaczności (0.039 vs 0.039µF)
- ✅ Uzupełnienie brakujących danych (napięcie, moc, tolerancja)
- ✅ Weryfikacja OCR (Parts List jako ground truth)

### 2. **Automatyzacja**
- ✅ Automatyczne uzupełnianie spec'ów
- ✅ Zmniejszenie manual review (tylko konflikty)
- ✅ Gotowy BOM do zamówienia części

### 3. **Profesjonalizm**
- ✅ Pełne specyfikacje dla każdego komponentu
- ✅ Part numbers dla łatwego sourcing'u
- ✅ Dokumentacja źródła danych (Parts List page number)

### 4. **Diagnostyka**
- ✅ Historia zmian komponentów (Original vs Replacement)
- ✅ Cross-reference z equivalent parts
- ✅ Identyfikacja discontinued parts

---

## 🚧 Wyzwania i rozwiązania

### Wyzwanie 1: Różne formaty Parts List
**Rozwiązanie:**
- Heurystyki + ML do identyfikacji kolumn
- Template matching dla popularnych producentów (Sony, Panasonic, etc.)
- Fallback do manual column mapping przez użytkownika

### Wyzwanie 2: OCR errors w Parts List
**Rozwiązanie:**
- Post-processing z domain knowledge (C12 nie może być "CI2")
- Fuzzy matching designatorów
- Walidacja value formats (regex patterns)

### Wyzwanie 3: Missing Parts List
**Rozwiązanie:**
- Graceful degradation (użyj tylko OCR + symbol detection)
- Sugestia do użytkownika o dodaniu Parts List jeśli dostępny
- Community database parts (crowdsourcing common components)

### Wyzwanie 4: Multilingual (japońskie, niemieckie service manuali)
**Rozwiązanie:**
- Tesseract OCR z multi-language support
- Translation API dla description fields
- Designatory są universal (C12, R5 - no translation needed)

---

## 📅 Implementation Roadmap

### Milestone 1: Parts List Extraction (2-3 tygodnie)
- [ ] PDF table extraction (pdfplumber integration)
- [ ] Parts List page detection heuristics
- [ ] Basic parsing (designator, value, description)
- [ ] Unit tests z sample service manuals

### Milestone 2: Component Matching (2 tygodnie)
- [ ] Designator matching algorithm
- [ ] Value conflict resolution logic
- [ ] Confidence scoring system
- [ ] Integration with existing component detection

### Milestone 3: UI Integration (2 tygodnie)
- [ ] Review panel for low-confidence components
- [ ] Side-by-side OCR vs Parts List display
- [ ] Bulk accept/edit interface
- [ ] Parts List preview (show extracted table)

### Milestone 4: Advanced Features (3 tygodnie)
- [ ] BOM export (CSV, Excel)
- [ ] Part number lookup (Digi-Key, Mouser API)
- [ ] Equivalent parts suggestions
- [ ] Historical parts database (discontinued → replacements)

### Milestone 5: Polish & Testing (1-2 tygodnie)
- [ ] Test with 10+ different service manuals
- [ ] Edge cases handling
- [ ] Performance optimization (large PDFs)
- [ ] Documentation & tutorials

**Szacowany całkowity czas:** 10-12 tygodni (2.5-3 miesiące)

---

## 💡 Przykładowe use cases

### Use Case 1: Naprawa sprzętu
```
Technik serwisowy:
1. Upload service manual Panasonic VCR
2. System automatycznie ekstraktuje schemat + Parts List
3. Identyfikuje uszkodzony C47 (470µF/16V electrolytic)
4. Export BOM → zamówienie części z part number
5. Czas oszczędzony: 30 min manual lookup
```

### Use Case 2: Reverse engineering
```
Hobbista:
1. Upload vintage amplifier service manual
2. Chce zbudować klon schematic
3. System generuje pełny netlist + BOM z dokładnymi spec'ami
4. Może zamówić wszystkie części z pełną kompatybilnością
```

### Use Case 3: Edukacja
```
Student elektroniki:
1. Analizuje klasyczne schematy (np. Fender amplifier)
2. System pokazuje każdy komponent z pełnymi parametrami
3. Może symulować w SPICE z dokładnymi wartościami
4. Rozumie dlaczego konkretne wartości zostały wybrane
```

---

## 🎯 Success Metrics

- **Accuracy:** >95% correct value matching (Parts List vs final netlist)
- **Coverage:** >90% components enriched from Parts List
- **Speed:** <30s to process typical service manual (50-100 pages)
- **User satisfaction:** <5 min manual review time per schematic page
- **Conflict resolution:** <2% components need manual intervention

---

## 🔗 Dependencies

### Prerequisites (muszą być gotowe przed start):
1. ✅ Symbol detection working well (YOLOv8 trained)
2. ✅ OCR for component values (już działa)
3. ✅ Component value parser (✅ DONE dzisiaj!)
4. ✅ Netlist generation pipeline (już jest)

### New dependencies to add:
- pdfplumber==0.10.3
- camelot-py[cv]==0.11.0
- fuzzywuzzy==0.18.0
- python-Levenshtein==0.23.0

---

## 📝 Notatki końcowe

To jest **bardzo realny feature** który doda ogromną wartość dla użytkowników profesjonalnych (technicy serwisowi, repair shops).

**Zalety:**
- ✅ Rozwiązuje real-world problem (niejednoznaczne wartości)
- ✅ Wykorzystuje już dostępne dane (Parts List w PDF)
- ✅ Technicznie możliwe (table extraction to solved problem)
- ✅ Komplementarne z AI symbol detection

**Potencjalny research paper:**
"Automated Component Specification Extraction from Service Manual Documentation for Circuit Reverse Engineering"

---

**Status:** 📋 Plan gotowy do realizacji
**Priorytet:** 🔥 Wysoki (po stabilizacji symbol detection)
**Difficulty:** ⭐⭐⭐ Średnia (głównie integracja i edge cases)
