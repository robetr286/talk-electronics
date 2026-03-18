import json
import os
import shutil
from pathlib import Path
from PIL import Image

# Mapowanie klas wg dataset_yolo
CLASS_MAP = {
    "resistor": 0,
    "capacitor": 1,
    "inductor": 2,
    "coil": 2,  # Alias w Label Studio
    "diode": 3,
    "op_amp": 4
}

def setup_yolo_dir(base_dir):
    """Tworzy strukturę katalogów YOLO."""
    img_dir = Path(base_dir) / "images"
    lbl_dir = Path(base_dir) / "labels"
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)
    return img_dir, lbl_dir

def convert_to_yolo_format(json_path, png_path, output_lbl_dir, output_img_dir):
    """Konwertuje plik z Label Studio do formatu YOLO txt."""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    if not isinstance(data, list):
        data = [data]
        
    img_name = Path(png_path).name
    
    # Znajdź właściwy task
    target_task = None
    for task in data:
        file_upload = task.get("file_upload", "")
        image_url = task.get("data", {}).get("image", "")
        if img_name in file_upload or img_name in image_url:
            target_task = task
            break
            
    if not target_task:
        print(f"  ❌ Nie znaleziono DOKŁADNIE zadania dla {img_name}")
        return False
        
    annotations = target_task.get("annotations", [])
    if not annotations:
        print(f"  ❌ Brak adnotacji dla {img_name}")
        return False
        
    result = annotations[0].get("result", [])
    if not result:
        print(f"  ❌ Brak bboxów dla {img_name}")
        return False
        
    # Kopiujemy obrazek do docelowego folderu
    dest_png = output_img_dir / img_name
    if Path(png_path) != dest_png:
        shutil.copy2(png_path, dest_png)
    
    dest_txt = output_lbl_dir / f"{Path(png_path).stem}.txt"
    yolo_lines = []
    
    for item in result:
        if item.get("type") != "rectanglelabels": continue
        
        val = item["value"]
        x_pct, y_pct = val["x"], val["y"]
        w_pct, h_pct = val["width"], val["height"]
        
        labels = val.get("rectanglelabels", [])
        if not labels: continue
        label = labels[0].lower()
        
        class_id = CLASS_MAP.get(label)
        if class_id is None:
            print(f"    ⚠️ Nieznana klasa '{label}' pomijana.")
            continue
            
        # YOLO oczekuje: class_id center_x center_y width height (znormalizowane 0-1)
        # LabelStudio zwraca x,y lewego górnego rogu w %, w,h w %
        x_center = (x_pct + w_pct / 2) / 100.0
        y_center = (y_pct + h_pct / 2) / 100.0
        w_norm = w_pct / 100.0
        h_norm = h_pct / 100.0
        
        # Zabezpieczenie przed wartościami > 1 lub < 0
        x_center = max(0.0001, min(0.9999, x_center))
        y_center = max(0.0001, min(0.9999, y_center))
        w_norm = max(0.0001, min(1.0, w_norm))
        h_norm = max(0.0001, min(1.0, h_norm))
        
        yolo_lines.append(f"{class_id} {x_center:.6f} {y_center:.6f} {w_norm:.6f} {h_norm:.6f}")
        
    if yolo_lines:
        with open(dest_txt, "w") as f:
            f.write("\n".join(yolo_lines))
        print(f"  ✅ Skonwertowano {img_name} ({len(yolo_lines)} obiekty)")
        return True
    
    return False

if __name__ == "__main__":
    SOURCE_DIR = Path("data/real/cewki")
    DEST_DIR_VAL = Path("data/yolo_dataset/merged_opamp_14_01_2026/test")
    # Zmieniamy powoli nazwę z old_dataset -> na nowy
    # Dla testów po prostu dopisujemy nowości do test/
    
    img_dir, lbl_dir = setup_yolo_dir(DEST_DIR_VAL)
    print("Konwersja i import do YOLO test datasetu...")
    
    # Skrypt przechodzi po podfolderach /cewki/X
    count = 0
    for folder in SOURCE_DIR.iterdir():
        if not folder.is_dir(): continue
        
        pngs = list(folder.glob("*.png"))
        jsons = list(folder.glob("*.json"))
        
        if pngs and jsons:
            print(f"Przetwarzam folder {folder.name}...")
            if convert_to_yolo_format(jsons[0], pngs[0], lbl_dir, img_dir):
                count += 1
                
    print(f"\nUkończono! Dodano {count} obrazów z cewkami do zbioru testowego.")
