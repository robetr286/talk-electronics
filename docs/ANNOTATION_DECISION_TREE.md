# Szybkie Drzewo Decyzyjne: Prostokąt vs Poligon

## 🔍 START: Spójrz na symbol

### ✅ Użyj OBRÓCONEGO PROSTOKĄTA (80-90% przypadków)

**Kiedy:**
- Symbol jest prostokątny/podobny do pudełka
- Możesz obrócić aby uniknąć tekstu/sąsiednich elementów
- Ciasne dopasowanie jest możliwe z <10% pustej przestrzeni

**Jak:**
1. Narysuj prostokąt wokół symbolu
2. Obróć aby dopasować do orientacji symbolu
3. Dostosuj rozmiar (ciasno, ale nie za ciasno)
4. Sprawdź: Czy nachodzi na tekst/inne symbole? NIE → Gotowe! ✅

**Skróty klawiszowe:**
- `1-0, q, w` = Wybór klasy
- Przeciągnij rogi = Zmiana rozmiaru
- Okrągły uchwyt = Rotacja
- `Backspace` = Usuń

---

### 🔺 Użyj POLIGONU (10-20% przypadków)

**Kiedy:**
✓ Obrócony prostokąt NIE MOŻE uniknąć nachodzenia:
  - Etykieta tekstowa na symbolu (nieuniknione)
  - Gęsty schemat (symbole bardzo blisko)
  - Nieregularny kształt (ręcznie rysowany, uszkodzony skan)
  - Częściowy widok (symbol przy krawędzi obrazu)

**Jak:**
1. Naciśnij `Shift + [1-0, q, w]` (aktywuje tryb Poligon)
2. Kliknij 4-8 punktów wokół konturu symbolu
3. Podwójne kliknięcie lub Enter aby zamknąć
4. Dostosuj punkty jeśli potrzeba

**Zachowaj prostotę:**
- Użyj 4 punktów dla symboli podobnych do pudełka (jak prostokąt)
- Użyj 5-8 punktów tylko gdy konieczne
- Podążaj za krawędziami symbolu, nie za tekstem/przewodami

---

## 🎯 Schemat Decyzyjny

```
┌─────────────────────────────────┐
│ Czy możesz narysować CIASNY     │
│ prostokąt? (po obróceniu)       │
└─────┬──────────────┬────────────┘
      │ TAK          │ NIE
      │              │
      ▼              ▼
┌───────────┐  ┌─────────────┐
│ Prostokąt │  │ Czy symbol  │
│  + Rotacja│  │ ma prosty   │
│           │  │ kształt?    │
└───────────┘  └──────┬──────┘
                      │
              ┌───────┴────────┐
              │ TAK      NIE   │
              ▼               ▼
        ┌───────────┐   ┌──────────┐
        │ Poligon   │   │ Poligon  │
        │ (4 pkt)   │   │ (5-8 pkt)│
        └───────────┘   └──────────┘
```

---

## 📊 Przykłady

### ✅ Przypadki Prostokąta

| Symbol | Rotacja | Dlaczego prostokąt? |
|--------|---------|---------------------|
| Rezystor (poziomy) | 0° | Standardowa orientacja |
| Rezystor (pionowy) | 90° | Prosta rotacja |
| Rezystor (skośny) | 45° | Obrócony aby ominąć tekst |
| Kondensator + etykieta "C1" | Obróć aby ominąć tekst | Tekst jest z boku |
| Wzmacniacz operacyjny | 0° lub 180° | Standardowy kształt IC |

### 🔺 Przypadki Poligonu

| Symbol | Dlaczego poligon? | Punkty |
|--------|-------------------|--------|
| Rezystor z "R1" na górze | Tekst nieuniknienie nachodzi | 4-6 pkt wokół korpusu |
| IC przy krawędzi (50% widoczne) | Częściowy widok | 4-5 pkt na widocznej części |
| Symbol ręcznie rysowany | Nieregularny kształt | 6-8 pkt podążając za konturem |
| Gęsty klaster (3 symbole ciasno) | Nie można rozdzielić | 8 pkt wokół grupy |

---

## ⚡ Wskazówki Przyspieszające

### Dla Prostokątów:
1. Narysuj zgrubny prostokąt → Obróć → Dostosuj rozmiar
2. Użyj siatki/zoomu dla precyzji
3. Cel: 10-15 sekund na anotację

