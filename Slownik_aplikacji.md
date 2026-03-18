# Slownik aplikacji

| Nazwa oryginalu | Opis | Kategoria (wg informatyki) | Zastosowanie w naszej aplikacji |
| --- | --- | --- | --- |

# Sanity check

    [opis] Krótki, szybki test „zdrowego rozsądku”, który ma potwierdzić, że pipeline lub wynik nie jest oczywiście zepsuty (np. 1 epoka na małym secie, szybka walidacja na realnym próbniku).

    [kategoria] Kontrola jakości / testy szybkie

    [zastosowanie] Używamy sanity checków przed długimi runami: krótki train/val na małym zestawie, podgląd overlayów i metryk, aby nie marnować GPU na błędnej konfiguracji.

 # DigitalOcean

    [opis] Platforma chmurowa udostepniajaca serwery i uslugi do hostowania aplikacji internetowych.

    [kategoria] Chmura / infrastruktura

    [zastosowanie] Docelowe srodowisko wdrozeniowe dla aplikacji; np. uruchomienie backendu Flask na   Droplecie z podpiętym wolumenem `uploads/`. |

# Generowanie masek ignorow

    [opis] Proces tworzenia obrazow-mask, ktore oznaczaja fragmenty schematu do pominiecia w analizie.

    [kategoria] Przetwarzanie obrazow / pipeline AI

    [zastosowanie] Mieszamy poligony i sciezki pędzla w jeden plik PNG przechowywany w `uploads/ignore-regions/masks`, aby logika detekcji wiedziala, ktorych pikseli nie analizowac.

# Flask

    [opis] Lekki framework Pythona do tworzenia serwisow HTTP i API.

    [kategoria] Framework webowy

    [zastosowanie] Rdzen aplikacji backendowej (`app.py`, blueprinty, routing).

# IgnoreRegionStore

    [opis] Serwis aplikacyjny przechowujacy metadane stref ignorowanych (JSON) oraz maski PNG.

    [kategoria] Logika domenowa / storage

    [zastosowanie] Obsluguje API `/api/ignore-regions`, zapisuje wpisy w `uploads/ignore-regions`, udostepnia liste oraz szczegolowe dane. |

# Playwright
    [opis] Zestaw narzedzi do end-to-end testow przegladarkowych.

    [kategoria] Testy automatyczne

    [zastosowanie] Planowane scenariusze E2E: tworzenie/edycja ignorow, weryfikacja cofania i smoke-testy hooka QA.


# Pipeline

    [opis] Ciag uporzadkowanych krokow, ktore przetwarzaja dane od wejscia do gotowego wyniku.

    [kategoria] Architektura oprogramowania / przetwarzanie danych

    [zastosowanie] Nasz pipeline detekcji laczy kroki (render PDF -> generowanie masek -> YOLO), dlatego kazdy etap (np. ignorowanie pikseli) musi dostarczyc poprawne dane kolejnym modulom.

# Backlog

    [opis] Lista zadań i pomysłów, które należy wykonać lub rozważyć w przyszłości; elementy na tej liście są zwykle uporządkowane według priorytetu.

    [kategoria] Zarządzanie projektem / planowanie pracy

    [zastosowanie] Używamy backlogu do przechowywania zadań dotyczących naprawy szkieletów (np. integracja lokalnych napraw, testy, prototyp grafowy).

# Weights

    [opis] Pliki wag modelu (np. `best.pt`, `last.pt`, `epoch*.pt`) zawierające wytrenowane parametry sieci neuronowej.

    [kategoria] Artefakty modelu / ML

    [zastosowanie] Pliki wag przechowujemy w katalogach eksperymentów (`runs/segment/<run>/weights`) i używamy ich do inferencji, dalszego fine‑tuningu lub do porównania wyników między runami.
 Elementy z backlogu z czasem trafiają do konkretnych zadań/pr-ów.

# Wagi (synonim: weights)

    [opis] Pliki zawierające wytrenowane parametry modelu. W naszym projekcie typowo `yolov8s-seg.pt` lub checkpointy z `runs/segment/.../weights`.

    [kategoria] Artefakty modelu / ML

    [zastosowanie] Trzymamy je w `weights/` lub w katalogach runów. Aplikacja przy detekcji symboli najpierw szuka ścieżki w `TALK_ELECTRONIC_YOLO_WEIGHTS`, a jeśli brak, używa domyślnych lokalizacji (np. `weights/yolov8s-seg.pt`).


