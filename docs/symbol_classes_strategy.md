# Strategia klas symboli elektronicznych

## Decyzje kluczowe

### Nazewnictwo: Angielskie vs Polskie

**✅ UŻYWAJ NAZW ANGIELSKICH** (resistor, capacitor, etc.)

#### Uzasadnienie:
- **Standardy ML**: Wszystkie pretrenowane modele (YOLO, COCO datasets) używają angielskich nazw
- **Kompatybilność kodu**: Klasy w kodzie Pythona: `class_names = ['resistor', 'capacitor']`
- **Dokumentacja**: Papers, tutorials, GitHub repos – wszystko po angielsku
- **Transfer learning**: Jeśli kiedyś użyjesz pretrenowanego modelu elektroniki, nazwy będą zgodne
- **SPICE/netlist export**: Formaty netlist używają angielskich oznaczeń (R, C, L, D, Q)
- **Międzynarodowość**: Łatwiej podzielić się modelem/datasetem z community

#### Polskie nazwy mogą być:
- W UI aplikacji (wyświetlanie dla użytkownika)
- W dokumentacji dla polskich użytkowników
- Jako alias/tłumaczenie w słowniku: `{'resistor': 'rezystor'}`

---

## Faza 1: MVP 0.1 – 9 klas podstawowych

### Lista klas startowych

```python
CORE_CLASSES_V1 = [
    'resistor',     # R - najbardziej powszechny
    'capacitor',    # C - bardzo częsty
    'inductor',     # L - rzadszy, ale ważny
    'diode',        # D - powszechny (LED, Zener, Schottky)
    'transistor',   # Q - BJT + MOSFET razem (na początku)
    'ic',           # U - ogólna klasa (op-amp, digital IC)
    'connector',    # J - interfejsy
    'ground',       # GND - critical dla netlist
    'power',        # VCC/VDD - critical dla netlist
]
```

### Dlaczego te 9 klas?
- Pokrywają **~80% symboli** w typowych schematach
- Wystarczające do wygenerowania użytecznej netlisty
- Łatwe do anotacji (wyraźne różnice wizualne)
- Szybki trening (mniej klas = szybsza konwergencja)
- Minimum potrzebne do funkcjonalnego MVP

---

## Szczegółowy opis klas (MVP 0.1)

### 1. **resistor** (rezystor)
- **Symbol**: Prostokąt (Europe: IEC) lub zygzak (USA: ANSI)
- **Oznaczenia**: R1, R2, R10
- **Wartości**: 10Ω, 1kΩ, 1MΩ
- **Warianty**: Rezystor stały, potencjometr (na później), termistor (na później)
- **SPICE prefix**: R

### 2. **capacitor** (kondensator)
- **Symbol**:
  - Niepolaryzowany: dwie równoległe linie `||`
  - Polaryzowany (elektrolityczny): jedna prosta + jedna zakrzywiona `|(`
- **Oznaczenia**: C1, C2, C100
- **Wartości**: 10pF, 100nF, 10µF, 1000µF
- **Warianty**: Ceramiczny, elektrolityczny, tantalowy
- **SPICE prefix**: C

### 3. **inductor** (cewka)
- **Symbol**: Seria półokręgów/spirala
- **Oznaczenia**: L1, L2, L10
- **Wartości**: 1µH, 100µH, 1mH
- **Warianty**: Cewka powietrzna, z rdzeniem ferrytowym
- **SPICE prefix**: L

### 4. **diode** (dioda)
- **Symbol**: Trójkąt + linia (strzałka pokazuje kierunek przewodzenia)
- **Oznaczenia**: D1, D2, LED1
- **Typy** (na początku wszystkie w jednej klasie):
  - Zwykła dioda prostownicza
  - LED (Light Emitting Diode)
  - Dioda Zenera (stabilizacja napięcia)
  - Dioda Schottky'ego (szybka)
- **SPICE prefix**: D

### 5. **transistor** (tranzystor)
- **Symbol**: Trzy końcówki
  - BJT: kolektor/emiter/baza (NPN/PNP)
  - MOSFET: dren/źródło/bramka (N-channel/P-channel)
