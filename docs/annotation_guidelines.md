# Wytyczne dotyczące anotacji

Ten dokument służy do koordynacji procesu etykietowania danych dla modeli detekcji symboli.

## Minimalny zakres zbioru danych
- Zgromadź co najmniej 600 zaanotowanych schematów obejmujących 12 podstawowych klas symboli (rezystory, kondensatory, wzmacniacze operacyjne, złącza, linie zasilania, masy, diody, tranzystory, piny układów scalonych, etykiety sieci, punkty pomiarowe, symbole różne).
- Dąż do minimum 10 tys. ramek ograniczających, z co najmniej 500 przykładami na klasę; klasy z długiego ogona można uzupełnić syntetycznie.
- Przechowuj surowe pliki w `data/raw/<source>/<file>` i uzupełniaj metadane pochodzenia w `data/index.csv` (kolumny: `source`, `license`, `format`, `notes`, `split_lock`).

## Format anotacji
- Preferowany format: **COCO bounding box detection** eksportowany jako JSON; rotację zapisujemy oddzielnie w `bbox_rotation` (stopnie) wewnątrz pola `attributes`.
- Struktura plików w `data/annotations/`:
  - `train.json`
  - `val.json`
  - `test.json`
  - `class_mapping.json` (autorytatywne odwzorowanie `category_id` na nazwę i kolor).
- Wymagane pola COCO dla każdej anotacji:
  - `bbox`: `[x, y, width, height]` w pikselach bezwzględnych.
  - `category_id`: liczba całkowita odnosząca się do listy `categories`.
  - `image_id`, `id`: liczby całkowite; utrzymuj stałe wartości między eksportami.
  - `attributes`: obiekt z opcjonalnymi polami `bbox_rotation`, `confidence_hint`, `annotator`.

### Przykładowy wpis
```
{
  "images": [
    {"id": 101, "file_name": "sheet_001.png", "height": 2048, "width": 3072}
  ],
  "annotations": [
    {
      "id": 9001,
      "image_id": 101,
      "category_id": 3,
      "bbox": [412.5, 820.0, 128.0, 96.0],
      "area": 12288.0,
      "iscrowd": 0,
      "attributes": {"bbox_rotation": 0.0, "annotator": "labeler_a"}
    }
  ],
  "categories": [
    {"id": 1, "name": "resistor"},
    {"id": 2, "name": "capacitor"},
    {"id": 3, "name": "op_amp"}
  ]
}
```
  ## Polityka podziału zbioru
  - Stosuj próbkowanie warstwowe według schematu, aby uniknąć przecieków; nadawaj unikalne identyfikatory schematów w `data/index.csv`.
  - Zablokuj podziały walidacyjne/testowe poprzez kolumnę `split_lock` (wartości: `train`, `val`, `test`, `auto`).
  - Utrzymuj deterministyczne podziały skryptem `scripts/split_dataset.py --seed 20251031` (do przygotowania wraz z potokiem przetwarzania).

  ## Lista kontrolna jakości
  - Ramki ograniczające muszą pozostawać w granicach obrazu, z szerokością/wysokością ≥ 4 piksele.
  - Odrzucaj anotacje o stosunku boków > 10 dla symboli o kształcie kwadratu, chyba że towarzyszy im rotacja.
  - Wymagaj podwójnej weryfikacji dla klas z F1 < 0,75 w ostatniej ewaluacji; stan recenzji zapisuj w `attributes.review_state` (`pending`, `approved`, `needs_fix`).
  - Notatki anotatora zapisuj w `attributes.comment` (czysty ASCII, maks. 120 znaków).

  ### Wskazówki dotyczące kadrowania ramek
  - Rysuj ramki tak, by obejmowały cały symbol, zostawiając równy bufor 2–4 px; unikniesz obcięcia geometrii.
  - Nie obejmuj sąsiednich symboli ani etykiet w tej samej ramce; gdy to trudne, zostaw bufor po stronie o najmniejszym zagęszczeniu.
  - Dla regionów `ic_pin` wyrównuj ramkę do korpusu pinu wraz z krótkim odcinkiem przewodu; utrzymuj wysokość ramek pinów w obrębie jednego obrazu w granicach ±10%.
  - Zaznaczaj obrys `ic` dopiero po pinach; zablokuj piny w panelu Label Studio przed rysowaniem większej ramki, żeby nie przesunąć ich przypadkiem.
  - Przy `connector` obejmuj ramką całe gniazdo wraz z oznaczeniem typu `J1`, `JS01` i numeracją pinów – nie twórz osobnych ramek dla samych opisów.
  - Znaków polaryzacji przy `capacitor` (np. `+`) nie oznaczaj osobno; poszerz ramkę kondensatora tak, by objęła ten znacznik, nawet jeśli znajduje się tuż obok elementu.
