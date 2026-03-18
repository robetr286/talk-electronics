from ultralytics import RTDETR

# Kluczowa poprawka: upewniamy się, że ładujemy bazowy model detekcji RTDETR, a nie stary model segmentacyjny
model = RTDETR('weights/rtdetr_best.pt') 

results = model.train(
    data='configs/yolov8_mixed_master.yaml',
    task='detect',         # <--- WYMUSZENIE TRYBU DETEKCJI
    epochs=100,
    imgsz=640,
    batch=2,
    workers=4,
    device=0,
    project='runs/detect',
    name='rtdetr_mixed_master',
    exist_ok=True,
    patience=15,
    save=True
)