# Pillow

    [opis] Biblioteka graficzna Pythona pozwalajaca latwo tworzyc i modyfikowac obrazy.

    [kategoria] Przetwarzanie obrazow

    [zastosowanie] Uzywana do rysowania masek PNG dla stref ignorowanych (funkcje `_write_mask`, `_draw_brush`).


# PyMuPDF
    [opis] Biblioteka Pythona do odczytu i renderowania PDF (zrodlowa nazwa modulu `fitz`).

    [kategoria] Przetwarzanie dokumentow

    [zastosowanie] Renderuje podglady stron PDF w `/api/pdf/...`; jezeli brak biblioteki, zwracamy blad 503. |


# Token autoryzacyjny

    [opis] Ustalony sekret przekazywany w naglowku HTTP, ktory potwierdza, ze klient ma prawo modyfikowac dane.

    [kategoria] Bezpieczenstwo API

    [zastosowanie] Konfigurowalny klucz `IGNORE_REGIONS_TOKEN` wymagany przy POST/PUT/DELETE `/api/ignore-regions` (np. naglowek `X-Ignore-Token`). |

# CI

    [opis] CI (Continuous Integration) - zautomatyzowany system budowy i testowania kodu przy każdym commicie/PR.

    [kategoria] DevOps / testowanie

    [zastosowanie] W repozytorium używamy CI do uruchamiania testów jednostkowych, smoke E2E oraz gating (pre-merge checks) w celu wykrycia regresji.

# PR-y

    [opis] Pull Request (PR) - zgłoszenie zmian do przeglądu i scalenia z główną gałęzią projektu.

    [kategoria] Procesy rozwojowe / code review

    [zastosowanie] Zamiast jednej dużej zmiany preferujemy rozbijanie PR-ów na mniejsze części (worker, testy, gating), co ułatwia przegląd i szybsze wdrożenia.

# Pull requesty w trybie draft

    [opis] Pull requesty można otwierać w trybie _draft_ (wersja robocza), co oznacza, że PR jest widoczny do przeglądu, ale nie gotowy do scalania.

    [kategoria] Procesy rozwojowe / code review

    [zastosowanie] Używamy draft PR-ów, żeby wystawić zmiany do wstępnego przeglądu i zebrać opinie zanim uznamy je za gotowe do formalnego review i scalania.

# boto3

    [opis] Oficjalny SDK (zestaw narzędzi programistycznych) Amazona do komunikacji z usługami AWS z poziomu Pythona. Pozwala m.in. wysyłać pliki do S3, wywoływać Textract, zarządzać kolejkami SQS itp.

    [kategoria] Biblioteka Pythona / AWS / chmura

    [zastosowanie] Używamy boto3 do wysyłania obrazów schematów do usługi AWS Textract (OCR w chmurze) i odbierania wyników rozpoznawania tekstu. Import `boto3` jest wymagany przez blueprint `textract_bp` — dlatego musi być zainstalowany także w środowisku testowym CI (`requirements-test.txt`), nawet jeśli testy nie łączą się z AWS.

# Bresenham

    [opis] Algorytm Bresenhama — efektywna metoda rasteryzacji kreski (linie) na siatce pikseli bez użycia operacji zmiennoprzecinkowych.

    [kategoria] Grafika / algorytmy binarne

    [zastosowanie] Używamy go w modułach łączenia punktów końcowych (endpoints) i rysowania prostych linii między nimi w lokalnej naprawie szkielety.

# Endpoints

    [opis] Punkty końcowe (endpoints) — piksele w szkielecie grafiki, które mają tylko jedno sąsiednie sąsiedztwo (koniec linii).

    [kategoria] Przetwarzanie obrazów / analiza grafów

    [zastosowanie] Metryka redukcji liczby endpoints jest jednym z kryteriów oceny naprawy szkiele­tów — zmniejszenie liczby endpoints zwykle oznacza lepsze połączenie przerw w linii.