- **Oznaczenia**: Q1, Q2, T1 (starsze schematy)
- **Typy** (na początku wszystkie w jednej klasie):
  - BJT NPN/PNP
  - MOSFET N/P
  - JFET
- **SPICE prefix**: Q

### 6. **ic** (układ scalony / integrated circuit)
- **Symbol**:
  - Prostokąt z wieloma pinami
  - Standardowe symbole (trójkąt = op-amp, prostokąt z napisem = digital IC)
- **Oznaczenia**: U1, U2, IC1
- **Przykłady**:
  - Wzmacniacze operacyjne (LM358, TL072)
  - Timery (555, 556)
  - Regulatory napięcia (LM7805, LM317)
  - Mikrokontrolery (ATmega, STM32)
  - Bramki logiczne (74HC00)
- **SPICE prefix**: U, X (subcircuit)

### 7. **connector** (złącze)
- **Symbol**:
  - Pin header (szereg kwadratów/kółek)
  - Terminal block (rzędy śrub)
  - Specjalizowane (USB, HDMI, audio jack)
- **Oznaczenia**: J1, J2, CON1, P1
- **Typy**:
  - Wtyki/gniazda zasilania
  - Złącza sygnałowe
  - Interfejsy komunikacyjne
- **SPICE**: Zazwyczaj nie modelowane (połączenia external)

### 8. **ground** (masa)
- **Symbol**:
  - Pozioma linia z pionowymi kreskami (ziemia)
  - Trójkąt (masa sygnałowa)
  - Trzy poziome linie różnej długości (ziemia ochronna)
- **Oznaczenia**: GND, AGND (analogowa), DGND (cyfrowa), PGND (zasilania)
- **Funkcja**: **Critical** dla generowania netlisty – punkt odniesienia
- **SPICE**: Node 0 (common reference)

### 9. **power** (zasilanie)
- **Symbol**:
  - Strzałka w górę
  - Kółko z kreską
  - Pozioma linia na górze
- **Oznaczenia**: +5V, +12V, -12V, VCC, VDD, VBAT, V+
- **Funkcja**: **Critical** dla generowania netlisty – źródła napięcia
- **SPICE**: Voltage source nodes

### 10. **ignore_region** (strefa ignorowana)
- **Symbol**: dowolny prostokąt/polygon, który obejmuje fragment spoza schematu (logo uczelni, instrukcje tekstowe, zdjęcie PCB, artefakty skanu)
- **Oznaczenia**: brak – nie wpisujemy `designator`, `type` ani `note`
- **Funkcja**: maskowanie śmieci przed treningiem modeli, aby pipeline wiedział co przyciąć
- **Uwaga**: nie łącz w jednym regionie elementów schematu i tła; jeżeli śmieci jest więcej, narysuj kilka oddzielnych `ignore_region`

-### 11. **broken_line** (przerwana linia przewodu)
- **Symbol**: bardzo wąski prostokąt poprowadzony dokładnie po brakującym odcinku przewodu albo przy krawędziach przerwy, aby wskazać miejsce uszkodzenia
- **Oznaczenia/metadane**: brak designatora; w `region_comment` wpisujemy `type=broken_line reason=<opis> severity=<minor|major|critical>`
- **Funkcja**: flagowanie błędów w źródłowym schemacie (np. dziura w skanie, zanik pikseli) tak, by pipeline potrafił zignorować nieciągłość przy generowaniu netlisty i przekazać raport do naprawy
- **Zasady**:
  - `reason` musi jasno opisywać problem (min. 6 znaków, bez skrótów typu `???`)
  - `severity` ocenia wpływ na analizę: `minor` (drobne ubytki), `major` (przerywa pojedynczą gałąź), `critical` (odcina zasilanie/wiele gałęzi)
  - Każdą przerwę oznacz osobno; gdy linia jest przerwana w kilku miejscach, dodaj kilka regionów, by raport był granularny
  - Używaj tylko jeśli linia faktycznie powinna być ciągła – nie służy do ignorowania świadomie rozłączonych ścieżek

