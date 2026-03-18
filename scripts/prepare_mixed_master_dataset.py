import json
import os
import shutil
import random
import glob

# USTAWIENIA
LABEL_STUDIO_JSON_DIR = "data/real/wszystkie_schematy"
LABEL_STUDIO_MEDIA_DIR = "/home/robert-b-k/.local/share/label-studio/media" # Zazwyczaj obrazy laduja w /media/upload/...
BASE_SYNTHETIC_DIR = "data/yolo_dataset/merged_opamp_14_01_2026"
NEW_MIXED_DIR = "data/yolo_dataset/mixed_master_v1"
SYNTHETIC_SAMPLE_SIZE = 800 # Ile weźmiemy starych, czystych schematów (aby nie zapomniał bazy)

CLASS_MAP = {
    'resistor': 0,
    'capacitor': 1,
    'inductor': 2,
    'diode': 3,
    'op_amp': 4
}

# PLIKI, KTÓRE MAJĄ BYĆ CAŁKOWICIE ZIGNOROWANE
BLACKLISTED_FILES = [
    "046fcc30-canvas-retouch-1768832637716.png",
    "7b55db3e-schemat_page31_oryginalny_2026-01-18_20-54-20.png",
    "33cbbd40-schemat_page35_prostowany_2026-01-18_20-48-37.png"
]

def create_dirs():
    if os.path.exists(NEW_MIXED_DIR):
        shutil.rmtree(NEW_MIXED_DIR)
    os.makedirs(f"{NEW_MIXED_DIR}/train/images", exist_ok=True)
    os.makedirs(f"{NEW_MIXED_DIR}/train/labels", exist_ok=True)
    os.makedirs(f"{NEW_MIXED_DIR}/test/images", exist_ok=True)
    os.makedirs(f"{NEW_MIXED_DIR}/test/labels", exist_ok=True)

def copy_and_convert_label(src, dst):
    lines = []
    with open(src, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) == 9:
                c = parts[0]
                coords = [float(x) for x in parts[1:]]
                xs = coords[0::2]
                ys = coords[1::2]
                xmin, xmax = min(xs), max(xs)
                ymin, ymax = min(ys), max(ys)
                xc = (xmin + xmax) / 2.0
                yc = (ymin + ymax) / 2.0
                w = xmax - xmin
                h = ymax - ymin
                lines.append(f"{c} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}\n")
            else:
                lines.append(line)
    with open(dst, 'w') as f:
        f.writelines(lines)
    if os.path.exists(NEW_MIXED_DIR):
        shutil.rmtree(NEW_MIXED_DIR)
    os.makedirs(f"{NEW_MIXED_DIR}/train/images", exist_ok=True)
    os.makedirs(f"{NEW_MIXED_DIR}/train/labels", exist_ok=True)
    os.makedirs(f"{NEW_MIXED_DIR}/test/images", exist_ok=True)
    os.makedirs(f"{NEW_MIXED_DIR}/test/labels", exist_ok=True)

def copy_synthetic_baseline():
    print(f"Kopiowanie {SYNTHETIC_SAMPLE_SIZE} czystych syntetycznych schematów jako kotwicę wiedzy...")
    train_images = list(glob.glob(f"{BASE_SYNTHETIC_DIR}/train/images/*.png")) + list(glob.glob(f"{BASE_SYNTHETIC_DIR}/train/images/*.jpg"))
    random.shuffle(train_images)
    
    # Kopiujemy do TRAIN
    for img_path in train_images[:SYNTHETIC_SAMPLE_SIZE]:
        fname = os.path.basename(img_path)
        lbl_path = img_path.replace("images", "labels").replace(".png", ".txt").replace(".jpg", ".txt")
        shutil.copy(img_path, f"{NEW_MIXED_DIR}/train/images/{fname}")
        if os.path.exists(lbl_path):
            copy_and_convert_label(lbl_path, f"{NEW_MIXED_DIR}/train/labels/{fname.replace('.png','.txt').replace('.jpg','.txt')}")

    # Przepisanie droche testowych by ewaluacja miala oba warianty
    test_images = list(glob.glob(f"{BASE_SYNTHETIC_DIR}/test/images/*.png")) + list(glob.glob(f"{BASE_SYNTHETIC_DIR}/test/images/*.jpg"))
    for img_path in test_images[:100]:
        # Omijaj pliki cewek kopiowane wczesniej recznie (nie są syntetykami)
        if "schemat" in os.path.basename(img_path).lower():
            continue
        fname = os.path.basename(img_path)
        lbl_path = img_path.replace("images", "labels").replace(".png", ".txt").replace(".jpg", ".txt")
        shutil.copy(img_path, f"{NEW_MIXED_DIR}/test/images/{fname}")
        if os.path.exists(lbl_path):
            copy_and_convert_label(lbl_path, f"{NEW_MIXED_DIR}/test/labels/{fname.replace('.png','.txt').replace('.jpg','.txt')}")

