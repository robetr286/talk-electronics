import cv2
import os
import glob

CLASS_MAP_REV = {
    0: 'resistor',
    1: 'capacitor',
    2: 'inductor',
    3: 'diode',
    4: 'op_amp'
}
COLORS = {
    0: (0, 0, 255),   # Red
    1: (0, 255, 0),   # Green
    2: (255, 0, 0),   # Blue
    3: (0, 255, 255), # Yellow
    4: (255, 0, 255)  # Magenta
}

IMG_DIR_TRAIN = "data/yolo_dataset/mixed_master_v1/train/images"
LBL_DIR_TRAIN = "data/yolo_dataset/mixed_master_v1/train/labels"
IMG_DIR_TEST = "data/yolo_dataset/mixed_master_v1/test/images"
LBL_DIR_TEST = "data/yolo_dataset/mixed_master_v1/test/labels"
OUT_DIR = "debug/real_mixed_overlays"

os.makedirs(OUT_DIR, exist_ok=True)

def draw_boxes(img_path, txt_path, out_path):
    img = cv2.imread(img_path)
    if img is None:
        return
    h, w, _ = img.shape
    
    with open(txt_path, 'r') as f:
        lines = f.readlines()
        
    for line in lines:
        parts = line.strip().split()
        if len(parts) == 5:
            cls_id = int(parts[0])
            cx, cy, nw, nh = map(float, parts[1:])
            
            x_min = int((cx - nw / 2) * w)
            y_min = int((cy - nh / 2) * h)
            x_max = int((cx + nw / 2) * w)
            y_max = int((cy + nh / 2) * h)
            
            color = COLORS.get(cls_id, (255,255,255))
            label = CLASS_MAP_REV.get(cls_id, str(cls_id))
            
            cv2.rectangle(img, (x_min, y_min), (x_max, y_max), color, 4)
            cv2.putText(img, label, (x_min, y_min - 10), cv2.FONT_HERSHEY_SIMPLEX, 1.5, color, 3)
            
    cv2.imwrite(out_path, img)

count = 0
for folder_img, folder_lbl in [(IMG_DIR_TRAIN, LBL_DIR_TRAIN), (IMG_DIR_TEST, LBL_DIR_TEST)]:
    for img_file in glob.glob(folder_img + "/*.*"):
        # Szukamy tylko prawdziwych skanów, ignorując te czyste wygenerowane 
        if "schemat" in img_file.lower() or "-" in os.path.basename(img_file):
            # Prosty filtr odrzucający calkowicie wygenerowane losowe nazwy z uuid (syntetyki) jezeli to mozliwe
            base_name = os.path.basename(img_file)
            txt_file = os.path.join(folder_lbl, base_name.rsplit('.', 1)[0] + '.txt')
            if os.path.exists(txt_file):
                # Jeżeli tak wygląda jak plik pochodzący od Ciebie, robimy obraz w debugu
                if len(base_name) > 15: # zwykle maja np '0a3f...'
                    out_path = os.path.join(OUT_DIR, base_name)
                    draw_boxes(img_file, txt_file, out_path)
                    count += 1
print(f"Wygenerowano {count} zdjęć do weryfikacji w folderze {OUT_DIR}/ !")