### Dla Poligonów:
1. Zacznij od 4 rogów (jak prostokąt)
2. Dodaj dodatkowe punkty tylko gdzie potrzeba
3. Podwójne kliknięcie aby zakończyć (nie klikaj punktu startowego)
4. Cel: 30-40 sekund na anotację

### Przetwarzanie Wsadowe:
- Najpierw zrób wszystkie prostokąty (tryb szybki)
- Potem wróć do poligonów (tryb precyzyjny)
- Lub: prostokąt dopóki nie napotkasz problemu → poligon → kontynuuj

---

## 🚫 Częste Błędy

| ❌ NIE RÓB TEGO | ✅ RÓB TO |
|-----------------|-----------|
| Używaj poligonu bo "jest dokładniejszy" | Używaj prostokąta gdy pasuje (szybciej!) |
| Rysuj ogromny prostokąt z dużo pustej przestrzeni | Obróć aby był ciasny |
| Używaj 15-punktowego poligonu dla prostych kształtów | Użyj maksymalnie 4-8 punktów |
| Włączaj etykiety tekstowe do anotacji | Anotuj tylko korpus symbolu |
| Włączaj połączenia przewodów | Anotuj tylko korpus komponentu |
| Nachodzenie na sąsiednie symbole | Każdy symbol = osobna anotacja |

---

## 🏁 Lista Kontrolna Jakości

Przed wysłaniem każdej anotacji:
- [ ] Czy jest CIASNA? (minimalna pusta przestrzeń)
- [ ] Czy jest CZYSTA? (bez tekstu/przewodów)
- [ ] Czy jest KOMPLETNA? (wszystkie widoczne części symbolu)
- [ ] Właściwe narzędzie? (prostokąt jeśli możliwe, poligon jeśli potrzeba)
- [ ] Właściwa klasa? (rezystor, kondensator, etc.)
- [ ] Dodana flaga jakości jeśli niepewne/zaszumione?

---

## 🆘 W Razie Wątpliwości

**Domyślnie: Prostokąt + Flaga Jakości:**
```
Jeśli nie jesteś pewien czy poligon jest potrzebny:
  → Użyj obróconego prostokąta
  → Zaznacz jakość = "noisy" (zaszumione)
  → Dodaj notatkę wyjaśniającą problem
```

To pozwala osobom sprawdzającym:
- Zobaczyć Twoje rozumowanie
- Zdecydować czy przekonwertować na poligon
- Śledzić trudne przypadki dla usprawnienia modelu

---

## 📈 Docelowe Statystyki

**Po 100 anotacjach powinieneś zobaczyć:**
- ~80-90% Prostokątów
- ~10-20% Poligonów
- Średni czas: 15s/anotacja
- Jakość: >80% "clean" (czystych)

**Jeśli masz:**
- <70% prostokątów → Nadużywasz poligonów (wolno!)
- >95% prostokątów → Możesz pomijać trudne przypadki
- <50% "clean" → Schematy mogą być zbyt niskiej jakości

---

## 🎓 Ćwiczenie Treningowe

**Poćwicz na tych 5 przypadkach:**

1. **Poziomy rezystor, etykieta "R1" po prawej**
   → Odpowiedź: Prostokąt pod 0°

2. **Pionowy kondensator, etykieta "C1" na górze niego**
   → Odpowiedź: Poligon (4-6 punktów wokół korpusu)

3. **Skośny tranzystor, etykieta "Q1" w pobliżu ale się nie dotyka**
   → Odpowiedź: Prostokąt pod ~45° (obrócony aby ominąć etykietę)

4. **Chip IC przy dolnej krawędzi obrazu (80% widoczny)**
   → Odpowiedź: Poligon (4-5 punktów na widocznej części)

5. **Rezystor w gęstym obszarze, 3 przewody przecinają go**
   → Odpowiedź: Prostokąt + quality="noisy" (lub poligon jeśli przewody uniemożliwiają)

---

**Pamiętaj: Prostokąt to Twój przyjaciel! 🎯**
- Szybszy w rysowaniu
- Łatwiejszy w dostosowywaniu
- Idealny dla 80-90% przypadków
- Używaj poligonu tylko gdy naprawdę musisz

**Kiedy przełączyć się na poligon:**
"Próbowałem obrócić, a nadal nie mogę uzyskać czystego prostokąta" → Czas na poligon! 🔺
