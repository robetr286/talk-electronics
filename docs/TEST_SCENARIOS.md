# Scenariusze testów end-to-end

## Scenariusz A – PDF z repo

### PDF workspace
1. Wczytaj `schemat_07.pdf` z repozytorium
2. Przejdź po wszystkich stronach, sprawdź:
   - Miniatury wyświetlają się poprawnie
   - Zoom i panning działają płynnie
   - Overlay RODO pojawia się przy pierwszym wejściu
3. Zapisz stronę do historii (przycisk „Zapisz stronę do historii")
4. Upewnij się, że wpis ma miniaturę i poprawny timestamp

### Przygotowanie obrazu
1. Przejdź do zakładki „Kadrowanie"
2. Zaznacz fragment schematu (prostokątne lub wielokątne zaznaczenie)
3. Zatwierdź i zapisz na serwer
4. W zakładce „Binaryzacja":
   - Wykonaj binaryzację Sauvola lub ręczny próg
   - Sprawdź podgląd przed/po
5. W zakładce „Retusz":
   - Wykonaj drobną poprawkę (np. usunięcie artefaktu pędzlem)
   - Zapisz finalny fragment do historii (checkbox + „Zapisz wynik")

### Detekcja symboli
1. Wybierz źródło „Aktualny fragment" lub wpis z historii
2. Detektor: `yolov8`, próg domyślny (~0.5)
3. Zaznacz „Zapisz wynik w historii"
4. Uruchom detekcję
5. Sprawdź:
   - Nakładka z bounding boxes (zoom/panning)
   - Tabela wyników z listą wykrytych symboli
   - Link do historii detekcji
   - Podświetlenie symbolu po kliknięciu w tabelę

### Segmentacja linii + netlista
1. Uruchom segmentację linii na przetworzonym obrazie
2. Potwierdź, że wpis trafia do historii (`type=segments`)
3. Po detekcji wybierz `symbolHistoryId` lub bieżący wynik w panelu netlisty
4. Wygeneruj netlistę, zobacz:
   - Highlight komponentów na canvas
   - Tabelę węzłów i krawędzi
   - Status netlisty (liczba essential/non-essential edges)
5. Wyeksportuj SPICE
6. Sprawdź status oraz plik `.cir` w folderze `uploads`

### Weryfikacja historii
1. Dropdown historii powinien zawierać wpisy:
   - `type=page` (strony PDF)
   - `type=processed` (binaryzacja)
   - `type=symbols` (detekcja)
   - `type=segments` (segmentacja)
2. Po akcji „Wyczyść historię (image-processing)" sprawdź:
   - Wpisy `processed` i `page` są usunięte
   - Wpisy `symbols` i `segments` nadal istnieją

### Notatki
- Zapisz latencję YOLO (ms)
- Ewentualne błędy/UI-glitche
- Ostrzeżenia w konsoli przeglądarki
- Błędy w terminalu Flask

---

## Scenariusz B – Lokalny PNG po retuszu

### Import
1. W zakładce „Wczytaj plik" wybierz retuszowany PNG z dysku
2. Sprawdź metadane:
   - Rozmiar obrazu
   - DPI (jeśli dostępne)
3. W razie potrzeby zastosuj binaryzację lub deskew

### Historia
1. Zapisz wejściowy plik do historii (`type=upload`)
2. Przeprowadź minimalny retusz:
   - Np. pędzel w zakładce „Canvas Retouch"
   - Zapisz wynik jako `processed`
3. Sprawdź, że oba wpisy (upload + processed) mają miniatury

### Detekcja symboli
1. Uruchom detektor `yolov8` na retuszowanym obrazie
2. Zapisz wynik w historii
3. Zweryfikuj highlighty:
   - Klik w tabeli → podgląd symbolu
   - Ukrywanie nakładki przełącznikiem

### Segmentacja i netlista
1. Wybierz segmentację z tego samego obrazu (manual upload)
2. Sprawdź, że netlista:
   - Integruje się z wynikami detekcji symboli
   - Highlightuje komponenty na canvas
   - Eksportuje poprawny plik SPICE

### Regresja błędów
- Szybko przełączaj zakładki podczas ładowania
- Obserwuj, czy pojawia się „pusty obszar" w kadrowania
- Zanotuj, jeśli PDF nie wyświetla się automatycznie

---

## Scenariusz C – Świeży upload (nowy PDF/PNG z dysku)

### Upload
1. Wgraj nowy plik (nieobecny wcześniej w repo)
2. Przejdź podstawowy workflow:
   - Kadrowanie → Binaryzacja → Retusz
   - Zapisz każdy krok do historii
3. Sprawdź, czy wszystkie wpisy mają poprawne timestampy

### Detekcja
1. Uruchom `yolov8` z niższym progiem (np. 0.2)
2. Zapisz wynik
3. Sprawdź, czy nowy wpis w historii odróżnia się timestampem
4. Zweryfikuj, że wykryto więcej symboli przy niższym progu

### Segmentacja
1. Uruchom segmentację
2. Obserwuj logi w terminalu Flask:
   - Czy brak błędów?
   - Czy operacje skeletonizacji/węzłów przebiegają poprawnie?
3. Podświetl maski/linie na canvas
4. Wyłącz/włącz nakładkę, aby upewnić się, że UI reaguje

### Cleanup
1. Użyj „Wyczyść historię" (pełny zakres)
2. Upewnij się, że usunięto wpisy tylko z aktualnego pliku
3. Usuń plik z folderu `uploads` (dla porządku)
4. Odnotuj, że cleanup działa poprawnie

---

## Weryfikacja końcowa (dla wszystkich scenariuszy)

1. **Historia na dysku**
   - Sprawdź `processing-history.json`
   - Czy wpisy są poprawnie pogrupowane po `scope`?
   - Czy metadane zawierają `previewUrl`, `createdAt`, `label`?

2. **Logi i dokumentacja**
   - Zanotuj w `PROGRESS_LOG.md` wyniki:
     - Pass/fail dla każdego scenariusza
     - Użyte pliki
     - Napotkane problemy
   - Jeśli coś poszło nie tak:
     - Dodaj wzmiankę do `DEV_PROGRESS.md`
     - Otwórz ticket w `TODO` lub `robert_to_do.md`

3. **Zatrzymanie serwera**
   - Naciśnij Ctrl+C w terminalu Flask
   - Sprawdź, czy cleanup przy zamknięciu działa

---

## Czecklista przed commitem

- [ ] Wszystkie scenariusze przetestowane (A, B, C)
- [ ] Historia zapisuje się poprawnie
- [ ] Detekcja symboli działa z różnymi progami
- [ ] Segmentacja + netlista integrują się
- [ ] Eksport SPICE generuje poprawny plik
- [ ] UI reaguje na przełączanie zakładek
- [ ] Brak błędów w konsoli/terminalu
- [ ] Dokumentacja zaktualizowana
- [ ] Commit message opisuje zmiany
