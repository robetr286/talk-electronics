from ultralytics import RTDETR

# Wczytaj model od najlepszych wag z poprzedniego treningu przed dodaniem cewek
model = RTDETR('runs/detect/rtdetr/merged_opamp_rtdetr_v2/weights/best.pt')

# Trening modelu dla klas uwzgledniającym zmodyfikowany zbiór z dopisanymi cewkami.
results = model.train(
    data='configs/yolov8_v2_cewki.yaml',
    epochs=15,    # krótszy trening tylko po to, by poduczyć nowych klas bez utraty wagi startowej
    imgsz=640,
    batch=4,
    name='merged_opamp_rtdetr_cewki',
    device=0,
    workers=0,
    val=True,
    patience=5,   # wcześniejsze zatrzymanie jeśli się przetrenuje na 1 klasę
    save_period=3
)