# gating

    [opis] Mechanizm blokujący (gating) — skrypt lub proces, który weryfikuje wyniki eksperymentów przed akceptacją zmian (np. w PR).

    [kategoria] Testy regresji / kontrola jakości

    [zastosowanie] Mamy prosty gating/regresję, która uruchamia worker (local_patch_repair_worker) i waliduje `local_results.json` przeciwko progom akceptacji (IoU, redukcja endpoints).

# worker

    [opis] Worker — proces lub skrypt uruchamiający długotrwałe zadania przetwarzania (np. lokalne naprawy lub batch validation).

    [kategoria] Architektura / procesy asynchroniczne

    [zastosowanie] `scripts/local_patch_repair_worker.py` jest przykładem worker'a, uruchamianego zwykle przez watchdog lub CI.

# main

    [opis] Główna gałąź repozytorium (`main`) — miejsce, do którego trafiają zweryfikowane i zaakceptowane zmiany.

    [kategoria] Kontrola wersji / zarządzanie gałęziami

    [zastosowanie] PR-y powinny być weryfikowane i przejść gating przed scaleniem do `main`.

# isort

    [opis] isort — narzędzie formatujące importy w plikach Pythona (porządkuje i grupuje importy).

    [kategoria] Narzędzia formatowania / pre-commit

    [zastosowanie] `isort` jest skonfigurowany w pre-commit hooks, by zapewnić kompatybilny styl importów przed commitem.

# flake8

    [opis] flake8 — linter Pythona, wykrywający błędy stylu i potencjalne problemy w kodzie.

    [kategoria] Statyczna analiza kodu

    [zastosowanie] Flake8 działa w pre-commit aby wychwycić proste błędy i niespójności przed spushowaniem zmian.

# trim trailing whitespace

    [opis] Pre-commit hook usuwający nadmiarowe spacje na końcach linii.

    [kategoria] Czyszczenie kodu / pre-commit

    [zastosowanie] Chroni repo przed zbędnymi różnicami whitespace w historii.

# fix end of files

    [opis] Pre-commit hook zapewniający końcowy nowy wiersz i poprawki końców plików.

    [kategoria] Formatowanie plików / pre-commit

    [zastosowanie] Zapewnia spójność i kompatybilność plików między różnymi edytorami i systemami.

# Mock UI

    [opis] Prosty, tymczasowy interfejs udający odpowiedź backendu/modelu, pozwalający obejrzeć i przetestować ekran zanim powstanie prawdziwa logika.

    [kategoria] Prototypowanie / UX

    [zastosowanie] Dodajemy przycisk lub akcję, która zwraca zaszyte na sztywno przykładowe dane (np. wykryte złącza krawędziowe) i rysuje je na canvasie, żeby szybko ocenić ergonomię bez czekania na gotowy backend/ML.

# check yaml

    [opis] Pre-commit hook weryfikujący poprawność plików YAML (syntax + parse).

    [kategoria] Kontrola konfiguracji / pre-commit

    [zastosowanie] Chroni przed błędnymi plikami konfiguracyjnymi YAML w repo.

# check for added large files

    [opis] Pre-commit sprawdzający dodawane pliki pod kątem zbyt dużych rozmiarów.

    [kategoria] Zarządzanie artefaktami / pre-commit

    [zastosowanie] Zabezpiecza repo przed przypadkowym dodaniem dużych binariów (ciężkich wag modeli).

# check json

    [opis] Pre-commit hook sprawdzający poprawność plików JSON.

    [kategoria] Kontrola konfiguracji / pre-commit

    [zastosowanie] Zapobiega committowaniu uszkodzonych lub nieprawidłowych plików JSON.

# check for merge conflicts

    [opis] Pre-commit hook wykrywający fragmenty konfliktów scalania (np. `<<<<<<<`) przed commitem.

    [kategoria] Bezpieczeństwo historii / pre-commit

    [zastosowanie] Zapewnia, że konflikty scalania nie trafią do głównej historii projektowej.

# debug

# PoC

    [opis] Proof of Concept (PoC) — szybkie, eksperymentalne uruchomienie minimalnego pipeline'u lub modelu, które ma na celu zweryfikowanie wykonalności koncepcji przed pełnym wdrożeniem.

    [kategoria] Prototypowanie / walidacja techniczna

    [zastosowanie] Używamy PoC do szybkich testów modeli, pipeline'ów lub integracji (np. testy porównawcze YOLO vs Mask R‑CNN vs Detectron2/Mask2Former) na małym zbiorze danych, aby ocenić jakość i koszty przed uruchomieniem dłuższych eksperymentów.

