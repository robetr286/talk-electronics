#!/usr/bin/env python3
"""
Generator syntetycznych schematów elektronicznych - Mock wersja z PIL.

Skrypt losowo rozmieszcza komponenty (rezystory, kondensatory, źródła)
i rysuje je używając PIL (bez KiCad).

Wymagania:
- Pillow (PIL)

Użycie:
    python generate_schematic.py --output output.png --seed 42 --components 20

✅ IMPLEMENTACJA:
- [x] Mock generator z PIL (bez KiCad)
- [x] Losowe rozmieszczanie komponentów
- [x] Rysowanie prostych symboli (rezystor, kondensator, GND)
- [x] Eksport do PNG z zapisaniem metadanych
- [x] Zapis współrzędnych do JSON dla anotacji
"""

import argparse
import json
import random
from pathlib import Path
from typing import Dict, List, Tuple

try:
    from PIL import Image, ImageDraw

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("⚠️  PIL (Pillow) nie zainstalowane. Zainstaluj: pip install Pillow")


class SchematicConfig:
    """Konfiguracja generatora schematów."""

    def __init__(
        self,
        seed: int = 42,
        num_components: int = 10,
        component_types: List[str] = None,
        canvas_size: Tuple[int, int] = (1000, 800),
    ):
        self.seed = seed
        self.num_components = num_components
        # Duplikaty w liście component_types pozwalają sterować proporcjami klas
        self.component_types = component_types or ["R", "C", "L", "D", "A"]
        self.canvas_size = canvas_size

        random.seed(seed)

    def to_dict(self) -> Dict:
        """Serializacja konfiguracji do słownika."""
        return {
            "seed": self.seed,
            "num_components": self.num_components,
            "component_types": self.component_types,
            "canvas_size": self.canvas_size,
        }


