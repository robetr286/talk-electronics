# Potwierdzenie: Start Opcji A — 7 grudnia 2025

Krótko: jutro zaczynamy od Opcji A — integrujemy `local_patch_repair` jako worker w pipeline i dodajemy testy oraz gating.

Co zrobimy jako pierwsze:
- Wyodrębnimy lokalną naprawę jako moduł (worker), dodamy parametryzację i proste unit tests.
- Ustawimy podstawowy gating/regresję, by chronić inne części pipeline przed pogorszeniem wyników.

Cel: bezpieczne, stopniowe wdrożenie lokalnej naprawy w pipeline i otrzymanie szybkich efektów poprawy topologii.