# Batch

    [opis] Liczba przykładów (obrazów) przetwarzanych jednocześnie w jednym kroku uczenia (forward/backward) lub wsadowaniu inferencji.

    [kategoria] Hiperparametr / konfiguracja treningu

    [zastosowanie] Parametr wpływa na throughput i zużycie pamięci GPU; na lokalnym A2000 zwykle używamy `batch=1`. Zwiększanie `batch` poprawia stabilność gradientów i przepustowość, ale wymaga więcej VRAM i może wymagać dostosowania LR (np. liniowe skalowanie). Dla porównań modeli trzymaj `batch` stały (np. 1) by porównanie czasów było rzetelne.

    [opis] Proces analizowania i diagnozowania problemów w kodzie lub plikach konfiguracyjnych.

    [kategoria] Rozwój / naprawa błędów

    [zastosowanie] W repo używamy trybu debug, logów i specjalnych folderów `debug/` do rejestrowania artefaktów i analizy regresji.

# Heurystyka

    [opis] Prosta, regułowa metoda lub przybliżenie wykorzystywane zamiast pełnego modelu/statystyki, zwykle szybsza, ale nie zawsze poprawna w 100% przypadków.

    [kategoria] Algorytmy przybliżone / inżynieria cech

    [zastosowanie] W postprocessingu Textract używamy heurystyk łączenia etykiet z wartościami (pasy pionowe/prawe, ograniczenia dla układów IC), aby ograniczyć błędne parowania bez trenowania dodatkowego modelu.

# Hash

    [opis] Skrót kryptograficzny – ciąg ograniczonej długości wynikający z przetworzenia danych wejściowych, używany do identyfikacji lub weryfikacji integralności.

    [kategoria] Bezpieczeństwo / uwierzytelnianie / integralność danych

    [zastosowanie] W systemie przechowujemy hashe haseł (np. PBKDF2‑SHA256) zamiast samych haseł oraz wykorzystujemy sumy kontrolne plików/modeli do sprawdzania, czy nie uległy modyfikacji.

# Budowanie słownika szumów iteracyjne

    [opis] Iteracyjne gromadzenie wzorców fałszywych odczytów OCR (szumów), które są dodawane do filtra postprocessingu w miarę testowania kolejnych schematów. Każdy nowy wariant błędnego odczytu (np. symbol masy odczytany jako „777", „III", „m", „1") zostaje trwale dodany do reguł filtrujących i działa na wszystkie przyszłe schematy.

    [kategoria] Postprocessing OCR / kontrola jakości

    [zastosowanie] W pipeline Textract funkcja `_should_drop_noise()` zawiera rosnący zestaw reguł filtrujących szumy zidentyfikowane na kolejnych schematach testowych. Podejście jest przyrostowe — im więcej schematów przetestujemy, tym kompletniejszy staje się słownik szumów i tym mniej ręcznych korekt potrzeba przy nowych rysunkach.

# Eval (textract_eval)

    [opis] Skrypt ewaluacyjny (`scripts/textract_eval.py`) uruchamiający pełny pipeline postprocessingu Textract na obrazach testowych i generujący overlay wizualny oraz plik JSON z wynikami. Pozwala szybko ocenić jakość rozpoznawania komponentów, wartości i etykiet sieciowych na schematach elektronicznych.

    [kategoria] Testy regresji / kontrola jakości OCR

    [zastosowanie] Uruchamiamy `textract_eval.py` na zbiorze obrazów z `textract_test/images/`. Skrypt generuje: (1) overlay PNG z kolorowymi ramkami i etykietami tokenów nałożonymi na oryginał, (2) plik `_post.json` z listą tokenów i par komponent–wartość. Flaga `--only <fragment>` pozwala ograniczyć ewaluację do wybranego schematu (dopasowanie podciągu w nazwie pliku). Służy do weryfikacji poprawek i wykrywania regresji — po każdej zmianie w postprocessingu uruchamiamy eval na wszystkich schematach testowych i porównujemy overlaye.
