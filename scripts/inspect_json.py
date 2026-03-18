import json
import glob
import os

JSON_DIR = "data/real/wszystkie_schematy"

def inspect():
    json_files = glob.glob(f"{JSON_DIR}/*.json")
    all_data = []
    for j_path in json_files:
        with open(j_path, 'r', encoding='utf-8') as f:
            d = json.load(f)
            if isinstance(d, dict): d = [d]
            all_data.extend(d)
            
    print(f"Total tasks: {len(all_data)}")
    
    files_to_check = [
        "4e84a026-schemat_page17_wycinek-prostokat_2026-01-18_20-24-36.png",
        "7b55db3e-schemat_page31_oryginalny_2026-01-18_20-54-20.png",
        "33cbbd40-schemat_page35_prostowany_2026-01-18_20-48-37.png",
        "046fcc30-canvas-retouch-1768832637716.png"
    ]
    
    for task in all_data:
        img_url = task.get('data', {}).get('image', '')
        base = os.path.basename(img_url)
        
        for tgt in files_to_check:
            if tgt in base:
                print(f"\n--- Znaleziono info dla {tgt} ---")
                annos = task.get('annotations', [])
                print(f" Ilość adnotacji: {len(annos)}")
                for i, a in enumerate(annos):
                    res = a.get('result', [])
                    print(f" Adnotacja {i} (id: {a.get('id')}, cancelled: {a.get('was_cancelled')}): {len(res)} bounds")
                    for r in res:
                        if r.get('type') == 'rectanglelabels':
                            labels = r.get('value', {}).get('rectanglelabels', [])
                            print(f"   - {labels}")

if __name__ == "__main__":
    inspect()