### 12. **edge_connector** (łącze krawędziowe)
- **Symbol**: niewielki prostokąt lub poligon obejmujący koniec przewodu na krawędzi arkusza oraz opis sieci.
- **Oznaczenia/metadane**: `type=edge_connector edge_id=<kod> page=<nr>` i opcjonalne `note=<cel>`.
- **Konwencja edge_id**: litera (`A`=lewa, `B`=prawa, `C`=górna, `D`=dolna krawędź) + dwie cyfry kolejności (`01–99`). Ten sam kod stosujemy na obu arkuszach, tworząc pary.
- **Funkcja**: umożliwia netliście i chatowi AI odnalezienie kontynuacji sieci w wielostronicowych schematach oraz raportowanie brakujących połączeń między arkuszami.
- **Dodatkowe pola**: `page` służy do wskazania fizycznego numeru strony z rysunku, `note` opisuje docelowy arkusz/sektor (np. `note=to_sheet3`).

---

## Konfiguracja Label Studio (MVP 0.1)

### XML template dla projektu

```xml
<View>
  <Image name="image" value="$image"/>
  <RectangleLabels name="label" toName="image">
    <Label value="resistor" background="#FF6B6B"/>
    <Label value="capacitor" background="#4ECDC4"/>
    <Label value="inductor" background="#45B7D1"/>
    <Label value="diode" background="#FFA07A"/>
    <Label value="transistor" background="#98D8C8"/>
    <Label value="ic" background="#F7DC6F"/>
    <Label value="connector" background="#BB8FCE"/>
    <Label value="ground" background="#85929E"/>
    <Label value="power" background="#F39C12"/>
    <Label value="ignore_region" background="#6A4C93"/>
  </RectangleLabels>
</View>
```

### Paleta kolorów (dla łatwości rozróżnienia)
- `resistor`: #FF6B6B (czerwony)
- `capacitor`: #4ECDC4 (turkusowy)
- `inductor`: #45B7D1 (niebieski)
- `diode`: #FFA07A (łososiowy)
- `transistor`: #98D8C8 (miętowy)
- `ic`: #F7DC6F (żółty)
- `connector`: #BB8FCE (fioletowy)
- `ground`: #85929E (szary)
- `power`: #F39C12 (pomarańczowy)
- `ignore_region`: #6A4C93 (śliwkowy)

---

## Faza 2: MVP 0.2 – Rozszerzenie (5-7 klas)

**Kiedy dodać?** Po osiągnięciu **mAP > 0.7** na 9 klasach podstawowych

```python
EXTENDED_CLASSES_V2 = CORE_CLASSES_V1 + [
    'op_amp',           # Wydzielony z 'ic' (bardzo specyficzny kształt trójkąta)
    'switch',           # Przełączniki, przyciski (SPST, SPDT, DPDT)
    'relay',            # Przekaźniki
    'transformer',      # Transformatory (dwie cewki z rdzeniem)
    'crystal',          # Kwarc, oscylatory (X1, XTAL)
    'fuse',             # Bezpieczniki (F1, FUSE)
    'voltage_source',   # Źródła napięcia (baterie, zasilacze - kółko z +/-)
]
```

### Dlaczego te klasy w drugiej fazie?
- **op_amp**: Bardzo powszechny, ale wyraźnie odróżnialny od ogólnego IC (trójkąt)
- **switch/relay**: Ważne dla logiki sterowania, ale rzadsze niż podstawowe
- **transformer**: Specjalistyczny, głównie w power supply
- **crystal/fuse**: Rzadsze, ale charakterystyczne kształty
- **voltage_source**: Uzupełnienie power/ground (baterie, generatory)

---

## Faza 3: Post-MVP – Subklasy specjalistyczne

**Kiedy dodać?** Po zebraniu **500+ schematów** i konkretnych use case