# Designator (oznaczenie referencyjne komponentu)

    [opis] Krótki alfanumeryczny identyfikator elementu elektronicznego na schemacie, składający się z litery kategorii i numeru porządkowego, np. R1 (rezystor nr 1), C3 (kondensator nr 3), D1 (dioda nr 1), Q2 (tranzystor nr 2), L1 (cewka nr 1), IC401 (układ scalony nr 401). Designator jednoznacznie wskazuje, który fizyczny komponent na płytce odpowiada symbolowi na rysunku.

    [kategoria] Elektronika / schematy / OCR

    [zastosowanie] W pipeline Textract designatory są kluczowym elementem — funkcja `_categorize()` rozpoznaje tokeny pasujące do wzorca `[RCDQLM]\d+` lub `IC\d+` i klasyfikuje je jako „component". Następnie `_pair_components_to_values()` paruje każdy designator z najbliższą wartością (np. R1 → 100kΩ). Brak designatorów w surowym wyjściu OCR (scenariusz A) oznacza, że żadna para nie powstanie, niezależnie od jakości pipeline'u. Gdy designatory są widoczne w OCR, ale pipeline je gubi (scenariusz B) — problem leży w regułach filtrowania lub kategoryzacji naszego kodu.

# Value (wartość komponentu)

    [opis] Parametr elektryczny przypisany do komponentu na schemacie — np. „100kΩ", „10nF", „2,2µF", „1N4148", „BC548". Wartość może być liczbą z jednostką (rezystancja, pojemność, indukcyjność) lub kodem/modelem elementu (np. oznaczenie diody lub tranzystora). Na overlayach postprocessingu rysowana jako **jasnoniebieski** box (RGB 0,128,255).

    [kategoria] Elektronika / schematy / OCR

    [zastosowanie] W pipeline Textract funkcja `_categorize()` klasyfikuje token jako „value", jeśli zawiera cyfry i pasuje do wzorców jednostek elektronicznych (K, M, Ω, F, V, µ itp.) lub ma separator (.,/). Wartości są parowane z najbliższym designatorem przez `_pair_components_to_values()`, tworząc pary typu R1→100kΩ. Na overlayach para jest połączona linią magenta.

# Net label (etykieta sieci / sygnału)

    [opis] Nazwa sygnału elektrycznego lub węzła na schemacie — np. „VCC", „GND", „+5V", „CLK", „We", „Do", „RC", „Q". Net labels identyfikują połączenia między komponentami: dwa punkty z tą samą etykietą są elektrycznie połączone, nawet jeśli nie rysuje się między nimi linii. Na overlayach postprocessingu rysowane jako **ciemnoniebieski** box (RGB 0,0,255).

    [kategoria] Elektronika / schematy / OCR

    [zastosowanie] W pipeline Textract `_categorize()` klasyfikuje token jako „net_label", gdy jest krótkim (≤6 znaków) alfanumerycznym tekstem bez cech wartości lub designatora. Obejmuje to: nazwy sygnałów (CLK, DATA), szyny zasilania (+5V, +12V, VCC), etykiety pinów (A, B, RC, Q). Net labels NIE są parowane z wartościami — służą do identyfikacji połączeń sieciowych, nie parametrów komponentów.

# Other (inne / niesklasyfikowane)

    [opis] Kategoria zbiorcza dla tokenów OCR, które nie pasują do żadnej z trzech głównych kategorii (component, value, net_label). Obejmuje: opisy tekstowe na schemacie (np. „Rys.", „cerami-czny", „Do drugiego kanału"), artefakty OCR, fragmenty symboli odczytane jako tekst, znaki interpunkcyjne. Na overlayach postprocessingu rysowane jako **zielony** box (RGB 0,200,0).

    [kategoria] OCR / postprocessing

    [zastosowanie] Tokeny „other" są ignorowane przy parowaniu — nie tworzą par komponent→wartość. Funkcja `_merge_horizontal_others()` scala sąsiadujące tokeny „other" w jedną etykietę (np. „cerami-" + „czny" → „cerami-czny"). Kategoria ta pełni rolę „kosza" na tekst, który jest widoczny na schemacie, ale nie ma znaczenia dla ekstrakcji listy elementów.
