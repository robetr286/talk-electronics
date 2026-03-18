# Test: Edge connectors → użycie ROI w Segmentacji

Cel
- Potwierdzić, że wykryte konektory z zakładki "Łączenie schematów" mogą zostać powiązane z modułem Segmentacji i że pole `Użyj ramki schematu (ROI)` aktywuje się po powiązaniu konektorów.

Pre‑warunki
- Dev server uruchomiony (Flask) i dostępny pod http://127.0.0.1:5000
- Testowy fixture obrazu dostępny: `/static/fixtures/line-segmentation/cross_gray.png` lub możliwość wczytania obrazu z dysku
- Konto/testowy workspace istnieje i jest w trybie testowym

Kroki testowe (dokładne)
1. Przejdź do zakładki `Segmentacja`.
   - Oczekiwana asercja: element `#lineSegSourceImage` widoczny; element `#lineSegUseConnectorRoi` **nieaktywny** (disabled lub unchecked).
2. Wybierz `Załaduj z dysku` (jeśli nie ma fixture) i upewnij się że obraz załadował się poprawnie.
3. Przejdź do zakładki `Łączenie schematów`.
   - Kliknij `Załaduj wykryte z backendu`.
   - Oczekiwana asercja: lista/popup z wykrytymi elementami jest widoczna.
4. W ramce "Dodaj lub edytuj konektor" uzupełnij pola i zapisz:
   - Edge ID: `a01`
   - Page: `1`
   - Label: `test`
   - (Notatka: pole `history id` powinno być wypełnione automatycznie — zapisz tę wartość do porównania.)
   - Kliknij `Zapisz konektor`.
   - Oczekiwana asercja: pojawia się komunikat (w ciągu 10s) `Załadowano 64 konektorów` (albo inny potwierdzający zapis). Zapisz `historyId` z odpowiedzi.
5. Wróć do zakładki `Segmentacja`.
   - Asercja: pole `#lineSegUseConnectorRoi` wciąż nieaktywne (jeśli dalej nie ma powiązania).
6. Przejdź do ramki/sekcji `Konektory krawędzi` i kliknij `Odśwież`.
   - Asercja: pod polem pojawia się wpis `Powiązano 1 konektorów` i w tabeli zobaczysz wiersz z `edgeId=a01` i `label=test`. (Opcjonalnie porównaj `historyId` w wierszu z zapisaną wartością).
7. Po pojawieniu się powiązania pole `#lineSegUseConnectorRoi` powinno stać się aktywne → zaznacz je.
8. Kliknij `Wykryj linie` (`#lineSegRunBtn`).
   - Oczekiwana asercja: w ciągu 30s pojawia się komunikat `Segmentacja zakończona`. Sprawdź, że odpowiedź serwera dla `/api/segment/lines` zawiera `result.metadata.roi` z oczekiwanym obiektem { x, y, width, height }.
9. Zakończ test: zapisz screenshoty, request/response bodies oraz log serwera w przypadku niepowodzenia.

Dodatkowe uwagi i odporność na flaki
- Zawsze czekaj na selektory i komunikaty z timeoutem (10s–30s) zamiast tylko używać `waitForTimeout` statycznego.
- Jeśli backend zwraca 0 wykrytych konektorów, test powinien zakończyć się błędem z jasnym komunikatem: `no connectors returned by /api/edge-connectors`.
- Loguj `historyId` z odpowiedzi i porównaj go z UI, aby potwierdzić, że to ten sam wpis.

Asercje do automatyzacji (Playwright)
- `expect(page.locator('#lineSegUseConnectorRoi')).toBeDisabled()`
- `expect(notification).toContainText(/Załadowano \d+ konektor/);`
- `expect(tableRow).toContainText('a01');`
- `expect(await resp.json()).toHaveProperty('result.metadata.roi');`

---

Krótka checklist (do szybkiego sprawdzenia)
- [ ] Pre‑warunki: server, fixture
- [ ] Załaduj i zapisz konektor (edgeId=a01)
- [ ] Odśwież konektory i potwierdź powiązanie
- [ ] Aktywuj ROI i uruchom segmentację
- [ ] Odbierz `Segmentacja zakończona` i zweryfikuj `metadata.roi`