def process_labelstudio():
    json_files = glob.glob(f"{LABEL_STUDIO_JSON_DIR}/*.json")
    if not json_files:
        print(f"BŁĄD: Brak plików JSON w folderze: {LABEL_STUDIO_JSON_DIR}")
        return

    all_data = []
    for j_path in json_files:
        with open(j_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Jeżeli plik nie jest tablicą, przekonwertuj go
            if isinstance(data, dict):
                data = [data]
            all_data.extend(data)
            
    # Usuwanie duplikatów po 'id' zadania na wypadek nadpisania
    unique_tasks = {task.get('id', i): task for i, task in enumerate(all_data)}
    data = list(unique_tasks.values())
    
    # FILTROWANIE BLACKLISTY PRZED PODZIAŁEM:
    filtered_data = []
    for task in data:
        image_url = task.get("data", {}).get("image", "")
        base_name = os.path.basename(image_url)
        if base_name in BLACKLISTED_FILES:
            print(f"[-] Odrzucono plik z blacklisty: {base_name}")
            continue
        filtered_data.append(task)
        
    data = filtered_data
    print(f"Po filtracji zostało {len(data)} poprawnych schematów.")
    
    # 80% leci do train, 20% do test
    random.shuffle(data)
    split_index = int(len(data) * 0.8)

    for idx, task in enumerate(data):
        subset = "train" if idx < split_index else "test"
        
        # Pobieranie sciezki. LS exportuje "image": "/data/upload/12/img.png"
        image_url = task.get("data", {}).get("image", "")
        if image_url.startswith("/data/"):
            image_url = image_url.replace("/data/", "", 1)
        
        source_img = os.path.join(LABEL_STUDIO_MEDIA_DIR, image_url)
        img_name = os.path.basename(source_img)
        
        if not os.path.exists(source_img):
            print(f"Ostrzeżenie: Nie znaleziono dyskowego obrazu: {source_img}")
            continue
            
        shutil.copy(source_img, f"{NEW_MIXED_DIR}/{subset}/images/{img_name}")
        
        yolo_lines = []
        if task.get("annotations"):
            anno = task["annotations"][0]
            for res in anno.get("result", []):
                if res.get("type") == "rectanglelabels":
                    orig_w, orig_h = res["original_width"], res["original_height"]
                    v = res["value"]
                    x, y, w, h = v["x"], v["y"], v["width"], v["height"]
                    label_name = v["rectanglelabels"][0]
                    
                    if label_name in CLASS_MAP:
                        class_id = CLASS_MAP[label_name]
                        # Convert LS percents back to YOLO normalize
                        xc = (x + w / 2) / 100.0
                        yc = (y + h / 2) / 100.0
                        norm_w = w / 100.0
                        norm_h = h / 100.0
                        
                        # Limity
                        xc = sorted((0.0001, xc, 0.9999))[1]
                        yc = sorted((0.0001, yc, 0.9999))[1]
                        norm_w = sorted((0.0001, norm_w, 0.9999))[1]
                        norm_h = sorted((0.0001, norm_h, 0.9999))[1]
                        
                        yolo_lines.append(f"{class_id} {xc:.6f} {yc:.6f} {norm_w:.6f} {norm_h:.6f}\n")
                        
        with open(f"{NEW_MIXED_DIR}/{subset}/labels/{img_name.replace('.png','.txt').replace('.jpg','.txt')}", 'w') as f:
            f.writelines(yolo_lines)
            
    print("Miksowanie Zakończone pomyślnie. Utworzono poprawne podziały.")

def gen_yaml():
    yml_path = "configs/yolov8_mixed_master.yaml"
    with open(yml_path, 'w') as f:
        f.write(f"path: {os.path.abspath(NEW_MIXED_DIR)}\n")
        f.write("train: train/images\n")
        f.write("val: test/images\n")
        f.write("test: test/images\n\n")
        f.write("names:\n")
        f.write("  0: resistor\n")
        f.write("  1: capacitor\n")
        f.write("  2: inductor\n")
        f.write("  3: diode\n")
        f.write("  4: op_amp\n")
    print(f"Wygenerowano konigurację sieci w {yml_path}")

if __name__ == "__main__":
    create_dirs()
    copy_synthetic_baseline()
    process_labelstudio()
    gen_yaml()