class SchematicGenerator:
    """Mock generator syntetycznych schematów przy użyciu PIL."""

    def __init__(self, config: SchematicConfig):
        self.config = config
        self.components = []
        self.connections = []
        self.image = None
        self.draw = None

        # Kolory
        self.bg_color = (255, 255, 255)  # Biały
        self.line_color = (0, 0, 0)  # Czarny
        self.text_color = (0, 0, 0)

    def generate(self) -> Dict:
        """
        Generuje syntetyczny schemat z losowymi komponentami.

        Returns:
            Słownik z metadanymi wygenerowanego schematu.
        """
        print(f"Generowanie schematu z {self.config.num_components} komponentami...")

        # Generuj komponenty z rozrzutem
        for i in range(self.config.num_components):
            component_type = random.choice(self.config.component_types)

            # Losowe pozycje z marginesem
            margin = 100
            x = random.randint(margin, self.config.canvas_size[0] - margin)
            y = random.randint(margin, self.config.canvas_size[1] - margin)

            # Wymiary bazowe
            if component_type in ["R", "L"]:  # Rezystor/Cewka
                width, height = 60, 20
            elif component_type == "C":  # Kondensator
                width, height = 20, 40
            elif component_type == "D":  # Dioda
                width, height = 40, 40
            elif component_type == "A":  # Wzmacniacz operacyjny
                width, height = 80, 60
            else:
                width, height = 50, 50

            rotation = random.choice([0, 90])  # Tylko 0° i 90° dla prostoty

            self.components.append(
                {
                    "id": f"{component_type}{i+1}",
                    "type": component_type,
                    "position": [x, y],
                    "width": width,
                    "height": height,
                    "rotation": rotation,
                }
            )

        return {
            "config": self.config.to_dict(),
            "components": self.components,
            "connections": self.connections,
        }

    def draw_resistor(self, x: int, y: int, width: int, height: int, rotation: int, label: str, variant: int = None):
        """Rysuje symbol rezystora (z wariantami)."""
        import random
        # 0=standard, 1=potencjometr, 2=termistor, 3=fotorezystor
        if variant is None:
            variant = random.choice([0, 1, 2, 3])
        
        # Prostokąt reprezentujący rezystor
        if rotation == 0:
            bbox = [x - width // 2, y - height // 2, x + width // 2, y + height // 2]
            self.draw.rectangle(bbox, outline=self.line_color, width=2)
            # Linie połączenia
            self.draw.line([x - width // 2 - 20, y, x - width // 2, y], fill=self.line_color, width=2)
            self.draw.line([x + width // 2, y, x + width // 2 + 20, y], fill=self.line_color, width=2)
            
            # Warianty dekoracyjne
            if variant == 1: # Potencjometr
                # Strzałka pod kątem (przez środek)
                self.draw.line([x - width // 3, y + height + 5, x + width // 3, y - height - 5], fill=self.line_color, width=2)
                # Grot
                self.draw.line([x + width // 3, y - height - 5, x + width // 3 - 8, y - height - 2], fill=self.line_color, width=2)
                self.draw.line([x + width // 3, y - height - 5, x + width // 3 - 2, y - height + 6], fill=self.line_color, width=2)
            elif variant == 2: # Termistor
                self.draw.line([x - width // 2 - 5, y + height // 2 + 5, x + width // 2 + 5, y - height // 2 - 5], fill=self.line_color, width=2)
                self.draw.line([x - width // 2 - 5, y + height // 2 + 5, x - width // 2 + 5, y + height // 2 + 5], fill=self.line_color, width=2)
            elif variant == 3: # Fotorezystor (dwie strzałeczki padające)
                for i in range(2):
                    arr_x = x - width // 4 + i * 15
                    arr_y = y - height - 15
                    self.draw.line([arr_x, arr_y, arr_x + 10, arr_y + 10], fill=self.line_color, width=2)
                    self.draw.line([arr_x + 10, arr_y + 10, arr_x + 3, arr_y + 10], fill=self.line_color, width=2)
                    self.draw.line([arr_x + 10, arr_y + 10, arr_x + 10, arr_y + 3], fill=self.line_color, width=2)

        else:  # 90° (width to DŁUGOŚĆ, height to SZEROKOŚĆ boczna)
            bbox = [x - height // 2, y - width // 2, x + height // 2, y + width // 2]
            self.draw.rectangle(bbox, outline=self.line_color, width=2)
            self.draw.line([x, y - width // 2 - 20, x, y - width // 2], fill=self.line_color, width=2)
            self.draw.line([x, y + width // 2, x, y + width // 2 + 20], fill=self.line_color, width=2)
            
            # Warianty dekoracyjne
            if variant == 1: # Potencjometr
                self.draw.line([x - height - 5, y - width // 3, x + height + 5, y + width // 3], fill=self.line_color, width=2)
                self.draw.line([x + height + 5, y + width // 3, x + height + 2, y + width // 3 - 8], fill=self.line_color, width=2)
                self.draw.line([x + height + 5, y + width // 3, x + height - 6, y + width // 3 - 2], fill=self.line_color, width=2)
            elif variant == 2: # Termistor
                self.draw.line([x + height // 2 + 5, y - width // 2 - 5, x - height // 2 - 5, y + width // 2 + 5], fill=self.line_color, width=2)
                self.draw.line([x + height // 2 + 5, y - width // 2 - 5, x + height // 2 + 5, y - width // 2 + 5], fill=self.line_color, width=2)
            elif variant == 3: # Fotorezystor
                for i in range(2):
                    arr_y = y - width // 4 + i * 15
                    arr_x = x - height - 15
                    self.draw.line([arr_x, arr_y, arr_x + 10, arr_y + 10], fill=self.line_color, width=2)
                    self.draw.line([arr_x + 10, arr_y + 10, arr_x + 3, arr_y + 10], fill=self.line_color, width=2)
                    self.draw.line([arr_x + 10, arr_y + 10, arr_x + 10, arr_y + 3], fill=self.line_color, width=2)

        # Label
        self.draw.text((x + 15, y - 20), label, fill=self.text_color)

    def draw_capacitor(self, x: int, y: int, width: int, height: int, rotation: int, label: str, variant: int = None):
        """Rysuje symbol kondensatora z wariantami (standard, polaryzowany)."""
        import random
        # 0=standard, 1=polaryzowany (+), 2=polaryzowany wygięty (+), 3=polaryzowany wygięty (bez +)
        if variant is None:
            variant = random.choice([0, 1, 2, 3])
        
        if rotation == 0:
            # Lewa elektroda + połączenie
            self.draw.line([x - 5, y - height // 2, x - 5, y + height // 2], fill=self.line_color, width=2)
            self.draw.line([x - 20, y, x - 5, y], fill=self.line_color, width=2)
            
            # Prawa elektroda + połączenie
            if variant >= 2:
                # Wygięta elektroda (np. elektrolityczny okładka ujemna)
                self.draw.arc([x, y - height // 2, x + 10, y + height // 2], start=270, end=90, fill=self.line_color, width=2)
                self.draw.line([x + 10, y, x + 20, y], fill=self.line_color, width=2)
            else:
                self.draw.line([x + 5, y - height // 2, x + 5, y + height // 2], fill=self.line_color, width=2)
                self.draw.line([x + 5, y, x + 20, y], fill=self.line_color, width=2)

            # Znak plusa (dodatni na lewej okładce, jeśli variant == 1 lub 2)
            if variant in [1, 2]:
                self.draw.line([x - 15, y - height // 2 + 2, x - 11, y - height // 2 + 2], fill=self.line_color, width=2)
                self.draw.line([x - 13, y - height // 2, x - 13, y - height // 2 + 4], fill=self.line_color, width=2)

        else:  # 90°
            # Górna elektroda + połączenie
            self.draw.line([x - height // 2, y - 5, x + height // 2, y - 5], fill=self.line_color, width=2)
            self.draw.line([x, y - 20, x, y - 5], fill=self.line_color, width=2)
            
            # Dolna elektroda + połączenie
            if variant >= 2:
                self.draw.arc([x - height // 2, y, x + height // 2, y + 10], start=180, end=360, fill=self.line_color, width=2)
                self.draw.line([x, y + 10, x, y + 20], fill=self.line_color, width=2)
            else:
                self.draw.line([x - height // 2, y + 5, x + height // 2, y + 5], fill=self.line_color, width=2)
                self.draw.line([x, y + 5, x, y + 20], fill=self.line_color, width=2)
            
            # Znak plusa
            if variant in [1, 2]:
                self.draw.line([x + height // 2 - 2, y - 15, x + height // 2 - 2, y - 11], fill=self.line_color, width=2)
                self.draw.line([x + height // 2 - 4, y - 13, x + height // 2, y - 13], fill=self.line_color, width=2)

        self.draw.text((x + 15, y - 20), label, fill=self.text_color)

    def draw_inductor(self, x: int, y: int, width: int, height: int, rotation: int, label: str, variant: int = None):
        """Rysuje symbol cewki rozbudowany o nowe warianty rdzenia (powietrze/brak, żelazo, ferryt)."""
        import math
        # 0=standard, 1=iron_core (dwie ciągłe linie), 2=ferrite_core (dwie przerywane linie)
        if variant is None:
            core_variant = random.choice([0, 1, 2])
        else:
            core_variant = variant
        num_bumps = random.choice([3, 4])
        
        if rotation == 0:
            bump_w = width / num_bumps
            start_x = x - width // 2
            # Linie połączenia
            self.draw.line([x - width // 2 - 20, y, x - width // 2, y], fill=self.line_color, width=2)
            self.draw.line([x + width // 2, y, x + width // 2 + 20, y], fill=self.line_color, width=2)
            # Łuki (półkola)
            for i in range(num_bumps):
                bx = start_x + i * bump_w
                arc_bbox = [bx, y - height // 2, bx + bump_w, y + height // 2]
                self.draw.arc(arc_bbox, start=180, end=0, fill=self.line_color, width=2)
            
            # Rysowanie rdzenia nad cewką
            if core_variant > 0:
                core_y1 = y - height // 2 - 5
                core_y2 = y - height // 2 - 12
                if core_variant == 1:  # Iron core (ciągłe)
                    self.draw.line([start_x, core_y1, start_x + width, core_y1], fill=self.line_color, width=2)
                    self.draw.line([start_x, core_y2, start_x + width, core_y2], fill=self.line_color, width=2)
                elif core_variant == 2:  # Ferrite core (przerywane)
                    dash_len = 6
                    gap = 4
                    cx = start_x
                    while cx < start_x + width:
                        ex = min(cx + dash_len, start_x + width)
                        self.draw.line([cx, core_y1, ex, core_y1], fill=self.line_color, width=2)
                        self.draw.line([cx, core_y2, ex, core_y2], fill=self.line_color, width=2)
                        cx += dash_len + gap

        else:  # 90°
            bump_h = width / num_bumps
            start_y = y - width // 2
            self.draw.line([x, y - width // 2 - 20, x, y - width // 2], fill=self.line_color, width=2)
            self.draw.line([x, y + width // 2, x, y + width // 2 + 20], fill=self.line_color, width=2)
            for i in range(num_bumps):
                by = start_y + i * bump_h
                arc_bbox = [x - height // 2, by, x + height // 2, by + bump_h]
                self.draw.arc(arc_bbox, start=270, end=90, fill=self.line_color, width=2)
            
            if core_variant > 0:
                core_x1 = x + height // 2 + 5
                core_x2 = x + height // 2 + 12
                if core_variant == 1:
                    self.draw.line([core_x1, start_y, core_x1, start_y + width], fill=self.line_color, width=2)
                    self.draw.line([core_x2, start_y, core_x2, start_y + width], fill=self.line_color, width=2)
                elif core_variant == 2:
                    dash_len = 6
                    gap = 4
                    cy = start_y
                    while cy < start_y + width:
                        ey = min(cy + dash_len, start_y + width)
                        self.draw.line([core_x1, cy, core_x1, ey], fill=self.line_color, width=2)
                        self.draw.line([core_x2, cy, core_x2, ey], fill=self.line_color, width=2)
                        cy += dash_len + gap

        self.draw.text((x + 15, y - 20), label, fill=self.text_color)

    def draw_diode(self, x: int, y: int, width: int, height: int, rotation: int, label: str, variant: int = None):
        """Rysuje symbol diody — losowy wariant (standard/zener/LED/fotodioda/schottky/varicap)."""
        import random
        # Wariant losowany 0=standard, 1=zener, 2=LED, 3=fotodioda, 4=schottky, 5=varicap
        if variant is None:
            variant = random.choice([0, 1, 2, 3, 4, 5])
        self._draw_diode_variant(x, y, width, height, rotation, label, variant)

    def _draw_diode_variant(self, x, y, width, height, rotation, label, variant):
        """Rysuje wariant diody: 0=standard, 1=zener, 2=LED, 3=fotodioda, 4=schottky, 5=varicap."""
        lc = self.line_color
        tc = self.text_color
        if rotation == 0:
            # Trójkąt wypełniony (anoda→katoda w prawo)
            tri = [(x - width // 4, y - height // 2),
                   (x - width // 4, y + height // 2),
                   (x + width // 4, y)]
            self.draw.polygon(tri, fill=lc, outline=lc, width=2)
            # Kreska katodowa
            kx = x + width // 4
            ky_top, ky_bot = y - height // 2, y + height // 2
            if variant == 1:  # Zener
                bend = height // 6
                self.draw.line([kx, ky_top, kx - bend, ky_top - bend], fill=lc, width=2)
                self.draw.line([kx, ky_top, kx, ky_bot], fill=lc, width=2)
                self.draw.line([kx, ky_bot, kx + bend, ky_bot + bend], fill=lc, width=2)
            elif variant == 4:  # Schottky
                bend = height // 6
                self.draw.line([kx, ky_top, kx, ky_bot], fill=lc, width=2)
                self.draw.line([kx, ky_top, kx + bend, ky_top], fill=lc, width=2)
                self.draw.line([kx + bend, ky_top, kx + bend, ky_top + bend], fill=lc, width=2)
                self.draw.line([kx, ky_bot, kx - bend, ky_bot], fill=lc, width=2)
                self.draw.line([kx - bend, ky_bot, kx - bend, ky_bot - bend], fill=lc, width=2)
            elif variant == 5:  # Varicap
                self.draw.line([kx, ky_top, kx, ky_bot], fill=lc, width=2)
                self.draw.line([kx + 4, ky_top, kx + 4, ky_bot], fill=lc, width=2)
            else:
                self.draw.line([kx, ky_top, kx, ky_bot], fill=lc, width=2)
                
            # Połączenia (przewody)
            self.draw.line([x - width // 2, y, x - width // 4, y], fill=lc, width=2)
            cx = x + width // 4 + 4 if variant == 5 else x + width // 4
            self.draw.line([cx, y, x + width // 2, y], fill=lc, width=2)
            
            # LED i Fotodioda strzałki
            if variant == 2 or variant == 3:
                for i in range(2):
                    t = 0.3 + i * 0.35
                    sx = int((x - width / 4) + t * (width / 2)) + 2
                    sy = int((y - height / 2) + t * (height / 2)) - 2
                    ex, ey = sx + 12, sy - 5
                    if variant == 2: # LED
                        self.draw.line([sx, sy, ex, ey], fill=lc, width=2)
                        self.draw.line([ex, ey, ex - 5, ey + 1], fill=lc, width=2)
                        self.draw.line([ex, ey, ex - 3, ey + 4], fill=lc, width=2)
                    elif variant == 3: # Fotodioda
                        self.draw.line([sx, sy, ex, ey], fill=lc, width=2)
                        self.draw.line([sx, sy, sx + 5, sy - 1], fill=lc, width=2)
                        self.draw.line([sx, sy, sx + 3, sy - 4], fill=lc, width=2)
        else:  # 90°
            tri = [(x - height // 2, y - width // 4),
                   (x + height // 2, y - width // 4),
                   (x, y + width // 4)]
            self.draw.polygon(tri, fill=lc, outline=lc, width=2)
            ky = y + width // 4
            kx_left, kx_right = x - height // 2, x + height // 2
            if variant == 1:  # Zener
                bend = height // 6
                self.draw.line([kx_left, ky, kx_left - bend, ky - bend], fill=lc, width=2)
                self.draw.line([kx_left, ky, kx_right, ky], fill=lc, width=2)
                self.draw.line([kx_right, ky, kx_right + bend, ky + bend], fill=lc, width=2)
            elif variant == 4:  # Schottky
                bend = height // 6
                self.draw.line([kx_left, ky, kx_right, ky], fill=lc, width=2)
                self.draw.line([kx_left, ky, kx_left, ky + bend], fill=lc, width=2)
                self.draw.line([kx_left, ky + bend, kx_left - bend, ky + bend], fill=lc, width=2)
                self.draw.line([kx_right, ky, kx_right, ky - bend], fill=lc, width=2)
                self.draw.line([kx_right, ky - bend, kx_right + bend, ky - bend], fill=lc, width=2)
            elif variant == 5:  # Varicap
                self.draw.line([kx_left, ky, kx_right, ky], fill=lc, width=2)
                self.draw.line([kx_left, ky + 4, kx_right, ky + 4], fill=lc, width=2)
            else:
                self.draw.line([kx_left, ky, kx_right, ky], fill=lc, width=2)
                
            self.draw.line([x, y - width // 2, x, y - width // 4], fill=lc, width=2)
            cy = y + width // 4 + 4 if variant == 5 else y + width // 4
            self.draw.line([x, cy, x, y + width // 2], fill=lc, width=2)
            
            if variant == 2 or variant == 3:
                for i in range(2):
                    t = 0.3 + i * 0.35
                    sx = int((x + height / 2) + t * (-height / 2)) + 2
                    sy = int((y - width / 4) + t * (width / 2)) + 2
                    ex, ey = sx + 5, sy + 12
                    if variant == 2: # LED
                        self.draw.line([sx, sy, ex, ey], fill=lc, width=2)
                        self.draw.line([ex, ey, ex - 1, ey - 5], fill=lc, width=2)
                        self.draw.line([ex, ey, ex - 4, ey - 3], fill=lc, width=2)
                    elif variant == 3: # Fotodioda
                        self.draw.line([sx, sy, ex, ey], fill=lc, width=2)
                        self.draw.line([sx, sy, sx - 1, sy + 5], fill=lc, width=2)
                        self.draw.line([sx, sy, sx - 4, sy + 3], fill=lc, width=2)

        self.draw.text((x + 15, y - 20), label, fill=tc)

    def draw_op_amp(self, x: int, y: int, width: int, height: int, rotation: int, label: str):
        """Rysuje symbol wzmacniacza operacyjnego (trójkąt z wejściami i wyjściem)."""
        # Opcjonalne piny zasilania (4. i 5. noga) - losowo generowane
        num_pins = random.choice([3, 4, 5])
        has_vcc = num_pins >= 4
        has_vee = num_pins == 5
        # Urozmaicenie dla 4 pinów - zasilanie może być tylko u góry albo tylko u dołu
        if num_pins == 4 and random.random() > 0.5:
            has_vcc, has_vee = False, True

        if rotation in {0, 180}:
            triangle = [(x - width // 2, y - height // 2), (x - width // 2, y + height // 2), (x + width // 2, y)]
            self.draw.polygon(triangle, outline=self.line_color, width=2)

            # Wejścia +/- po lewej stronie
            in_y_offset = height // 4
            self.draw.line(
                [(x - width // 2 - 25, y - in_y_offset), (x - width // 2, y - in_y_offset)],
                fill=self.line_color,
                width=2,
            )
            self.draw.line(
                [(x - width // 2 - 25, y + in_y_offset), (x - width // 2, y + in_y_offset)],
                fill=self.line_color,
                width=2,
            )
            self.draw.text((x - width // 2 - 35, y - in_y_offset - 8), "+", fill=self.text_color)
            self.draw.text((x - width // 2 - 35, y + in_y_offset - 8), "-", fill=self.text_color)

            # Wyjście po prawej
            self.draw.line([(x + width // 2, y), (x + width // 2 + 30, y)], fill=self.line_color, width=2)

            # Opcjonalne zasilanie (góra/dół) dla rotacji 0/180
            if has_vcc:
                self.draw.line([(x, y - height // 4), (x, y - height // 4 - 25)], fill=self.line_color, width=2)
            if has_vee:
                self.draw.line([(x, y + height // 4), (x, y + height // 4 + 25)], fill=self.line_color, width=2)

        else:  # 90/270 - obrót prosty bez zmiany geometrii trójkąta
            triangle = [(x - height // 2, y + width // 2), (x + height // 2, y + width // 2), (x, y - width // 2)]
            self.draw.polygon(triangle, outline=self.line_color, width=2)

            # Wejścia +/- u dołu trójkąta (po lewej/prawej po obrocie)
            in_x_offset = height // 4
            self.draw.line(
                [(x - in_x_offset, y + width // 2 + 25), (x - in_x_offset, y + width // 2)],
                fill=self.line_color,
                width=2,
            )
            self.draw.line(
                [(x + in_x_offset, y + width // 2 + 25), (x + in_x_offset, y + width // 2)],
                fill=self.line_color,
                width=2,
            )
            self.draw.text((x - in_x_offset - 8, y + width // 2 + 28), "+", fill=self.text_color)
            self.draw.text((x + in_x_offset - 8, y + width // 2 + 28), "-", fill=self.text_color)

            # Wyjście na wierzchołku
            self.draw.line([(x, y - width // 2), (x, y - width // 2 - 30)], fill=self.line_color, width=2)

            # Opcjonalne zasilanie (lewo/prawo) dla rotacji 90/270
            if has_vcc:
                self.draw.line([(x - height // 4, y), (x - height // 4 - 25, y)], fill=self.line_color, width=2)
            if has_vee:
                self.draw.line([(x + height // 4, y), (x + height // 4 + 25, y)], fill=self.line_color, width=2)

        self.draw.text((x + 15, y - 20), label, fill=self.text_color)

    def export_to_png(self, output_path: Path) -> None:
        """
        Rysuje i eksportuje schemat do PNG.

        Args:
            output_path: Ścieżka wyjściowa dla pliku PNG.
        """
        if not PIL_AVAILABLE:
            raise ImportError("PIL (Pillow) jest wymagane. Zainstaluj: pip install Pillow")

        # Utwórz obraz
        self.image = Image.new("RGB", self.config.canvas_size, self.bg_color)
        self.draw = ImageDraw.Draw(self.image)

        # Rysuj każdy komponent
        for comp in self.components:
            x, y = comp["position"]
            w, h = comp["width"], comp["height"]
            rot = comp["rotation"]
            label = comp["id"]
            comp_type = comp["type"]

            if comp_type == "R":
                self.draw_resistor(x, y, w, h, rot, label)
            elif comp_type == "C":
                self.draw_capacitor(x, y, w, h, rot, label)
            elif comp_type == "L":
                self.draw_inductor(x, y, w, h, rot, label)
            elif comp_type == "D":
                self.draw_diode(x, y, w, h, rot, label)
            elif comp_type == "A":
                self.draw_op_amp(x, y, w, h, rot, label)

        # Zapisz
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.image.save(str(output_path), "PNG")
        print(f"[OK] Zapisano schemat: {output_path}")

    def save_metadata(self, output_path: Path) -> None:
        """
        Zapisuje metadane generowania do JSON.

        Args:
            output_path: Ścieżka wyjściowa dla metadanych.
        """
        metadata = {
            "config": self.config.to_dict(),
            "components": self.components,
            "connections": self.connections,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        print(f"Zapisano metadane: {output_path}")


def main():
    """Główna funkcja skryptu."""
    parser = argparse.ArgumentParser(description="Mock generator syntetycznych schematów (PIL-based, bez KiCad)")
    parser.add_argument("--output", type=Path, required=True, help="Ścieżka wyjściowa dla pliku schematu (PNG)")
    parser.add_argument("--metadata", type=Path, help="Ścieżka wyjściowa dla metadanych (JSON)")
    parser.add_argument("--seed", type=int, default=42, help="Seed dla generatora losowego")
    parser.add_argument("--components", type=int, default=10, help="Liczba komponentów do wygenerowania")
    parser.add_argument("--width", type=int, default=1000, help="Szerokość płótna w pikselach")
    parser.add_argument("--height", type=int, default=800, help="Wysokość płótna w pikselach")

    args = parser.parse_args()

    # Konfiguracja generatora
    config = SchematicConfig(seed=args.seed, num_components=args.components, canvas_size=(args.width, args.height))

    # Generowanie schematu
    generator = SchematicGenerator(config)
    metadata = generator.generate()

    # Eksport do PNG
    generator.export_to_png(args.output)

    # Zapisz metadane
    metadata_path = args.metadata or args.output.with_suffix(".json")
    generator.save_metadata(metadata_path)

    print(f"[OK] Wygenerowano schemat: {len(metadata['components'])} komponentów")
    print(f"  - Obraz: {args.output}")
    print(f"  - Metadane: {metadata_path}")


if __name__ == "__main__":
    main()