### Szczegółowe subklasy tranzystorów
```python
TRANSISTOR_SUBCLASSES = [
    'bjt_npn',      # Zamiast ogólnego 'transistor'
    'bjt_pnp',
    'mosfet_n',
    'mosfet_p',
    'jfet_n',
    'jfet_p',
]
```

### Szczegółowe subklasy diod
```python
DIODE_SUBCLASSES = [
    'diode_rectifier',  # Zwykła prostownicza
    'diode_schottky',   # Szybka
    'diode_zener',      # Stabilizacyjna
    'led',              # Light emitting
    'photodiode',       # Czuła na światło
]
```

### Komponenty pasywne rozszerzone
```python
PASSIVE_EXTENDED = [
    'potentiometer',    # Rezystor zmienny
    'varistor',         # MOV - ochrona przepięciowa
    'thermistor',       # NTC/PTC - czujnik temp
    'variable_capacitor', # Kondensator zmienny (tuning)
]
```

### Zaawansowane IC
```python
IC_SPECIALIZED = [
    'microcontroller',  # MCU (Arduino, STM32, PIC)
    'memory',           # EEPROM, Flash, RAM
    'logic_gate',       # AND, OR, NOT, NAND, NOR, XOR
    'comparator',       # Komparator napięcia
    'adc',              # Analog-to-Digital Converter
    'dac',              # Digital-to-Analog Converter
]
```

### Sensory i aktuatory
```python
SENSORS_ACTUATORS = [
    'sensor_temp',      # Czujnik temperatury
    'sensor_light',     # Fotorezystor, LDR
    'sensor_pressure',  # Czujnik ciśnienia
    'motor',            # Silnik DC/stepper
    'speaker',          # Głośnik, buzzer
]
```

---

## Strategia rozwoju – Flow diagram

```
START: 9 klas podstawowych (MVP 0.1)
  ↓
Anotacja 50+ schematów (20 ręcznych + 30 syntetycznych)
  ↓
Trening YOLOv8 (100 epok)
  ↓
Ewaluacja: mAP, precision, recall
  ↓
mAP > 0.7? ──NO──> Popraw dataset (więcej próbek, lepsze anotacje)
  ↓ YES              ↓
MVP 0.2: +5-7 klas   Refactor modelu (augmentacje, hiperparametry)
  ↓                  ↓
Ponowny trening      Ponowny trening
  ↓
Nowe klasy accuracy > 0.65? ──NO──> Więcej danych dla nowych klas
  ↓ YES
MVP 0.3: Subklasy specjalistyczne
  ↓
Transfer learning (fine-tuning z większym datasetem)
  ↓
Production-ready model
```

---

## Praktyczne wskazówki anotacji

### Priorytet anotacji (MVP 0.1)

**Wysokie priority** (annotuj WSZYSTKIE wystąpienia):
1. `ground` – **critical** dla netlisty
2. `power` – **critical** dla netlisty
3. `resistor` – najbardziej powszechny
4. `capacitor` – bardzo częsty
5. `ic` – ważny, często wielopinowy

**Średnie priority** (annotuj większość):
6. `transistor` – ważny, ale rzadszy
7. `diode` – średnio częsty

**Niskie priority** (annotuj jeśli widoczne):
8. `inductor` – rzadki w schematach cyfrowych
9. `connector` – często na brzegach schematu

### Wytyczne jakości

**Bbox powinien**:
- ✅ Obejmować cały symbol (bez clipowania)
- ✅ Minimalizować margin (ciasno wokół symbolu)
- ✅ Uwzględniać oznaczenia (R1, C2) jeśli są blisko
- ❌ NIE obejmować długich linii połączeń
- ❌ NIE nakładać się z innymi bbox (jeśli możliwe)

**Trudne przypadki**:
- **Symbole połączone**: Anotuj każdy oddzielnie (np. mostek prostowniczy = 4 diody)
- **IC z opisem funkcji**: Bbox tylko symbol, nie cały blok tekstu
- **Ground/Power wielokrotne**: Każde wystąpienie osobno
- **Symbole niewyraźne**: Pomiń (lepiej mniej, ale pewne anotacje)

---

