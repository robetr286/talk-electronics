#!/usr/bin/env bash
# monitor_training.sh — monitoruje trening RT-DETR-L w pętli
# Użycie: bash monitor_training.sh [interwał_sekund]
#
# Domyślnie co 60s sprawdza:
# - czy proces treningowy żyje
# - najnowsze metryki z results.csv
# - zużycie GPU

INTERVAL=${1:-60}
CSV="runs/detect/rtdetr/merged_opamp_rtdetr_v2/results.csv"
LOG="runs/detect/rtdetr/training_v2.log"

echo "🔍 Monitor treningu RT-DETR-L (co ${INTERVAL}s, Ctrl+C aby zatrzymać)"
echo "================================================================"

while true; do
    echo ""
    echo "--- $(date '+%Y-%m-%d %H:%M:%S') ---"

    # Sprawdź proces
    PID=$(pgrep -f "resume_training.py" 2>/dev/null || pgrep -f "train_rtdetr.py" 2>/dev/null)
    if [ -z "$PID" ]; then
        echo "⚠️  BRAK procesu treningowego!"
        # Sprawdź czy trening się skończył (finalne ploty)
        if [ -f "runs/detect/rtdetr/merged_opamp_rtdetr/results.png" ]; then
            echo "✅ Trening zakończony — results.png istnieje"
            break
        else
            echo "❌ Trening przerwany — brak results.png"
            echo "   Ostatnie linie logu:"
            tail -5 "$LOG" 2>/dev/null
            break
        fi
    else
        echo "✅ Proces treningowy działa (PID: $PID)"
    fi

    # Najnowsze metryki
    if [ -f "$CSV" ]; then
        TOTAL=$(wc -l < "$CSV")
        EPOCHS=$((TOTAL - 1))
        echo "📊 Epok ukończonych: ${EPOCHS}/80"
        echo "   Ostatnie 3 epoki:"
        tail -3 "$CSV" | awk -F',' '{printf "   Ep %2s: P=%.3f R=%.3f mAP50=%.3f mAP50-95=%.3f\n", $1, $6, $7, $8, $9}'
    fi

    # GPU
    nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu \
        --format=csv,noheader,nounits 2>/dev/null | \
        awk -F', ' '{printf "🔥 GPU: %s%% | VRAM: %s/%s MiB | Temp: %s°C\n", $1, $2, $3, $4}'

    sleep "$INTERVAL"
done
