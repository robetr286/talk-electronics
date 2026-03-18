# Eksport do SPICE (.cir)

Jak wygenerować plik SPICE z aplikacji Talk_electronic.

## Minimalny flow (API / backend)
1. Przygotuj netlistę logiczną (nodes/edges + `metadata.net_labels`).
2. Zbuduj listę komponentów (`kind`, `nodes`, opcjonalnie `value`, `reference`, `parameters`).
3. Wywołaj endpoint `POST /api/segment/netlist/spice` z payloadem:
   ```json
   {
     "netlist": { ... },
     "components": [
       {"kind": "resistor", "nodes": ["NET001", "NET002"], "value": "1k"},
       {"kind": "capacitor", "nodes": ["NET002", "0"], "value": "10u"}
     ],
     "title": "Demo RC",
     "groundAlias": "0",
     "storeHistory": true
   }
   ```
4. Odpowiedź zawiera klucz `spice` (tekst `.cir`) oraz `metadata` (liczba komponentów, tytuł, ostrzeżenia). Jeśli `storeHistory=true`, plik `.cir` trafia do `uploads/`.

## Mapowanie symbol → SPICE
- Domyślne prefiksy: R (rezystor), C (kondensator), L (cewka), D (dioda), Q (tranzystor), X (opamp/IC/connector/misc), V (power_rail), G (ground).
- Wartości są normalizowane, gdy to możliwe (np. `1k`, `10u`), ale można podać surowe napisy.
- Węzły `0/gnd/ground` mapują się na `groundAlias` (domyślnie `0`).

## Walidacja
- Brak węzłów w netliście → błąd `NETLIST_EMPTY` (400).
- Nieznane węzły w komponentach → `SPICE_COMPONENT_ERRORS` (400) z opisem węzła.
- Przy braku komponentów eksport zwróci deck z komentarzem i ostrzeżeniem.

## Przykładowy deck RC (sprawdzony w ngspice)
Plik `demo_rc.cir` zaakceptowany przez ngspice (brak błędów parsera):

```
* RC low-pass step response
V1 NET_IN 0 PULSE(0 5 0 1n 1n 1ms 2ms)
R1 NET_IN NET_OUT 1k
C1 NET_OUT 0 10u
.tran 0.1ms 10ms
.end
```

Uruchom: `ngspice demo_rc.cir` – symulacja powinna zakończyć się bez błędów (komenda `tran`).

## Skrót dla UI
- W zakładce **Segmentacja linii → Netlista** kliknij **Eksportuj do SPICE** po wygenerowaniu netlisty.
- Podgląd `.cir` i link pobrania pojawiają się w panelu. Zaznacz `Zapisz w historii`, aby plik trafił do `processed/spice/`.

## Testy i metryka sukcesu
- Test `tests/test_netlist_to_spice.py` sprawdza generację RC oraz endpoint API.
- Metryka: przykładowy RC eksportuje do `.cir` i przechodzi symulację w ngspice/LTspice (brak błędów parsera).

## Dla nietechnicznego
- Cel: klik w UI → gotowy plik SPICE. Jeśli czegoś brakuje (np. wartość elementu lub nazwa węzła), API zwróci czytelną informację, co uzupełnić.