## Struktura kodu dla klas (przyszłość)

### Plik konfiguracyjny klas

```python
# talk_electronic/services/symbol_detection/class_registry.py

"""
Registry klas symboli elektronicznych z wersjonowaniem.
"""

# Wersja 1: MVP 0.1 (podstawowe 9 klas)
SYMBOL_CLASSES_V1 = [
    'resistor',
    'capacitor',
    'inductor',
    'diode',
    'transistor',
    'ic',
    'connector',
    'ground',
    'power',
]

# Wersja 2: MVP 0.2 (+5-7 klas)
SYMBOL_CLASSES_V2 = SYMBOL_CLASSES_V1 + [
    'op_amp',
    'switch',
    'relay',
    'transformer',
    'crystal',
    'fuse',
    'voltage_source',
]

# Wersja 3: Subklasy specjalistyczne
SYMBOL_CLASSES_V3 = SYMBOL_CLASSES_V2 + [
    'bjt_npn', 'bjt_pnp',
    'mosfet_n', 'mosfet_p',
    'diode_schottky', 'diode_zener', 'led',
    'potentiometer', 'varistor',
]

# Aktywna wersja (zmień przy upgrade)
ACTIVE_CLASSES = SYMBOL_CLASSES_V1
ACTIVE_VERSION = 'v1'

# Mapowanie do prefiksów SPICE
SPICE_PREFIX_MAP = {
    'resistor': 'R',
    'capacitor': 'C',
    'inductor': 'L',
    'diode': 'D',
    'transistor': 'Q',
    'ic': 'U',
    'ground': 'GND',
    'power': 'VCC',
    # ... extend for V2, V3
}

# Tłumaczenia UI (opcjonalnie)
CLASS_TRANSLATIONS_PL = {
    'resistor': 'Rezystor',

### Testy end-to-end (E2E) — wyjaśnienie dla laika

Testy "end-to-end" (E2E) to sposób sprawdzania całej aplikacji dokładnie tak, jakby korzystał z niej prawdziwy użytkownik.
Wyobraź sobie kogoś, kto siada przed przeglądarką i klika przyciski, wczytuje pliki i sprawdza czy wszystko działa — E2E robi to automatycznie.

Dlaczego to ważne?
- Pokazuje czy wszystkie części aplikacji współpracują razem (frontend, backend, pliki, baza) — nie tylko pojedyncze kawałki.
- Odkrywa błędy, które mogą pojawić tylko kiedy kilka rzeczy zadziała w określonej kolejności (np. transfer obrazu z zakładki Binaryzacja do zakładki Retusz).
- Pomaga szybko wykryć regresje gdy wprowadzamy nowe zmiany — test E2E powiadomi nas, jeśli coś przestanie działać.

Jak to działa w tym projekcie (w skrócie):
- Test uruchamia przeglądarkę w trybie automatycznym, otwiera aplikację i symuluje kliknięcia, upload, transfer do retuszu i ładowanie wyniku.
- Jeśli któryś krok się nie powiedzie (np. obraz nie załaduje się w panelu retuszu), test się nie powiedzie i poinformuje programistów.

Gdzie są przykładowe pliki (scaffold): `tests/e2e/playwright.config.js` i `tests/e2e/home.spec.js` — to przykładowy test który sprawdza, że aplikacja się uruchamia i widoczny jest przycisk "Załaduj wynik z binaryzacji".

Jeśli chcesz, mogę dodać szczegółowy test UI (Playwright), instrukcję instalacji i uruchomienia oraz integrację w CI (GitHub Actions) — krok po kroku.
    'capacitor': 'Kondensator',
    'inductor': 'Cewka',
    'diode': 'Dioda',
    'transistor': 'Tranzystor',
    'ic': 'Układ scalony',
    'connector': 'Złącze',
    'ground': 'Masa',
    'power': 'Zasilanie',
}

def get_class_list(version='v1'):
    """Zwraca listę klas dla danej wersji."""
    versions = {
        'v1': SYMBOL_CLASSES_V1,
        'v2': SYMBOL_CLASSES_V2,
        'v3': SYMBOL_CLASSES_V3,
    }
    return versions.get(version, SYMBOL_CLASSES_V1)

def get_spice_prefix(class_name):
    """Mapuje klasę symbolu na prefix SPICE."""
    return SPICE_PREFIX_MAP.get(class_name, 'X')

def translate_class(class_name, lang='pl'):
    """Tłumaczy nazwę klasy na język UI."""
    if lang == 'pl':
        return CLASS_TRANSLATIONS_PL.get(class_name, class_name)
    return class_name  # Default: English
```