- Wszystkie fragmenty, które nie są częścią schematu (logo producenta, instrukcje tekstowe, zdjęcia PCB, paski kalibracyjne, zabrudzone marginesy) oznaczaj osobną ramką `ignore_region`, żeby preprocessing mógł je łatwo wyciąć.
- Annotate the parent `ic` outline after pins; lock pin regions in the Label Studio sidebar before drawing the larger `ic` box so accidental moves are prevented.

### Strefy ignorowane (`ignore_region`)
- Rysuj `ignore_region` wtedy, gdy na obrazie występuje element graficzny niebędący częścią schematu – np. logo, instrukcja obsługi, artefakty skanu, suwak z parametrami.
- Nie dodawaj metadanych ani komentarzy do tego labela; jego jedyną rolą jest umożliwić pipeline'owi pominięcie tych pikseli.
- Jeśli elementów jest kilka (np. logo + legenda), narysuj osobne regiony, aby łatwiej było je maskować selektywnie.

### Uszkodzone połączenia (`broken_line`)
- Zaznacz `broken_line`, gdy na schemacie linia przewodu jest fizycznie przerwana, choć powinna tworzyć ciągły obwód (np. brakujący fragment po skanie, zerwany kawałek eksportu).
- Region rysuj wąskim prostokątem (ok. 3–4 px szerokości) dokładnie wzdłuż brakującego segmentu; jeśli szczelina jest szersza, możesz narysować dwa prostokąty na obu końcach.
- W starszych zadaniach możesz natrafić na poligony `broken_line`; zostaw je w tym formacie lub miękko popraw, ale nowe oznaczenia twórz wyłącznie prostokątem.
- W metadanych **zawsze** wpisuj `type=broken_line reason=<opis> severity=<minor|major|critical>`:
  - `reason` opisuje przyczynę (np. `reason=scan_gap_pin3`); minimum 6 znaków, bez spacji na końcach.
  - `severity` określa wpływ na analizę: `minor` (kosmetyczne), `major` (łamie pojedynczy obwód), `critical` (odcina wiele gałęzi lub zasilanie).
- W przypadku wielu przerw na jednej linii dodaj osobne regiony, żeby w raporcie łatwiej identyfikować miejsca wymagające naprawy.

### Łącza między arkuszami (`edge_connector`)
- Używaj `edge_connector`, gdy przewód kończy się na krawędzi strony, a dalszy ciąg znajduje się na innym arkuszu PDF.
- Preferuj mały prostokąt (Rectangle tool) obejmujący końcówkę linii i podpis (utrzymuj szerokość do kilku pikseli, długość do ~25 px). Polygon rysuj tylko jeśli przewód jest skośnie i prostokąt łapałby zbędne elementy.
- W `region_comment` wpisuj minimum `type=edge_connector edge_id=<kod> page=<nr_strony>` i opcjonalne `note=<dokąd prowadzi>`.
- Konwencja `edge_id`: `A`, `B`, `C`, `D` oznaczają odpowiednio lewą, prawą, górną i dolną krawędź arkusza; dwucyfrowy numer (`01–99`) to kolejny punkt na tej krawędzi liczony od góry/od lewej. Przykład: `edge_id=A05` → lewa krawędź, piąty konektor.
- Pole `page` przepisuj z widocznego numeru na schemacie (jeśli brak – użyj numeru logicznego przyjętego w projekcie, start od 1).
- `note` opisz kierunek kontynuacji (np. `note=to_sheet3`, `note=section_B`), aby QA mogło łatwo odnaleźć parę.
