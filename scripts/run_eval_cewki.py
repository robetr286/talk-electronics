from ultralytics import RTDETR

# Wczytaj stary model (sprzed dogrania cewek do zbioru testowego)
model = RTDETR('runs/detect/rtdetr/merged_opamp_rtdetr_v2/weights/best.pt')

# Oszacuj jego wydajność na wszystkich klasach ze zbioru test (ze zaktualizowanym folderem z obrazkami)
print("Ewaluacja poprzednich wag na nowym zbiorze testowym...")
results = model.val(data='configs/yolov8_v2_cewki.yaml', split='test', imgsz=640)
print("\n === EFEKTY PREDYKCJI ZE STARYMI WAGAMI NA NOWYM ZBIORZE ZE WSKAZANIEM ZAPOMINANIA ===")