---

## Metryki sukcesu (per faza)

### MVP 0.1 (9 klas)
- **Dataset**: Min. 50 schematów zanotowanych
- **mAP**: > 0.5 (akceptowalne dla prototypu)
- **Per-class precision**: > 0.6 dla wszystkich klas
- **Inference time**: < 500ms na CPU (Intel i5/Ryzen 5)
- **Czas anotacji**: < 10 min/schemat

### MVP 0.2 (14-16 klas)
- **Dataset**: Min. 100 schematów
- **mAP**: > 0.65
- **Per-class precision**: > 0.7 dla klas V1, > 0.5 dla nowych klas V2
- **Inference time**: < 700ms na CPU

### Post-MVP (25+ klas)
- **Dataset**: 500+ schematów
- **mAP**: > 0.75
- **Per-class precision**: > 0.8 dla wszystkich klas
- **Inference time**: < 1s na CPU, < 100ms na GPU

---

## Najczęstsze błędy (do unikania)

### ❌ Błąd 1: Za dużo klas od razu
- **Problem**: 30 klas w MVP → długi trening, niski accuracy
- **Rozwiązanie**: Start z 9 klas, rozszerzaj iteracyjnie

### ❌ Błąd 2: Niekonsekwentne nazewnictwo
- **Problem**: Mieszanie angielskiego/polskiego → chaos w kodzie
- **Rozwiązanie**: Konsekwentnie angielskie w ML, polskie tylko w UI

### ❌ Błąd 3: Zbyt ogólne klasy
- **Problem**: Jedna klasa "component" dla wszystkiego → model nie uczy się
- **Rozwiązanie**: Wyraźnie rozdzielone klasy (resistor ≠ capacitor)

### ❌ Błąd 4: Zbyt szczegółowe subklasy za wcześnie
- **Problem**: bjt_npn vs bjt_pnp w MVP → za mało danych per klasa
- **Rozwiązanie**: Start z "transistor" (ogólnie), potem split

### ❌ Błąd 5: Pomijanie ground/power
- **Problem**: Focus na komponentach, ignorowanie węzłów → niepełna netlist
- **Rozwiązanie**: Ground/power są **critical** – anotuj wszystkie!

---

## Checklist przed startem anotacji

- [ ] Label Studio zainstalowane i działające
- [ ] Projekt utworzony z nazwą "Electronic Symbols Detection"
- [ ] Dodane 9 klas z XML template (kolorami)
- [ ] Przeczytane wytyczne anotacji (bbox guidelines)
- [ ] Przygotowane 10-20 PNG z różnorodnych schematów (300 DPI)
- [ ] Backup strategy ustalone (`~/.label-studio/` → external drive)
- [ ] Zdefiniowany cel pierwszej sesji (5 schematów zanotowanych)

---

## Następne kroki (po tej dokumentacji)

1. **Teraz**: Zainstaluj Label Studio (`conda create -n label-studio python=3.11`)
2. **Potem**: Skonfiguruj projekt z 9 klasami podstawowymi
3. **Następnie**: Wyeksportuj 10 PNG z aplikacji Flask
4. **Dalej**: Rozpocznij pierwszą sesję anotacji (cel: 5 schematów)
5. **Na koniec**: Eksport COCO + walidacja → `data/annotations/coco_batch_001.json`

---

**Dokument wersja**: 1.0
**Data utworzenia**: 2025-11-06
**Autor**: GitHub Copilot + robetr286
**Status**: Gotowy do implementacji
