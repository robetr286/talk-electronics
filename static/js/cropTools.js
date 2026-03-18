import { CROP_MAX_ZOOM, CROP_MIN_ZOOM, CROP_ZOOM_STEP, POLYGON_CLOSE_DISTANCE } from './constants.js';

export function initCropTools(dom, dependencies = {}) {
    const {
        cropCanvas,
        cropRulerLeft,
        cropRulerRight,
        cropOverlay,
        startCropBtn,
        polygonCropBtn,
        resetCropBtn,
        saveCropBtn,
        downloadCropBtn,
        overwriteOriginalBtn,
        deskewBtn,
        deskewManualBtn,
        deskewManualControls,
        deskewAngleSlider,
        deskewAngleValue,
        deskewApplyBtn,
        deskewCancelBtn,
        rotateLeftBtn,
        rotateRightBtn,
        cropInstructions,
        cropInstructionText,
        croppedPreview,
        cropStats,
        cropDimensions,
        cropSize,
        cropAspectRatio,
        cropQuality,
        cropZoomInBtn,
        cropZoomOutBtn,
        cropZoomResetBtn,
        cropZoomLabel,
        cropButtonsSection,
    } = dom;

    const {
        getDocumentContext = () => ({ token: null, currentPage: 1 }),
        onCropSaved = () => {},
    } = dependencies;

    const cropCtx = cropCanvas.getContext('2d');
    const rulerLeftCtx = cropRulerLeft ? cropRulerLeft.getContext('2d') : null;
    const rulerRightCtx = cropRulerRight ? cropRulerRight.getContext('2d') : null;

    let sourceImage = null;
    let sourceImageIsLocal = false; // true gdy obraz pochodzi z lokalnej modyfikacji (np. rotate 90°)
    let isCropping = false;
    let cropStartX = 0;
    let cropStartY = 0;
    let cropEndX = 0;
    let cropEndY = 0;
    let selectionMode = null;
    let cropRectCanvas = null;
    let cropRectImage = null;
    let croppedImageData = null;
    let previewCanvas = null;
    let previewCtx = null;
    let cropZoomLevel = 1;
    let cropPanX = 0;
    let cropPanY = 0;
    let cropBaseScale = 1;
    let isCropPanning = false;
    let cropPanStartX = 0;
    let cropPanStartY = 0;

    let polygonPointsCanvas = [];
    let polygonPointsImage = [];
    let polygonTempPoint = null;
    let isDrawingPolygon = false;
    let isDraggingPolygonPoint = false;
    let polygonDragIndex = -1;
    let isHoveringFirstPolygonPoint = false;

    let isResizingCrop = false;
    let resizeHandle = null;
    let resizeStartX = 0;
    let resizeStartY = 0;
    let originalCropRectCanvas = null;

    // Stan dla deskew z podglądem na żywo
    let deskewOriginalImage = null;  // Kopia obrazu przed rotacją
    let deskewPreviewAngle = 0;       // Aktualny kąt podglądu
    let isDeskewPreviewMode = false;  // Czy jesteśmy w trybie podglądu
    let lastSourceSignature = null;   // Służy do wykrywania, czy obraz faktycznie się zmienił
    // Ochrona przed nadpisaniem ręcznie zmodyfikowanego obrazu:
    let manualOverrideUntilContextChange = false; // true jeśli użytkownik ręcznie zmienił obraz (np. deskew) i chcemy zachować go dopóki kontekst nie zmieni się
    let manualOverrideSignature = null; // pełny podpis kontekstu w momencie ręcznej zmiany (stary sposób)
    let manualOverrideSourceUrl = null; // znormalizowany URL obrazu używany do sprawdzania czy to TEN sam plik (toleruje zmianę rozdzielczości/dpi)
    let instructionsHideTimer = null; // Timer do automatycznego ukrywania paska instrukcji
    let instructionsHideDeadline = null; // Czas (timestamp) kiedy instrukcja ma zostać ukryta

    function normalizeUrl(url) {
        if (!url) {
            return '';
        }
        try {
            const parsed = new URL(url, window.location.origin);
            parsed.search = '';
            parsed.hash = '';
            return parsed.toString();
        } catch (e) {
            // Fallback dla relative/niestandardowych ścieżek
            const clean = url.split('#')[0];
            return clean.split('?')[0];
        }
    }

    function buildSourceSignature(context) {
        if (!context) {
            return null;
        }
        const url = normalizeUrl(context.lastImageUrl || context.image?.src || '');
        const page = Number.isFinite(context.currentPage) ? context.currentPage : '';
        const dpi = Number.isFinite(context.imageDpi) ? context.imageDpi : '';
        const width = context.pageWidthPx || context.image?.width || '';
        const height = context.pageHeightPx || context.image?.height || '';
        return `${url}|${page}|${dpi}|${width}x${height}`;
    }

    function updateCropZoomUI() {
        if (!cropZoomLabel) {
            return;
        }
        const zoomPercent = Math.round(cropZoomLevel * 100);
        cropZoomLabel.textContent = `${zoomPercent}%`;
        if (cropZoomOutBtn) {
            cropZoomOutBtn.disabled = cropZoomLevel <= CROP_MIN_ZOOM;
        }
        if (cropZoomInBtn) {
            cropZoomInBtn.disabled = cropZoomLevel >= CROP_MAX_ZOOM;
        }
        if (cropZoomResetBtn) {
            cropZoomResetBtn.disabled = cropZoomLevel === 1;
        }
    }

    function canUseCropTools() {
        return Boolean(sourceImage);
    }

    function setButtonMode(button, isActive) {
        if (!button) {
            return;
        }
        button.classList.toggle('btn-success', isActive);
        button.classList.toggle('btn-outline-success', !isActive);
    }

    function clearSelectionState() {
        cropRectCanvas = null;
        cropRectImage = null;
        cropStartX = 0;
        cropStartY = 0;
        cropEndX = 0;
        cropEndY = 0;
        polygonPointsCanvas = [];
        polygonPointsImage = [];
        polygonTempPoint = null;
        isCropping = false;
        isDrawingPolygon = false;
        isDraggingPolygonPoint = false;
        polygonDragIndex = -1;
        isHoveringFirstPolygonPoint = false;
        croppedImageData = null;
        cropCanvas.classList.remove('cropping', 'has-crop');
        if (saveCropBtn) {
            saveCropBtn.disabled = true;
        }
        if (croppedPreview) {
            croppedPreview.innerHTML = '<p class="text-muted mb-0">Brak podglądu — zaznacz fragment schematu.</p>';
        }
        if (cropStats) {
            cropStats.classList.add('hidden');
        }
    }

    function updateCropInstructions(text, options = {}) {
        if (!cropInstructions || !cropInstructionText) {
            return;
        }
        const { autoHideMs = null } = options;
        cropInstructionText.textContent = text;
        cropInstructions.classList.remove('hidden');
        if (instructionsHideTimer) {
            clearTimeout(instructionsHideTimer);
            instructionsHideTimer = null;
        }
        instructionsHideDeadline = null;
        if (Number.isFinite(autoHideMs) && autoHideMs > 0) {
            const duration = Math.max(0, autoHideMs);
            instructionsHideDeadline = Date.now() + duration;
            instructionsHideTimer = setTimeout(() => {
                cropInstructions.classList.add('hidden');
                instructionsHideTimer = null;
                instructionsHideDeadline = null;
            }, duration);
        }
    }

    function hideCropInstructions() {
        if (!cropInstructions) {
            return;
        }
        if (instructionsHideTimer) {
            clearTimeout(instructionsHideTimer);
            instructionsHideTimer = null;
        }
        instructionsHideDeadline = null;
        cropInstructions.classList.add('hidden');
    }

    function calculateCropBaseScale() {
        if (!sourceImage) {
            cropBaseScale = 1;
            return;
        }
        const wrapper = cropCanvas.parentElement;
        const wrapperWidth = wrapper ? wrapper.clientWidth : sourceImage.width;
        const wrapperHeight = wrapper ? wrapper.clientHeight : sourceImage.height;
        // Nie skaluj powyżej 1 - startujemy w trybie "dopasuj do okna" bez powiększania mniejszego obrazu.
        cropBaseScale = Math.min(
            wrapperWidth / sourceImage.width,
            wrapperHeight / sourceImage.height,
            1,
        );
        if (!Number.isFinite(cropBaseScale) || cropBaseScale <= 0) {
            cropBaseScale = 1;
        }
    }

    function applyCropCanvasSize() {
        const wrapper = cropCanvas.parentElement;
        if (!wrapper) {
            return false;
        }
        const width = wrapper.clientWidth;
        const height = wrapper.clientHeight;
        if (width === 0 || height === 0) {
            return false;
        }
        if (cropCanvas.width === width && cropCanvas.height === height) {
            return true;
        }
        cropCanvas.width = width;
        cropCanvas.height = height;
        return true;
    }

    function clampCropPan() {
        if (!sourceImage) {
            return;
        }
        const wrapperWidth = cropCanvas.width;
        const wrapperHeight = cropCanvas.height;
        const scaledWidth = sourceImage.width * cropBaseScale * cropZoomLevel;
        const scaledHeight = sourceImage.height * cropBaseScale * cropZoomLevel;
        const maxPanX = Math.max(0, (scaledWidth - wrapperWidth) / 2);
        const maxPanY = Math.max(0, (scaledHeight - wrapperHeight) / 2);
        cropPanX = Math.max(-maxPanX, Math.min(maxPanX, cropPanX));
        cropPanY = Math.max(-maxPanY, Math.min(maxPanY, cropPanY));
    }

    function resetCropPan() {
        cropPanX = 0;
        cropPanY = 0;
    }

    // Funkcje rysowania linijek pionowych (lewa i prawa)
    function drawVerticalRuler(ctx, canvasElement, isRightSide = false) {
        if (!ctx || !sourceImage) return;

        const rulerWidth = canvasElement.width;
        const rulerHeight = canvasElement.height;

        // Wyczyść linijkę
        ctx.clearRect(0, 0, rulerWidth, rulerHeight);

        // Ustawienia stylu
        ctx.fillStyle = '#333';
        ctx.strokeStyle = '#666';
        ctx.font = '9px Arial';
        ctx.textAlign = 'right';
        ctx.textBaseline = 'middle';

        // Oblicz offset świata
        const wrapperHeight = cropCanvas.height;
        const scaledHeight = sourceImage.height * cropBaseScale * cropZoomLevel;
        const centerY = (wrapperHeight - scaledHeight) / 2 + cropPanY;

        // Rysuj znaczniki co 10px
        for (let y = 0; y < rulerHeight; y += 10) {
            // Współrzędna świata obrazu
            const worldY = Math.round((y - centerY) / (cropBaseScale * cropZoomLevel));

            // Szerokość znacznika
            let tickWidth = 2;
            if (y % 100 === 0) {
                tickWidth = 8;
                // Rysuj numer
                if (worldY >= 0 && worldY <= sourceImage.height) {
                    ctx.save();
                    const textX = isRightSide ? 10 : rulerWidth - 10;
                    ctx.translate(textX, y);
                    ctx.rotate(-Math.PI / 2);
                    ctx.textAlign = 'center';
                    ctx.fillText(worldY.toString(), 0, 0);
                    ctx.restore();
                }
            } else if (y % 50 === 0) {
                tickWidth = 5;
            }

            // Rysuj znacznik
            if (isRightSide) {
                ctx.fillRect(0, y, tickWidth, 1);  // Od lewej strony prawej linijki
            } else {
                ctx.fillRect(rulerWidth - tickWidth, y, tickWidth, 1);  // Od prawej strony lewej linijki
            }
        }
    }

    function updateRulers() {
        drawVerticalRuler(rulerLeftCtx, cropRulerLeft, false);  // Lewa linijka
        drawVerticalRuler(rulerRightCtx, cropRulerRight, true);  // Prawa linijka
    }

    function drawCropImage() {
        if (!sourceImage) {
            cropCtx.clearRect(0, 0, cropCanvas.width, cropCanvas.height);
            return;
        }
        const wrapperWidth = cropCanvas.width;
        const wrapperHeight = cropCanvas.height;
        cropCtx.clearRect(0, 0, wrapperWidth, wrapperHeight);

        // Jeśli w trybie podglądu deskew, rysuj z rotacją
        if (isDeskewPreviewMode && deskewPreviewAngle !== 0) {
            const scaledWidth = sourceImage.width * cropBaseScale * cropZoomLevel;
            const scaledHeight = sourceImage.height * cropBaseScale * cropZoomLevel;

            cropCtx.save();
            // Przesuń do środka canvas
            cropCtx.translate(wrapperWidth / 2 + cropPanX, wrapperHeight / 2 + cropPanY);
            // Obróć (kąt w radianach) - odwróć znak aby zgadzało się z rotacją stosowaną po stronie serwera
            cropCtx.rotate((-deskewPreviewAngle * Math.PI) / 180);
            // Rysuj obraz ze środkiem w (0, 0)
            cropCtx.drawImage(sourceImage, -scaledWidth / 2, -scaledHeight / 2, scaledWidth, scaledHeight);
            cropCtx.restore();
        } else {
            // Normalny tryb bez rotacji
            const scaledWidth = sourceImage.width * cropBaseScale * cropZoomLevel;
            const scaledHeight = sourceImage.height * cropBaseScale * cropZoomLevel;
            const centerX = (wrapperWidth - scaledWidth) / 2;
            const centerY = (wrapperHeight - scaledHeight) / 2;
            cropCtx.save();
            cropCtx.translate(centerX + cropPanX, centerY + cropPanY);
            cropCtx.drawImage(sourceImage, 0, 0, scaledWidth, scaledHeight);
            cropCtx.restore();
        }

        // Aktualizuj linijki po każdym rysowaniu
        updateRulers();
    }

    function getCropCoordinateTransform() {
        if (!sourceImage) {
            return null;
        }
        const wrapperWidth = cropCanvas.width;
        const wrapperHeight = cropCanvas.height;
        if (wrapperWidth === 0 || wrapperHeight === 0) {
            return null;
        }
        const scaledWidth = sourceImage.width * cropBaseScale * cropZoomLevel;
        const scaledHeight = sourceImage.height * cropBaseScale * cropZoomLevel;
        const centerX = (wrapperWidth - scaledWidth) / 2;
        const centerY = (wrapperHeight - scaledHeight) / 2;
        const imageLeft = centerX + cropPanX;
        const imageTop = centerY + cropPanY;
        const scaleToImage = 1 / (cropBaseScale * cropZoomLevel);
        return {
            imageLeft,
            imageTop,
            scaleToImage,
            scaleToCanvas: cropBaseScale * cropZoomLevel,
        };
    }

    function clampImageRect(rect) {
        if (!sourceImage || !rect) {
            return null;
        }
        const x = Math.max(0, Math.min(rect.x, sourceImage.width));
        const y = Math.max(0, Math.min(rect.y, sourceImage.height));
        const maxWidth = sourceImage.width - x;
        const maxHeight = sourceImage.height - y;
        const width = Math.max(0, Math.min(rect.width, maxWidth));
        const height = Math.max(0, Math.min(rect.height, maxHeight));
        if (width < 1 || height < 1) {
            return null;
        }
        return { x, y, width, height };
    }

    function canvasRectToImageRect(rect) {
        const transform = getCropCoordinateTransform();
        if (!transform || !rect) {
            return null;
        }
        const { imageLeft, imageTop, scaleToImage } = transform;
        const x = (rect.x - imageLeft) * scaleToImage;
        const y = (rect.y - imageTop) * scaleToImage;
        const width = rect.width * scaleToImage;
        const height = rect.height * scaleToImage;
        return clampImageRect({ x, y, width, height });
    }

    function imageRectToCanvasRect(rect) {
        const transform = getCropCoordinateTransform();
        if (!transform || !rect) {
            return null;
        }
        const { imageLeft, imageTop, scaleToCanvas } = transform;
        return {
            x: imageLeft + rect.x * scaleToCanvas,
            y: imageTop + rect.y * scaleToCanvas,
            width: rect.width * scaleToCanvas,
            height: rect.height * scaleToCanvas,
        };
    }

    function syncImageRectFromCanvas() {
        cropRectImage = canvasRectToImageRect(cropRectCanvas);
        if (cropRectImage) {
            cropRectCanvas = imageRectToCanvasRect(cropRectImage);
        } else {
            cropRectCanvas = null;
            croppedImageData = null;
        }
    }

    function syncCanvasRectFromImage() {
        if (!cropRectImage) {
            cropRectCanvas = null;
            return;
        }
        cropRectCanvas = imageRectToCanvasRect(cropRectImage);
    }

    function canvasPointToImagePoint(point) {
        const transform = getCropCoordinateTransform();
        if (!transform || !point) {
            return null;
        }
        const { imageLeft, imageTop, scaleToImage } = transform;
        return {
            x: (point.x - imageLeft) * scaleToImage,
            y: (point.y - imageTop) * scaleToImage,
        };
    }

    function imagePointToCanvasPoint(point) {
        const transform = getCropCoordinateTransform();
        if (!transform || !point) {
            return null;
        }
        const { imageLeft, imageTop, scaleToCanvas } = transform;
        return {
            x: imageLeft + point.x * scaleToCanvas,
            y: imageTop + point.y * scaleToCanvas,
        };
    }

    function syncPolygonImagePoints() {
        if (!polygonPointsCanvas.length) {
            polygonPointsImage = [];
            return;
        }
        const result = [];
        for (const pt of polygonPointsCanvas) {
            const converted = canvasPointToImagePoint(pt);
            if (!converted) {
                polygonPointsImage = [];
                return;
            }
            result.push(converted);
        }
        polygonPointsImage = result;
    }

    function syncPolygonCanvasPoints() {
        if (!polygonPointsImage.length) {
            polygonPointsCanvas = [];
            return;
        }
        const result = [];
        for (const pt of polygonPointsImage) {
            const converted = imagePointToCanvasPoint(pt);
            if (!converted) {
                polygonPointsCanvas = [];
                return;
            }
            result.push(converted);
        }
        polygonPointsCanvas = result;
    }

    function changeCropZoom(delta) {
        const newZoom = Math.max(CROP_MIN_ZOOM, Math.min(CROP_MAX_ZOOM, cropZoomLevel + delta));
        if (newZoom === cropZoomLevel) {
            return;
        }
        cropZoomLevel = newZoom;
        resetCropPan();
        drawCropImage();
        updateCropZoomUI();
        resumeSelectionAfterViewportChange();
        generateCropPreview();
    }

    function resetCropZoom() {
        cropZoomLevel = 1;
        resetCropPan();
        drawCropImage();
        updateCropZoomUI();
        resumeSelectionAfterViewportChange();
        generateCropPreview();
    }

    function resumeSelectionAfterViewportChange() {
        if (selectionMode === 'rectangle') {
            if (cropRectImage) {
                syncCanvasRectFromImage();
                if (cropRectCanvas) {
                    drawSelectionOverlay();
                }
            }
        } else if (selectionMode === 'polygon') {
            if (polygonPointsImage.length >= 1) {
                syncPolygonCanvasPoints();
                drawSelectionOverlay();
            }
        }
    }

    function clampMouseToImage(mouseX, mouseY) {
        if (!sourceImage) {
            return { x: mouseX, y: mouseY };
        }
        const wrapperWidth = cropCanvas.width;
        const wrapperHeight = cropCanvas.height;
        const scaledWidth = sourceImage.width * cropBaseScale * cropZoomLevel;
        const scaledHeight = sourceImage.height * cropBaseScale * cropZoomLevel;
        const centerX = (wrapperWidth - scaledWidth) / 2;
        const centerY = (wrapperHeight - scaledHeight) / 2;
        const imageLeft = centerX + cropPanX;
        const imageTop = centerY + cropPanY;
        const imageRight = imageLeft + scaledWidth;
        const imageBottom = imageTop + scaledHeight;
        const clampedX = Math.max(imageLeft, Math.min(imageRight, mouseX));
        const clampedY = Math.max(imageTop, Math.min(imageBottom, mouseY));
        return { x: clampedX, y: clampedY };
    }

    function drawSelectionOverlay(tempPoint = null) {
        if (selectionMode === 'polygon') {
            drawPolygonSelection(tempPoint);
            return;
        }
        drawCropRectangle();
    }

    function drawPolygonSelection(tempPoint = null) {
        const renderPoints = [...polygonPointsCanvas];
        if (tempPoint) {
            renderPoints.push(tempPoint);
        }
        if (!renderPoints.length) {
            return;
        }
        const shouldClose = !isDrawingPolygon && !tempPoint && polygonPointsCanvas.length >= 3;
        cropCtx.save();
        cropCtx.lineWidth = 2;
        cropCtx.strokeStyle = '#31f576';
        cropCtx.fillStyle = 'rgba(49, 245, 118, 0.12)';
        cropCtx.beginPath();
        renderPoints.forEach((pt, index) => {
            if (index === 0) {
                cropCtx.moveTo(pt.x, pt.y);
            } else {
                cropCtx.lineTo(pt.x, pt.y);
            }
        });
        if (shouldClose) {
            cropCtx.closePath();
            cropCtx.fill();
        }
        cropCtx.stroke();
        if (isDrawingPolygon && isHoveringFirstPolygonPoint && polygonPointsCanvas.length >= 3) {
            const first = polygonPointsCanvas[0];
            const last = polygonPointsCanvas[polygonPointsCanvas.length - 1];
            cropCtx.setLineDash([6, 6]);
            cropCtx.strokeStyle = 'rgba(255, 221, 87, 0.9)';
            cropCtx.beginPath();
            cropCtx.moveTo(last.x, last.y);
            cropCtx.lineTo(first.x, first.y);
            cropCtx.stroke();
            cropCtx.setLineDash([]);
        }
        cropCtx.lineWidth = 2;
        const handleSize = 10;
        polygonPointsCanvas.forEach((pt, index) => {
            const isFirst = index === 0;
            const isHighlighted = isFirst && isDrawingPolygon && isHoveringFirstPolygonPoint;
            cropCtx.fillStyle = isHighlighted ? '#ffdd57' : '#31f576';
            cropCtx.strokeStyle = '#ffffff';
            cropCtx.fillRect(pt.x - handleSize / 2, pt.y - handleSize / 2, handleSize, handleSize);
            cropCtx.strokeRect(pt.x - handleSize / 2, pt.y - handleSize / 2, handleSize, handleSize);
        });
        cropCtx.restore();
    }

    function drawCropRectangle(rectOverride = null) {
        let x;
        let y;
        let width;
        let height;
        const selection = rectOverride || cropRectCanvas;
        if (selection) {
            ({ x, y, width, height } = selection);
        } else {
            x = Math.min(cropStartX, cropEndX);
            y = Math.min(cropStartY, cropEndY);
            width = Math.abs(cropEndX - cropStartX);
            height = Math.abs(cropEndY - cropStartY);
        }
        if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
            return;
        }
        cropCtx.strokeStyle = '#31f576';
        cropCtx.lineWidth = 3;
        cropCtx.strokeRect(x, y, width, height);
        cropCtx.strokeStyle = 'rgba(255, 255, 255, 0.8)';
        cropCtx.lineWidth = 1;
        cropCtx.strokeRect(x + 1.5, y + 1.5, width - 3, height - 3);
        const handleSize = 10;
        cropCtx.fillStyle = '#31f576';
        cropCtx.strokeStyle = '#ffffff';
        cropCtx.lineWidth = 2;
        cropCtx.fillRect(x - handleSize / 2, y - handleSize / 2, handleSize, handleSize);
        cropCtx.strokeRect(x - handleSize / 2, y - handleSize / 2, handleSize, handleSize);
        cropCtx.fillRect(x + width - handleSize / 2, y - handleSize / 2, handleSize, handleSize);
        cropCtx.strokeRect(x + width - handleSize / 2, y - handleSize / 2, handleSize, handleSize);
        cropCtx.fillRect(x - handleSize / 2, y + height - handleSize / 2, handleSize, handleSize);
        cropCtx.strokeRect(x - handleSize / 2, y + height - handleSize / 2, handleSize, handleSize);
        cropCtx.fillRect(x + width - handleSize / 2, y + height - handleSize / 2, handleSize, handleSize);
        cropCtx.strokeRect(x + width - handleSize / 2, y + height - handleSize / 2, handleSize, handleSize);
        if (width > 50 && height > 50) {
            cropCtx.fillStyle = 'rgba(5, 18, 29, 0.8)';
            cropCtx.font = 'bold 12px sans-serif';
            cropCtx.textAlign = 'center';
            cropCtx.textBaseline = 'middle';
            const labelText = `${Math.round(width)} × ${Math.round(height)}`;
            const textWidth = cropCtx.measureText(labelText).width + 10;
            cropCtx.fillRect(x + width / 2 - textWidth / 2, y - 20, textWidth, 16);
            cropCtx.fillStyle = '#31f576';
            cropCtx.fillText(labelText, x + width / 2, y - 12);
        }
    }

    function updateCropStats(width, height, canvas) {
        if (!cropDimensions || !cropSize || !cropAspectRatio || !cropQuality || !cropStats) {
            return;
        }
        const dataURL = canvas.toDataURL('image/png');
        const sizeKB = Math.round((dataURL.length * 0.75) / 1024);
        const gcd = (a, b) => (b === 0 ? a : gcd(b, a % b));
        const divisor = gcd(Math.round(width), Math.round(height));
        const ratioW = Math.round(width / divisor);
        const ratioH = Math.round(height / divisor);
        let qualityClass = 'quality-good';
        let qualityText = '✓ Dobra';
        if (width < 200 || height < 200) {
            qualityClass = 'quality-poor';
            qualityText = '⚠ Niska - zbyt mały obszar';
        } else if (width < 400 || height < 400) {
            qualityClass = 'quality-medium';
            qualityText = '○ Średnia - rozważ większy obszar';
        }
        cropDimensions.textContent = `${Math.round(width)} × ${Math.round(height)} px`;
        cropSize.textContent = `${sizeKB} KB`;
        cropAspectRatio.textContent = `${ratioW}:${ratioH}`;
        cropQuality.textContent = qualityText;
        cropQuality.className = qualityClass;
        cropStats.classList.remove('hidden');
    }

    function generateCropPreview() {
        if (!sourceImage) {
            return;
        }

        const hasPolygonSelection = polygonPointsCanvas.length >= 3 && !isDrawingPolygon;
        if (hasPolygonSelection) {
            syncPolygonImagePoints();
            if (polygonPointsImage.length < 3) {
                return;
            }
            const xs = polygonPointsImage.map((pt) => pt.x);
            const ys = polygonPointsImage.map((pt) => pt.y);
            const minX = Math.max(0, Math.floor(Math.min(...xs)));
            const minY = Math.max(0, Math.floor(Math.min(...ys)));
            const maxX = Math.min(sourceImage.width, Math.ceil(Math.max(...xs)));
            const maxY = Math.min(sourceImage.height, Math.ceil(Math.max(...ys)));
            const width = Math.max(1, maxX - minX);
            const height = Math.max(1, maxY - minY);
            if (!previewCanvas) {
                previewCanvas = document.createElement('canvas');
                previewCtx = previewCanvas.getContext('2d');
            }
            previewCanvas.width = width;
            previewCanvas.height = height;
            previewCanvas.style.width = '100%';
            previewCanvas.style.height = 'auto';
            previewCanvas.style.maxHeight = '100%';
            previewCtx.clearRect(0, 0, width, height);
            previewCtx.save();
            previewCtx.beginPath();
            polygonPointsImage.forEach((pt, index) => {
                const offsetX = pt.x - minX;
                const offsetY = pt.y - minY;
                if (index === 0) {
                    previewCtx.moveTo(offsetX, offsetY);
                } else {
                    previewCtx.lineTo(offsetX, offsetY);
                }
            });
            previewCtx.closePath();
            previewCtx.clip();
            previewCtx.drawImage(sourceImage, minX, minY, width, height, 0, 0, width, height);
            previewCtx.restore();
            if (croppedPreview) {
                croppedPreview.innerHTML = '';
                croppedPreview.appendChild(previewCanvas);
            }
            cropCanvas.classList.add('has-crop');
            croppedImageData = {
                type: 'polygon',
                canvas: previewCanvas,
                bounds: { x: minX, y: minY, width, height },
                points: polygonPointsImage.map((pt) => ({ x: pt.x, y: pt.y })),
            };
            if (saveCropBtn) {
                saveCropBtn.disabled = false;
            }
            updateCropStats(width, height, previewCanvas);
            return;
        }

        if (!cropRectCanvas && !isCropping) {
            if (croppedPreview) {
                croppedPreview.innerHTML = '<p class="text-muted">Zaznacz obszar, aby zobaczyć podgląd</p>';
            }
            cropCanvas.classList.remove('has-crop');
            croppedImageData = null;
            if (cropStats) {
                cropStats.classList.add('hidden');
            }
            if (saveCropBtn) {
                saveCropBtn.disabled = true;
            }
            return;
        }

        syncImageRectFromCanvas();
        if (!cropRectImage) {
            if (croppedPreview) {
                croppedPreview.innerHTML = '<p class="text-muted">Zaznacz obszar, aby zobaczyć podgląd</p>';
            }
            cropCanvas.classList.remove('has-crop');
            croppedImageData = null;
            if (cropStats) {
                cropStats.classList.add('hidden');
            }
            if (saveCropBtn) {
                saveCropBtn.disabled = true;
            }
            return;
        }

        const targetWidth = Math.max(1, Math.round(cropRectImage.width));
        const targetHeight = Math.max(1, Math.round(cropRectImage.height));
        if (!previewCanvas) {
            previewCanvas = document.createElement('canvas');
            previewCtx = previewCanvas.getContext('2d');
        }
        previewCanvas.width = targetWidth;
        previewCanvas.height = targetHeight;
        previewCanvas.style.width = '100%';
        previewCanvas.style.height = 'auto';
        previewCanvas.style.maxHeight = '100%';
        previewCtx.clearRect(0, 0, targetWidth, targetHeight);
        previewCtx.drawImage(
            sourceImage,
            cropRectImage.x,
            cropRectImage.y,
            cropRectImage.width,
            cropRectImage.height,
            0,
            0,
            targetWidth,
            targetHeight,
        );
        if (croppedPreview) {
            croppedPreview.innerHTML = '';
            croppedPreview.appendChild(previewCanvas);
        }
        cropCanvas.classList.add('has-crop');
        croppedImageData = {
            type: 'rectangle',
            canvas: previewCanvas,
            x: cropRectImage.x,
            y: cropRectImage.y,
            width: cropRectImage.width,
            height: cropRectImage.height,
        };
        if (saveCropBtn) {
            saveCropBtn.disabled = false;
        }
        updateCropStats(targetWidth, targetHeight, previewCanvas);
    }

    function finalizePolygonSelection() {
        if (polygonPointsCanvas.length < 3) {
            return;
        }
        if (polygonPointsCanvas.length >= 2) {
            const lastIndex = polygonPointsCanvas.length - 1;
            const last = polygonPointsCanvas[lastIndex];
            const prev = polygonPointsCanvas[lastIndex - 1];
            if (last && prev && Math.abs(last.x - prev.x) < 0.5 && Math.abs(last.y - prev.y) < 0.5) {
                polygonPointsCanvas.pop();
            }
        }
        syncPolygonImagePoints();
        if (polygonPointsImage.length < 3) {
            return;
        }
        isDrawingPolygon = false;
        polygonTempPoint = null;
        isDraggingPolygonPoint = false;
        polygonDragIndex = -1;
        isHoveringFirstPolygonPoint = false;
        cropCanvas.classList.add('has-crop');
        updateCropInstructions('Wielokąt gotowy. Użyj przycisku Zapisz, aby zachować fragment.');
        drawCropImage();
        syncPolygonCanvasPoints();
        drawSelectionOverlay();
        generateCropPreview();
        if (saveCropBtn) {
            saveCropBtn.disabled = false;
        }
    }

    function getResizeHandle(mouseX, mouseY) {
        if (selectionMode !== 'rectangle' || !cropRectCanvas) {
            return null;
        }
        const hitAreaSize = 15;
        const x = cropRectCanvas.x;
        const y = cropRectCanvas.y;
        const width = cropRectCanvas.width;
        const height = cropRectCanvas.height;
        const isInArea = (px, py, cx, cy, size) => px >= cx - size && px <= cx + size && py >= cy - size && py <= cy + size;
        if (isInArea(mouseX, mouseY, x, y, hitAreaSize)) {
            return 'tl';
        }
        if (isInArea(mouseX, mouseY, x + width, y, hitAreaSize)) {
            return 'tr';
        }
        if (isInArea(mouseX, mouseY, x, y + height, hitAreaSize)) {
            return 'bl';
        }
        if (isInArea(mouseX, mouseY, x + width, y + height, hitAreaSize)) {
            return 'br';
        }
        return null;
    }

    function getPolygonHandle(mouseX, mouseY) {
        if (selectionMode !== 'polygon' || polygonPointsCanvas.length === 0) {
            return -1;
        }
        const hitArea = 12;
        for (let i = 0; i < polygonPointsCanvas.length; i += 1) {
            const pt = polygonPointsCanvas[i];
            if (Math.abs(mouseX - pt.x) <= hitArea && Math.abs(mouseY - pt.y) <= hitArea) {
                return i;
            }
        }
        return -1;
    }

    function updateCropCursor(mouseX, mouseY) {
        if (selectionMode === 'polygon') {
            if (!isDrawingPolygon) {
                const handleIndex = getPolygonHandle(mouseX, mouseY);
                if (handleIndex !== -1) {
                    cropCanvas.style.cursor = 'grab';
                    return;
                }
            }
            cropCanvas.style.cursor = 'crosshair';
            return;
        }
        if (selectionMode === 'rectangle') {
            if (isCropping) {
                cropCanvas.style.cursor = 'crosshair';
                return;
            }
            if (cropZoomLevel > 1 && !cropRectCanvas) {
                cropCanvas.style.cursor = 'grab';
                return;
            }
            const handle = getResizeHandle(mouseX, mouseY);
            if (handle) {
                if (handle === 'tl' || handle === 'br') {
                    cropCanvas.style.cursor = 'nwse-resize';
                } else {
                    cropCanvas.style.cursor = 'nesw-resize';
                }
            } else if (cropRectCanvas) {
                cropCanvas.style.cursor = 'default';
            } else {
                cropCanvas.style.cursor = 'crosshair';
            }
            return;
        }
        cropCanvas.style.cursor = 'crosshair';
    }

    function setSelectionMode(mode, options = {}) {
        if (!['rectangle', 'polygon'].includes(mode)) {
            return;
        }
        const { force = false } = options;
        if (!force && selectionMode === mode) {
            return;
        }
        selectionMode = mode;
        clearSelectionState();
        if (mode === 'rectangle') {
            updateCropInstructions('Kliknij i przeciągnij na obrazie, aby zaznaczyć prostokąt, następnie zapisz go przyciskiem.');
            isCropping = true;
            cropCanvas.classList.add('cropping');
        } else {
            updateCropInstructions('Klikaj kolejne punkty wielokąta. Zakończ podwójnym kliknięciem lub prawym przyciskiem myszy.');
            isDrawingPolygon = false;
            cropCanvas.classList.remove('cropping');
        }
        setButtonMode(startCropBtn, mode === 'rectangle');
        setButtonMode(polygonCropBtn, mode === 'polygon');
        if (resetCropBtn) {
            resetCropBtn.disabled = false;
        }
        drawCropImage();
        drawSelectionOverlay();
    }

    function enableCropControls() {
        if (startCropBtn) {
            startCropBtn.disabled = false;
        }
        if (polygonCropBtn) {
            polygonCropBtn.disabled = false;
        }
        if (downloadCropBtn) {
            downloadCropBtn.disabled = false;
        }
        if (overwriteOriginalBtn) {
            overwriteOriginalBtn.disabled = false;
        }
        if (rotateLeftBtn) {
            rotateLeftBtn.disabled = false;
        }
        if (rotateRightBtn) {
            rotateRightBtn.disabled = false;
        }
        if (cropZoomInBtn) {
            cropZoomInBtn.disabled = false;
        }
        if (cropZoomOutBtn) {
            cropZoomOutBtn.disabled = false;
        }
        if (cropZoomResetBtn) {
            cropZoomResetBtn.disabled = false;
        }
    }

    function disableCropControls() {
        if (startCropBtn) {
            startCropBtn.disabled = true;
        }
        if (polygonCropBtn) {
            polygonCropBtn.disabled = true;
        }
        if (downloadCropBtn) {
            downloadCropBtn.disabled = true;
        }
        if (overwriteOriginalBtn) {
            overwriteOriginalBtn.disabled = true;
        }
        if (rotateLeftBtn) {
            rotateLeftBtn.disabled = true;
        }
        if (rotateRightBtn) {
            rotateRightBtn.disabled = true;
        }
        if (cropZoomInBtn) {
            cropZoomInBtn.disabled = true;
        }
        if (cropZoomOutBtn) {
            cropZoomOutBtn.disabled = true;
        }
        if (cropZoomResetBtn) {
            cropZoomResetBtn.disabled = true;
        }
        if (resetCropBtn) {
            resetCropBtn.disabled = true;
        }
        hideCropInstructions();
    }

    function updateCropCanvas(options = {}) {
        const { preserveViewport = false } = options;
        const previousViewport = preserveViewport
            ? { zoom: cropZoomLevel, panX: cropPanX, panY: cropPanY }
            : null;

        // Zachowaj stan paska instrukcji przed odświeżeniem
        const instructionsVisible = cropInstructions && !cropInstructions.classList.contains('hidden');
        const instructionsText = cropInstructionText ? cropInstructionText.textContent : '';
        const instructionsRemainingMs = instructionsHideDeadline
            ? Math.max(0, instructionsHideDeadline - Date.now())
            : null;

        if (!applyCropCanvasSize()) {
            return;
        }
        cropCtx.clearRect(0, 0, cropCanvas.width, cropCanvas.height);
        if (!sourceImage) {
            disableCropControls();
            return;
        }
        enableCropControls();
        setButtonMode(startCropBtn, selectionMode === 'rectangle');
        setButtonMode(polygonCropBtn, selectionMode === 'polygon');
        cropZoomLevel = 1;
        calculateCropBaseScale();
        resetCropPan();
        if (previousViewport) {
            cropZoomLevel = Math.max(CROP_MIN_ZOOM, Math.min(CROP_MAX_ZOOM, previousViewport.zoom || 1));
            cropPanX = previousViewport.panX;
            cropPanY = previousViewport.panY;
            clampCropPan();
        }
        drawCropImage();
        updateCropZoomUI();
        resumeSelectionAfterViewportChange();
        generateCropPreview();

        // Przywróć pasek instrukcji, jeśli był widoczny
        if (instructionsVisible && cropInstructions && cropInstructionText) {
            const autoHideMs = instructionsRemainingMs && instructionsRemainingMs > 0 ? instructionsRemainingMs : null;
            updateCropInstructions(instructionsText, { autoHideMs });
        }
    }

    function handleMouseDown(event) {
        if (!canUseCropTools()) {
            return;
        }
        const rect = cropCanvas.getBoundingClientRect();
        const scaleX = cropCanvas.width / rect.width;
        const scaleY = cropCanvas.height / rect.height;
        const rawMouseX = (event.clientX - rect.left) * scaleX;
        const rawMouseY = (event.clientY - rect.top) * scaleY;
        let mouseX = rawMouseX;
        let mouseY = rawMouseY;
        if (selectionMode === 'polygon') {
            const clamped = clampMouseToImage(mouseX, mouseY);
            mouseX = clamped.x;
            mouseY = clamped.y;
            if (isDrawingPolygon) {
                isHoveringFirstPolygonPoint = false;
                if (polygonPointsCanvas.length >= 3) {
                    const first = polygonPointsCanvas[0];
                    const dxFirst = mouseX - first.x;
                    const dyFirst = mouseY - first.y;
                    const distFirst = Math.hypot(dxFirst, dyFirst);
                    isHoveringFirstPolygonPoint = distFirst <= POLYGON_CLOSE_DISTANCE;
                }
            }
            if (!isDrawingPolygon && event.button === 0) {
                const handleIndex = getPolygonHandle(mouseX, mouseY);
                if (handleIndex !== -1) {
                    event.preventDefault();
                    isDraggingPolygonPoint = true;
                    polygonDragIndex = handleIndex;
                    polygonTempPoint = null;
                    return;
                }
            }
            if (event.button === 0) {
                event.preventDefault();
                if (!isDrawingPolygon) {
                    isDrawingPolygon = true;
                    polygonPointsCanvas = [];
                    polygonPointsImage = [];
                    if (saveCropBtn) {
                        saveCropBtn.disabled = true;
                    }
                    updateCropInstructions('Klikaj kolejne punkty wielokąta. Zakończ podwójnym kliknięciem lub prawym przyciskiem myszy.');
                }
                polygonPointsCanvas.push({ x: mouseX, y: mouseY });
                syncPolygonImagePoints();
                drawCropImage();
                drawSelectionOverlay();
                return;
            }
            if (!isDrawingPolygon && cropZoomLevel > 1 && (event.button === 1 || event.button === 2)) {
                event.preventDefault();
                isCropPanning = true;
                cropPanStartX = rawMouseX - cropPanX;
                cropPanStartY = rawMouseY - cropPanY;
                cropCanvas.classList.add('is-panning');
            }
            if (isDrawingPolygon && event.button === 2) {
                event.preventDefault();
            }
            return;
        }
        const clamped = clampMouseToImage(mouseX, mouseY);
        mouseX = clamped.x;
        mouseY = clamped.y;
        const handle = getResizeHandle(mouseX, mouseY);
        if (handle && cropRectCanvas) {
            event.preventDefault();
            isResizingCrop = true;
            resizeHandle = handle;
            resizeStartX = mouseX;
            resizeStartY = mouseY;
            originalCropRectCanvas = { ...cropRectCanvas };
            cropCanvas.classList.add('is-resizing');
            return;
        }
        if (isCropping && event.button === 0) {
            cropStartX = mouseX;
            cropStartY = mouseY;
            cropEndX = cropStartX;
            cropEndY = cropStartY;
        } else if (cropZoomLevel > 1 && (event.button === 2 || event.button === 1)) {
            event.preventDefault();
            isCropPanning = true;
            cropPanStartX = rawMouseX - cropPanX;
            cropPanStartY = rawMouseY - cropPanY;
            cropCanvas.classList.add('is-panning');
        }
    }

    function handleMouseMove(event) {
        if (!canUseCropTools()) {
            return;
        }
        const rect = cropCanvas.getBoundingClientRect();
        const scaleX = cropCanvas.width / rect.width;
        const scaleY = cropCanvas.height / rect.height;
        const rawMouseX = (event.clientX - rect.left) * scaleX;
        const rawMouseY = (event.clientY - rect.top) * scaleY;
        updateCropCursor(rawMouseX, rawMouseY);
        if (isResizingCrop && selectionMode === 'rectangle' && resizeHandle && originalCropRectCanvas) {
            const clamped = clampMouseToImage(rawMouseX, rawMouseY);
            const mouseX = clamped.x;
            const mouseY = clamped.y;
            const deltaX = mouseX - resizeStartX;
            const deltaY = mouseY - resizeStartY;
            let newX = originalCropRectCanvas.x;
            let newY = originalCropRectCanvas.y;
            let newWidth = originalCropRectCanvas.width;
            let newHeight = originalCropRectCanvas.height;
            switch (resizeHandle) {
                case 'tl':
                    newX = originalCropRectCanvas.x + deltaX;
                    newY = originalCropRectCanvas.y + deltaY;
                    newWidth = originalCropRectCanvas.width - deltaX;
                    newHeight = originalCropRectCanvas.height - deltaY;
                    break;
                case 'tr':
                    newY = originalCropRectCanvas.y + deltaY;
                    newWidth = originalCropRectCanvas.width + deltaX;
                    newHeight = originalCropRectCanvas.height - deltaY;
                    break;
                case 'bl':
                    newX = originalCropRectCanvas.x + deltaX;
                    newWidth = originalCropRectCanvas.width - deltaX;
                    newHeight = originalCropRectCanvas.height + deltaY;
                    break;
                case 'br':
                    newWidth = originalCropRectCanvas.width + deltaX;
                    newHeight = originalCropRectCanvas.height + deltaY;
                    break;
                default:
                    break;
            }
            if (newWidth > 20 && newHeight > 20) {
                cropRectCanvas = { x: newX, y: newY, width: newWidth, height: newHeight };
                drawCropImage();
                drawSelectionOverlay();
                generateCropPreview();
            }
            return;
        }
        if (selectionMode === 'polygon') {
            if (isDraggingPolygonPoint && polygonDragIndex !== -1) {
                const clamped = clampMouseToImage(rawMouseX, rawMouseY);
                polygonPointsCanvas[polygonDragIndex] = { x: clamped.x, y: clamped.y };
                polygonTempPoint = null;
                syncPolygonImagePoints();
                drawCropImage();
                drawSelectionOverlay();
                generateCropPreview();
                return;
            }
            if (isDrawingPolygon) {
                const clamped = clampMouseToImage(rawMouseX, rawMouseY);
                polygonTempPoint = { x: clamped.x, y: clamped.y };
                if (polygonPointsCanvas.length >= 3) {
                    const first = polygonPointsCanvas[0];
                    const dxFirst = clamped.x - first.x;
                    const dyFirst = clamped.y - first.y;
                    const distFirst = Math.hypot(dxFirst, dyFirst);
                    isHoveringFirstPolygonPoint = distFirst <= POLYGON_CLOSE_DISTANCE;
                } else {
                    isHoveringFirstPolygonPoint = false;
                }
                drawCropImage();
                drawSelectionOverlay(polygonTempPoint);
            } else {
                polygonTempPoint = null;
                isHoveringFirstPolygonPoint = false;
            }
        } else if (selectionMode === 'rectangle' && isCropping && event.buttons === 1) {
            const clamped = clampMouseToImage(rawMouseX, rawMouseY);
            cropEndX = clamped.x;
            cropEndY = clamped.y;
            drawCropImage();
            drawSelectionOverlay();
        }
        if (isCropPanning) {
            cropPanX = rawMouseX - cropPanStartX;
            cropPanY = rawMouseY - cropPanStartY;
            clampCropPan();
            drawCropImage();
            if (selectionMode === 'polygon' && polygonPointsImage.length) {
                syncPolygonCanvasPoints();
                if (isDrawingPolygon) {
                    polygonTempPoint = null;
                }
                drawSelectionOverlay();
            } else if (selectionMode === 'rectangle') {
                if (cropRectImage) {
                    syncCanvasRectFromImage();
                }
                drawSelectionOverlay();
            }
        }
    }

    function handleMouseUp(event) {
        if (!canUseCropTools()) {
            return;
        }
        if (isDraggingPolygonPoint) {
            const rect = cropCanvas.getBoundingClientRect();
            const scaleX = cropCanvas.width / rect.width;
            const scaleY = cropCanvas.height / rect.height;
            const rawMouseX = (event.clientX - rect.left) * scaleX;
            const rawMouseY = (event.clientY - rect.top) * scaleY;
            const clamped = clampMouseToImage(rawMouseX, rawMouseY);
            if (polygonDragIndex !== -1) {
                polygonPointsCanvas[polygonDragIndex] = { x: clamped.x, y: clamped.y };
            }
            syncPolygonImagePoints();
            drawCropImage();
            drawSelectionOverlay();
            generateCropPreview();
            isDraggingPolygonPoint = false;
            polygonDragIndex = -1;
            isHoveringFirstPolygonPoint = false;
            return;
        }
        if (isResizingCrop) {
            isResizingCrop = false;
            resizeHandle = null;
            originalCropRectCanvas = null;
            cropCanvas.classList.remove('is-resizing');
            generateCropPreview();
            return;
        }
        if (isCropPanning) {
            isCropPanning = false;
            cropCanvas.classList.remove('is-panning');
            clampCropPan();
            drawCropImage();
            resumeSelectionAfterViewportChange();
            if (selectionMode === 'polygon' && isDrawingPolygon) {
                polygonTempPoint = null;
                isHoveringFirstPolygonPoint = false;
                drawSelectionOverlay();
            }
            if (selectionMode === 'polygon') {
                if (!isDrawingPolygon && polygonPointsImage.length >= 3) {
                    generateCropPreview();
                }
            } else {
                generateCropPreview();
            }
            return;
        }
        if (selectionMode === 'polygon') {
            if (isDrawingPolygon && event.button === 2) {
                finalizePolygonSelection();
            }
            return;
        }
        if (selectionMode === 'rectangle' && isCropping) {
            const rect = cropCanvas.getBoundingClientRect();
            const scaleX = cropCanvas.width / rect.width;
            const scaleY = cropCanvas.height / rect.height;
            const mouseX = (event.clientX - rect.left) * scaleX;
            const mouseY = (event.clientY - rect.top) * scaleY;
            const clamped = clampMouseToImage(mouseX, mouseY);
            cropEndX = clamped.x;
            cropEndY = clamped.y;
            const x = Math.min(cropStartX, cropEndX);
            const y = Math.min(cropStartY, cropEndY);
            const width = Math.abs(cropEndX - cropStartX);
            const height = Math.abs(cropEndY - cropStartY);
            if (width > 10 && height > 10) {
                cropRectCanvas = { x, y, width, height };
                isCropping = false;
                cropCanvas.classList.remove('cropping');
                cropCanvas.classList.add('has-crop');
                generateCropPreview();
                if (saveCropBtn) {
                    saveCropBtn.disabled = false;
                }
            }
        }
    }

    function handleDoubleClick(event) {
        if (!canUseCropTools()) {
            return;
        }
        if (selectionMode === 'polygon' && isDrawingPolygon && polygonPointsCanvas.length >= 3) {
            const rect = cropCanvas.getBoundingClientRect();
            const scaleX = cropCanvas.width / rect.width;
            const scaleY = cropCanvas.height / rect.height;
            const mouseX = (event.clientX - rect.left) * scaleX;
            const mouseY = (event.clientY - rect.top) * scaleY;
            const clamped = clampMouseToImage(mouseX, mouseY);
            const first = polygonPointsCanvas[0];
            const distanceToFirst = Math.hypot(clamped.x - first.x, clamped.y - first.y);
            if (distanceToFirst <= POLYGON_CLOSE_DISTANCE) {
                event.preventDefault();
                finalizePolygonSelection();
            }
        }
    }

    function handleMouseLeave() {
        cropCanvas.classList.remove('panning');
        isCropPanning = false;
        if (isDraggingPolygonPoint) {
            isDraggingPolygonPoint = false;
            polygonDragIndex = -1;
            polygonTempPoint = null;
            syncPolygonImagePoints();
            drawCropImage();
            drawSelectionOverlay();
            generateCropPreview();
        }
        isHoveringFirstPolygonPoint = false;
        if (selectionMode === 'polygon' && isDrawingPolygon && canUseCropTools()) {
            polygonTempPoint = null;
            drawCropImage();
            drawSelectionOverlay();
        }
    }

    function bindCropEvents() {
        cropCanvas.addEventListener('mousedown', handleMouseDown);
        cropCanvas.addEventListener('mousemove', handleMouseMove);
        cropCanvas.addEventListener('mouseup', handleMouseUp);
        cropCanvas.addEventListener('mouseleave', handleMouseLeave);
        cropCanvas.addEventListener('contextmenu', (event) => event.preventDefault());
        cropCanvas.addEventListener('dblclick', handleDoubleClick);
        cropCanvas.addEventListener('mouseenter', () => {
            if (!isCropping && cropZoomLevel > 1) {
                cropCanvas.classList.add('panning');
            }
        });
    }

    // ========================================================================
    // v7 - DESKEW (Prostowanie obrazu)
    // ========================================================================

    async function deskewCurrentImage() {
        if (!sourceImage || !deskewBtn) {
            console.warn('Brak obrazu źródłowego lub przycisku deskew');
            return;
        }

        const originalText = deskewBtn.innerHTML;
        deskewBtn.disabled = true;
        deskewBtn.innerHTML = '🔄 Prostowanie...';

        try {
            // Pobierz URL aktualnego obrazu na canvas
            const imageUrl = sourceImage.src;

            // Przygotuj payload - jeśli obraz jest blob/data URL lub nie jest URL-em serwera, wyślij imageData z canvas
            let payload;
            if (imageUrl && (imageUrl.startsWith('blob:') || imageUrl.startsWith('data:') || !(imageUrl.startsWith('http') || imageUrl.startsWith('/')))) {
                const dataUrl = cropCanvas.toDataURL('image/png');
                payload = { imageData: dataUrl };
            } else {
                payload = { imageUrl };
            }

            // Wywołaj endpoint deskew
            const response = await fetch('/processing/deskew', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Błąd prostowania');
            }

            const result = await response.json();

            // Wczytaj wyprostowany obraz
            const img = new Image();
            img.onload = () => {
                sourceImage = img;
                sourceImageIsLocal = false;
                isDeskewPreviewMode = false;
                deskewPreviewAngle = 0;
                deskewOriginalImage = null;
                if (deskewAngleSlider) {
                    deskewAngleSlider.value = '0';
                }
                if (deskewAngleValue) {
                    deskewAngleValue.textContent = '0.0';
                }
                drawCropImage();

                // Pokaż komunikat o wykrytym kącie
                const angle = result.detectedAngle;
                const msg = Math.abs(angle) < 0.5
                    ? '✅ Obraz już prosty (kąt < 0.5°)'
                    : `✅ Wyprostowano obraz (wykryty kąt: ${angle}°)`;
                updateCropInstructions(msg);

                console.log('Deskew sukces:', result);
            };
            img.onerror = () => {
                throw new Error('Nie można wczytać wyprostowanego obrazu');
            };
            img.src = result.previewUrl;

        } catch (error) {
            console.error('Błąd deskew:', error);
            updateCropInstructions(`❌ Błąd prostowania: ${error.message}`);
        } finally {
            deskewBtn.disabled = false;
            deskewBtn.innerHTML = originalText;
        }
    }

    async function deskewWithManualAngle(manualAngle) {
        if (!sourceImage || !deskewApplyBtn) {
            console.warn('Brak obrazu źródłowego lub przycisku apply');
            return;
        }

        const originalText = deskewApplyBtn.innerHTML;
        deskewApplyBtn.disabled = true;
        deskewApplyBtn.innerHTML = '🔄 Prostowanie...';

        try {
            // Pobierz URL aktualnego obrazu na canvas
            const imageUrl = sourceImage.src || '';

            // Preferuj pełno-rozmiarowy URL dokumentu (jeśli dostępny), aby zachować oryginalną rozdzielczość
            const docContext = getDocumentContext() || {};
            const preferredUrl = docContext.lastImageUrl || imageUrl;
            const isLocalSource = sourceImageIsLocal || imageUrl.startsWith('data:');
            const hasServerUrl = Boolean(preferredUrl && (preferredUrl.startsWith('http') || preferredUrl.startsWith('/')));

            // Przygotuj payload - jeśli mamy serwerowy URL użyj go (zachowamy pełną rozdzielczość),
            // w przeciwnym razie wyślij dane z canvas (dataURL)
            let payload;
            if (!isLocalSource && hasServerUrl) {
                payload = { imageUrl: preferredUrl, manualAngle: manualAngle };
            } else if (imageUrl.startsWith('data:')) {
                payload = { imageData: imageUrl, manualAngle: manualAngle };
            } else {
                const dataUrl = cropCanvas.toDataURL('image/png');
                payload = { imageData: dataUrl, manualAngle: manualAngle };
            }

            // Wywołaj endpoint deskew z ręcznym kątem
            const response = await fetch('/processing/deskew', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Błąd prostowania');
            }

            const result = await response.json();

            // Wczytaj wyprostowany obraz
            const img = new Image();
            img.onload = () => {
                sourceImage = img;
                sourceImageIsLocal = false;
                // Ustal podpis na podstawie aktualnego kontekstu, by późniejsze odświeżenia nie nadpisały ręcznie obróconego obrazu.
                const context = getDocumentContext() || {};
                const contextSignature = buildSourceSignature(context);
                const contextUrl = normalizeUrl(context.lastImageUrl || context.image?.src || '');
                if (contextSignature) {
                    lastSourceSignature = contextSignature;
                    manualOverrideUntilContextChange = true;
                    manualOverrideSignature = contextSignature;
                    manualOverrideSourceUrl = contextUrl;
                    console.debug('[cropTools] manual override ustawiony po deskew (signature):', contextSignature, 'url:', contextUrl);
                }
                drawCropImage();

                // Pokaż komunikat o zastosowanym kącie
                updateCropInstructions(`✅ Obrócono o ${manualAngle.toFixed(1)}°`);

                console.log('Deskew manual sukces:', result);
            };
            img.onerror = () => {
                throw new Error('Nie można wczytać wyprostowanego obrazu');
            };
            img.src = result.previewUrl;

        } catch (error) {
            console.error('Błąd deskew manual:', error);
            updateCropInstructions(`❌ Błąd prostowania: ${error.message}`);
        } finally {
            deskewApplyBtn.disabled = false;
            deskewApplyBtn.innerHTML = originalText;
        }
    }

    function rotateImage90(direction = 'cw') {
        if (!sourceImage) {
            updateCropInstructions('❌ Brak obrazu do obrotu');
            return;
        }
        const angle = direction === 'ccw' ? -90 : 90;
        const width = sourceImage.width;
        const height = sourceImage.height;
        const swapSides = Math.abs(angle) === 90 || Math.abs(angle) === 270;
        const canvas = document.createElement('canvas');
        canvas.width = swapSides ? height : width;
        canvas.height = swapSides ? width : height;
        const ctx = canvas.getContext('2d');
        ctx.imageSmoothingEnabled = false;
        ctx.save();
        if (angle === 90) {
            ctx.translate(canvas.width, 0);
        } else if (angle === -90) {
            ctx.translate(0, canvas.height);
        } else {
            ctx.translate(canvas.width, canvas.height);
        }
        ctx.rotate((angle * Math.PI) / 180);
        ctx.drawImage(sourceImage, 0, 0);
        ctx.restore();

        const rotatedUrl = canvas.toDataURL('image/png');
        const img = new Image();
        img.onload = () => {
            sourceImage = img;
            sourceImageIsLocal = true;
            lastSourceSignature = null; // wymuś pełne odświeżenie przy kolejnym setSourceImage
            // Ustaw manual override, by rotacja 90° również nie była nadpisywana natychmiast
            const ctx = getDocumentContext() || {};
            const contextSignature90 = buildSourceSignature(ctx);
            const contextUrl90 = normalizeUrl(ctx.lastImageUrl || ctx.image?.src || '');
            if (contextSignature90) {
                manualOverrideUntilContextChange = true;
                manualOverrideSignature = contextSignature90;
                manualOverrideSourceUrl = contextUrl90;
                console.debug('[cropTools] manual override ustawiony po rotate90 (signature):', contextSignature90, 'url:', contextUrl90);
            }
            clearSelectionState();
            updateCropCanvas();
            updateCropInstructions(`✅ Obrócono o ${angle}° (bez zmiany rozdzielczości)`);
        };
        img.onerror = () => {
            updateCropInstructions('❌ Nie udało się obrócić obrazu');
        };
        img.src = rotatedUrl;
    }

    async function downloadCurrentImage() {
        if (!sourceImage) {
            console.warn('Brak obrazu do pobrania');
            updateCropInstructions('❌ Brak obrazu do pobrania');
            return;
        }

        const context = getDocumentContext() || {};
        const pageNum = context.currentPage || 1;
        const timestamp = new Date()
            .toISOString()
            .replace(/T/, '_')
            .replace(/:/g, '-')
            .replace(/\..+/, '');

        if (croppedImageData?.canvas) {
            try {
                const cropType = croppedImageData.type === 'polygon' ? 'wycinek-wielokat' : 'wycinek-prostokat';
                const filename = `schemat_page${pageNum}_${cropType}_${timestamp}.png`;
                const blob = await new Promise((resolve, reject) => {
                    croppedImageData.canvas.toBlob((result) => {
                        if (result) {
                            resolve(result);
                            return;
                        }
                        reject(new Error('Nie udało się przygotować pliku PNG.'));
                    }, 'image/png');
                });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                updateCropInstructions(`✅ Pobrano kadr: ${filename}`);
                return;
            } catch (error) {
                console.error('Błąd pobierania kadru:', error);
                updateCropInstructions('❌ Błąd pobierania kadru');
                return;
            }
        }

        try {
            let operation = 'oryginalny';
            if (sourceImage.src.includes('/retouch/deskew-')) {
                operation = 'prostowany';
            } else if (sourceImage.src.includes('/processed/')) {
                operation = 'przetworzony';
            } else if (sourceImage.src.includes('_crop_')) {
                operation = 'wykadrowany';
            }
            const filename = `schemat_page${pageNum}_${operation}_${timestamp}.png`;
            const response = await fetch(sourceImage.src);
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            updateCropInstructions(`✅ Pobrano: ${filename}`);
        } catch (error) {
            console.error('Błąd pobierania obrazu:', error);
            updateCropInstructions('❌ Błąd pobierania obrazu');
        }
    }

    async function saveCroppedImage() {
        if (!croppedImageData || !saveCropBtn) {
            return;
        }
        const originalText = saveCropBtn.innerHTML;
        saveCropBtn.disabled = true;
        saveCropBtn.innerHTML = '💾 Zapisywanie...';
        let localObjectUrl = null;
        try {
            const blob = await new Promise((resolve, reject) => {
                croppedImageData.canvas.toBlob((result) => {
                    if (result) {
                        resolve(result);
                        return;
                    }
                    reject(new Error('Nie udało się wygenerować pliku PNG z kadrowania.'));
                }, 'image/png');
            });
            localObjectUrl = URL.createObjectURL(blob);
            const context = getDocumentContext() || {};
            const formData = new FormData();
            formData.append('file', blob, 'cropped_area.png');
            formData.append('token', context.token || '');
            formData.append('page', context.currentPage || 1);
            if (croppedImageData.type === 'polygon') {
                formData.append('selection_type', 'polygon');
                formData.append('polygon_points', JSON.stringify(croppedImageData.points));
                formData.append('selection_bounds', JSON.stringify(croppedImageData.bounds));
            } else {
                formData.append('selection_type', 'rectangle');
                formData.append(
                    'selection_rect',
                    JSON.stringify({
                        x: croppedImageData.x,
                        y: croppedImageData.y,
                        width: croppedImageData.width,
                        height: croppedImageData.height,
                    }),
                );
            }
            const response = await fetch('/save-crop', {
                method: 'POST',
                body: formData,
            });
            const data = await response.json();
            if (data.success) {
                saveCropBtn.innerHTML = '✅ Zapisano!';
                try {
                    const contextDetails = getDocumentContext() || {};
                    const payload = {
                        url: data.url,
                        filename: data.filename,
                        sizeKb: data.size_kb,
                        selectionType: croppedImageData?.type,
                        objectUrl: localObjectUrl,
                        geometry:
                            croppedImageData?.type === 'polygon'
                                ? { points: croppedImageData.points, bounds: croppedImageData.bounds }
                                : {
                                      x: croppedImageData?.x,
                                      y: croppedImageData?.y,
                                      width: croppedImageData?.width,
                                      height: croppedImageData?.height,
                                  },
                        documentContext: {
                            token: contextDetails.token,
                            currentPage: contextDetails.currentPage,
                            filename: contextDetails.filename,
                        },
                        savedAt: new Date().toISOString(),
                    };
                    if (typeof onCropSaved === 'function') {
                        console.log('[cropTools] Wywołuję callback onCropSaved z payload:', payload);
                        onCropSaved(payload);
                    } else {
                        console.warn('[cropTools] onCropSaved nie jest funkcją');
                    }
                } catch (notifyError) {
                    console.error('Error propagating saved crop info:', notifyError);
                }
                setTimeout(() => {
                    saveCropBtn.innerHTML = originalText;
                    saveCropBtn.disabled = false;
                }, 2000);
            } else {
                throw new Error(data.error || 'Unknown error');
            }
        } catch (error) {
            console.error('Error saving crop:', error);
            saveCropBtn.innerHTML = '❌ Błąd zapisu';
            setTimeout(() => {
                saveCropBtn.innerHTML = originalText;
                saveCropBtn.disabled = false;
            }, 2000);
            if (localObjectUrl) {
                URL.revokeObjectURL(localObjectUrl);
            }
        }
    }

    async function overwriteOriginalFile() {
        if (!sourceImage || !overwriteOriginalBtn) {
            return;
        }

        const context = getDocumentContext() || {};
        if (!context.token) {
            updateCropInstructions('❌ Brak tokenu dokumentu — wgraj plik ponownie.');
            return;
        }

        const confirmed = window.confirm(
            'Nadpiszemy oryginalny plik źródłowy. Zrobimy kopię zapasową w /uploads/backups. Kontynuować?',
        );
        if (!confirmed) {
            return;
        }

        const previousLabel = overwriteOriginalBtn.innerHTML;
        overwriteOriginalBtn.disabled = true;
        overwriteOriginalBtn.innerHTML = '⏳ Nadpisywanie...';

        try {
            const canvas = document.createElement('canvas');
            canvas.width = sourceImage.width;
            canvas.height = sourceImage.height;
            const ctx = canvas.getContext('2d');
            ctx.imageSmoothingEnabled = false;
            ctx.drawImage(sourceImage, 0, 0);

            const blob = await new Promise((resolve, reject) => {
                canvas.toBlob((result) => {
                    if (result) {
                        resolve(result);
                        return;
                    }
                    reject(new Error('Nie udało się przygotować pliku do nadpisania.'));
                }, 'image/png');
            });

            const formData = new FormData();
            formData.append('file', blob, 'overwrite.png');
            formData.append('token', context.token || '');
            if (context.currentPage) {
                formData.append('page', context.currentPage);
            }
            if (context.filename) {
                formData.append('filename', context.filename);
            }

            const response = await fetch('/overwrite-original', {
                method: 'POST',
                body: formData,
            });
            const payload = await response.json();
            if (!response.ok || !payload.success) {
                throw new Error(payload.error || 'Nie udało się nadpisać pliku.');
            }

            overwriteOriginalBtn.innerHTML = '✅ Nadpisano';
            const backupInfo = payload.backup_filename ? `Kopia: ${payload.backup_filename}` : 'Utworzono kopię zapasową';
            updateCropInstructions(`✅ Oryginał zastąpiony. ${backupInfo}`, { autoHideMs: 4000 });

            // Jeśli backend zwrócił nowy podgląd, wymuś przeładowanie obrazu z cache-bustingiem
            if (payload.preview_url) {
                const refreshedUrl = `${payload.preview_url}?ts=${Date.now()}`;
                const img = new Image();
                img.onload = () => {
                    sourceImage = img;
                    sourceImageIsLocal = false;
                    lastSourceSignature = null;
                    // Po nadpisaniu oryginału resetujemy manual override — to nie jest już ręczna zmiana użytkownika
                    manualOverrideUntilContextChange = false;
                    manualOverrideSignature = null;
                    clearSelectionState();
                    updateCropCanvas();
                    updateCropInstructions('🔄 Załadowano zaktualizowany podgląd (odświeżono cache).', { autoHideMs: 3000 });
                    // Pokaż akcje do pobrania / pokazania ścieżki
                    showOverwriteActions(payload);
                };
                img.onerror = () => {
                    console.warn('Nie udało się odświeżyć podglądu po nadpisaniu.');
                    showOverwriteActions(payload);
                };
                img.src = refreshedUrl;
            } else {
                // Jeśli nie ma podglądu, też daj akcje
                showOverwriteActions(payload);
            }
        } catch (error) {
            console.error('Błąd nadpisywania oryginału:', error);
            overwriteOriginalBtn.innerHTML = '❌ Błąd';
            updateCropInstructions(`❌ Błąd nadpisywania: ${error.message}`);
        } finally {
            setTimeout(() => {
                overwriteOriginalBtn.innerHTML = previousLabel;
                overwriteOriginalBtn.disabled = false;
            }, 2000);
        }
    }

    function wireControlButtons() {
        if (startCropBtn) {
            startCropBtn.addEventListener('click', () => {
                if (!canUseCropTools()) {
                    return;
                }
                setSelectionMode('rectangle', { force: true });
            });
        }
        if (polygonCropBtn) {
            polygonCropBtn.addEventListener('click', () => {
                if (!canUseCropTools()) {
                    return;
                }
                setSelectionMode('polygon', { force: true });
            });
        }
        if (resetCropBtn) {
            resetCropBtn.addEventListener('click', () => {
                if (selectionMode) {
                    setSelectionMode(selectionMode, { force: true });
                } else {
                    clearSelectionState();
                    hideCropInstructions();
                    setButtonMode(startCropBtn, false);
                    setButtonMode(polygonCropBtn, false);
                    drawCropImage();
                    drawSelectionOverlay();
                }
                if (startCropBtn) {
                    startCropBtn.disabled = !canUseCropTools();
                }
                if (polygonCropBtn) {
                    polygonCropBtn.disabled = !canUseCropTools();
                }
                if (!selectionMode) {
                    resetCropBtn.disabled = true;
                }
            });
        }
        if (saveCropBtn) {
            saveCropBtn.addEventListener('click', saveCroppedImage);
        }
        if (downloadCropBtn) {
            downloadCropBtn.addEventListener('click', downloadCurrentImage);
        }
        if (overwriteOriginalBtn) {
            overwriteOriginalBtn.addEventListener('click', () => {
                void overwriteOriginalFile();
            });
        }
        if (rotateLeftBtn) {
            rotateLeftBtn.addEventListener('click', () => rotateImage90('ccw'));
        }
        if (rotateRightBtn) {
            rotateRightBtn.addEventListener('click', () => rotateImage90('cw'));
        }
        if (deskewBtn) {
            deskewBtn.addEventListener('click', deskewCurrentImage);
        }
        if (deskewManualBtn) {
            deskewManualBtn.addEventListener('click', () => {
                if (!sourceImage) {
                    const context = typeof getDocumentContext === 'function' ? getDocumentContext() : null;
                    if (context?.image) {
                        setSourceImageFromContext(context);
                    }
                }
                if (!sourceImage) {
                    console.warn('Brak obrazu źródłowego');
                    updateCropInstructions('❌ Brak obrazu do prostowania');
                    return;
                }

                // Zapisz oryginalny obraz (kopia referencji)
                deskewOriginalImage = sourceImage;
                deskewPreviewAngle = 0;
                isDeskewPreviewMode = true;

                // Pokaż kontrolki ręczne
                deskewManualControls.classList.remove('hidden');
                deskewAngleSlider.value = 0;
                deskewAngleValue.textContent = '0.0';

                // Pokaż instrukcję
                updateCropInstructions('🎚️ Przesuń suwak aby zobaczyć podgląd rotacji');
            });
        }
        if (deskewAngleSlider) {
            deskewAngleSlider.addEventListener('input', (e) => {
                const angle = parseFloat(e.target.value);
                deskewAngleValue.textContent = angle.toFixed(1);

                // PODGLĄD NA ŻYWO - zmień kąt i przerysuj
                if (isDeskewPreviewMode) {
                    deskewPreviewAngle = angle;
                    drawCropImage();  // Rysuje z rotacją

                    // Aktualizuj instrukcję
                    updateCropInstructions(`🔄 Podgląd: obrót o ${angle.toFixed(1)}° (kliknij "Zastosuj" aby zapisać)`);
                }
            });
        }
        if (deskewApplyBtn) {
            deskewApplyBtn.addEventListener('click', async () => {
                const angle = parseFloat(deskewAngleSlider.value);

                if (Math.abs(angle) > 0.01) {
                    await deskewWithManualAngle(angle);
                    isDeskewPreviewMode = false;
                    deskewPreviewAngle = 0;
                    deskewOriginalImage = null;
                    if (deskewAngleSlider) {
                        deskewAngleSlider.value = '0';
                    }
                    if (deskewAngleValue) {
                        deskewAngleValue.textContent = '0.0';
                    }
                    return;
                }

                // Kąt 0 - zachowaj kontrolki, ale pokaż informację
                updateCropInstructions('✅ Anulowano (kąt = 0°)');
                deskewOriginalImage = null;
                isDeskewPreviewMode = false;
                deskewPreviewAngle = 0;
                if (deskewAngleSlider) {
                    deskewAngleSlider.value = '0';
                }
                if (deskewAngleValue) {
                    deskewAngleValue.textContent = '0.0';
                }
                drawCropImage();
            });
        }
        if (deskewCancelBtn) {
            deskewCancelBtn.addEventListener('click', () => {
                // Przywróć oryginalny obraz (anuluj podgląd)
                isDeskewPreviewMode = false;
                deskewPreviewAngle = 0;
                deskewOriginalImage = null;

                // Ukryj kontrolki bez zmian
                if (deskewManualControls) {
                    deskewManualControls.classList.add('hidden');
                }
                deskewAngleSlider.value = 0;
                deskewAngleValue.textContent = '0.0';

                // Przerysuj bez rotacji
                drawCropImage();

                // Ukryj instrukcję
                hideCropInstructions();
            });
        }
        if (cropZoomInBtn) {
            cropZoomInBtn.addEventListener('click', () => changeCropZoom(CROP_ZOOM_STEP));
        }
        if (cropZoomOutBtn) {
            cropZoomOutBtn.addEventListener('click', () => changeCropZoom(-CROP_ZOOM_STEP));
        }
        if (cropZoomResetBtn) {
            cropZoomResetBtn.addEventListener('click', resetCropZoom);
        }
    }

    bindCropEvents();
    wireControlButtons();
    disableCropControls();
    updateCropZoomUI();

    // Pomocnicza funkcja UI dla akcji po nadpisaniu oryginału
    function showOverwriteActions(payload) {
        if (!cropButtonsSection) return;

        // Usuń istniejący kontener akcji jeśli już istnieje
        const existing = document.getElementById('overwriteActionsContainer');
        if (existing) {
            existing.remove();
        }

        const container = document.createElement('div');
        container.id = 'overwriteActionsContainer';
        container.className = 'd-flex gap-2 mt-2';

        // Download button
        const downloadBtn = document.createElement('button');
        downloadBtn.type = 'button';
        downloadBtn.className = 'btn btn-sm btn-outline-primary';
        downloadBtn.textContent = '💾 Pobierz poprawioną wersję';
        downloadBtn.addEventListener('click', async () => {
            try {
                const url = payload.preview_url ? `${payload.preview_url}?ts=${Date.now()}` : null;
                if (!url) {
                    updateCropInstructions('❌ Brak URL podglądu do pobrania');
                    return;
                }
                const suggested = payload.rendered_filename || payload.new_source_path?.split('/')?.pop() || 'poprawiony.png';
                const a = document.createElement('a');
                a.href = url;
                a.download = suggested;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                updateCropInstructions('✅ Rozpoczęto pobieranie');
            } catch (e) {
                console.error('Błąd pobierania poprawionej wersji', e);
                updateCropInstructions('❌ Błąd pobierania');
            }
        });

        // Copy path button
        const copyBtn = document.createElement('button');
        copyBtn.type = 'button';
        copyBtn.className = 'btn btn-sm btn-outline-secondary';
        copyBtn.textContent = '📁 Pokaż ścieżkę';
        copyBtn.addEventListener('click', async () => {
            const path = payload.new_source_path || payload.original_filename || '';
            try {
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    await navigator.clipboard.writeText(path);
                    updateCropInstructions('✅ Ścieżka skopiowana do schowka');
                } else {
                    // Fallback: pokaz w instrukcji
                    updateCropInstructions(`📁 Ścieżka: ${path}`);
                }
            } catch (err) {
                console.warn('Nie udało się skopiować do schowka', err);
                updateCropInstructions(`📁 Ścieżka: ${path}`);
            }
        });

        // Close button
        const closeBtn = document.createElement('button');
        closeBtn.type = 'button';
        closeBtn.className = 'btn btn-sm btn-outline-secondary';
        closeBtn.textContent = '✖ Ukryj';
        closeBtn.addEventListener('click', () => container.remove());

        container.appendChild(downloadBtn);
        container.appendChild(copyBtn);
        container.appendChild(closeBtn);

        cropButtonsSection.appendChild(container);

        // Dodaj przyciski: Zapisz jako (wywoła Save As), Otwórz w nowej karcie, Pobierz i Pokaż ścieżkę
        const saveAsBtn = document.createElement('button');
        saveAsBtn.type = 'button';
        saveAsBtn.className = 'btn btn-sm btn-primary';
        saveAsBtn.textContent = '💾 Zapisz jako...';
        saveAsBtn.addEventListener('click', () => {
            void downloadAndSuggest(payload);
        });

        const openBtn = document.createElement('button');
        openBtn.type = 'button';
        openBtn.className = 'btn btn-sm btn-outline-primary';
        openBtn.textContent = '🔍 Otwórz w nowej karcie';
        openBtn.addEventListener('click', () => {
            const src = payload.preview_url || payload.new_source_path || null;
            if (!src) {
                updateCropInstructions('❌ Brak URL do otwarcia');
                return;
            }
            const url = src.includes('?') ? `${src}&ts=${Date.now()}` : `${src}?ts=${Date.now()}`;
            window.open(url, '_blank', 'noreferrer');
            updateCropInstructions('🔍 Otworzono w nowej karcie — użyj Zapisz jako żeby nadpisać plik lokalny');
        });

        container.insertBefore(saveAsBtn, container.firstChild);
        container.insertBefore(openBtn, container.firstChild);

        // Automatyczne usunięcie po 20s
        setTimeout(() => {
            const el = document.getElementById('overwriteActionsContainer');
            if (el) el.remove();
        }, 20000);
    }

    async function downloadAndSuggest(payload) {
        try {
            const src = payload.preview_url || payload.new_source_path || null;
            if (!src) {
                updateCropInstructions('❌ Brak URL do pobrania');
                return;
            }
            const url = src.includes('?') ? `${src}&ts=${Date.now()}` : `${src}?ts=${Date.now()}`;
            updateCropInstructions('🔽 Pobieram poprawioną wersję do zapisania...');
            const res = await fetch(url);
            if (!res.ok) {
                throw new Error(`HTTP ${res.status}`);
            }
            const blob = await res.blob();
            const suggested = payload.original_filename || payload.rendered_filename || (payload.new_source_path && payload.new_source_path.split('/').pop()) || 'poprawiony.png';

            // Preferencjalnie użyj File System Access API (Save File Picker) jeżeli dostępne
            if (window.showSaveFilePicker) {
                try {
                    const opts = {
                        suggestedName: suggested,
                        types: [
                            {
                                description: 'Image',
                                accept: {
                                    'image/png': ['.png'],
                                    'image/jpeg': ['.jpg', '.jpeg'],
                                },
                            },
                        ],
                    };
                    const handle = await window.showSaveFilePicker(opts);
                    const writable = await handle.createWritable();
                    await writable.write(blob);
                    await writable.close();
                    updateCropInstructions('✅ Zapisano plik lokalnie');
                    return;
                } catch (err) {
                    console.warn('showSaveFilePicker failed:', err);
                    // fallthrough do otwarcia w nowej karcie
                }
            }

            // Fallback: otwórz blob w nowej karcie i poproś użytkownika o Zapisz jako
            const localUrl = URL.createObjectURL(blob);
            window.open(localUrl, '_blank');
            updateCropInstructions('🔽 Otworzono poprawioną wersję w nowej karcie — użyj Zapisz jako (Ctrl+S) aby zapisać.');
            // NOTE: revoke po jakimś czasie aby użytkownik miał czas zapisać
            setTimeout(() => URL.revokeObjectURL(localUrl), 60 * 1000);
        } catch (err) {
            console.error('downloadAndSuggest error:', err);
            updateCropInstructions('❌ Nie udało się uruchomić zapisu pliku');
        }
    }

    function setSourceImageFromContext(context) {
        const nextImage = context?.image || null;
        const nextSignature = buildSourceSignature(context);

        // Jeśli mamy aktywną ręczną nadpisującą zmianę (manual override), i kontekst się NIE zmienił,
        // to nie nadpisujemy źródła — traktujmy to jak "to samo" aż do zmiany kontekstu.
        if (manualOverrideUntilContextChange) {
            // Preferujemy porównanie znormalizowanego URL-a obrazu, aby tolerować zmianę rozdzielczości/DPI
            const nextUrl = normalizeUrl(context?.lastImageUrl || context?.image?.src || '');
            if (nextUrl && manualOverrideSourceUrl && nextUrl === manualOverrideSourceUrl) {
                console.debug('[cropTools] manual override aktywny — nie nadpisuję obrazu (url match)');
                drawCropImage();
                drawSelectionOverlay();
                generateCropPreview();
                updateCropZoomUI();
                return;
            }
            // Jeśli URL się zmienił, wyczyść override
            console.debug('[cropTools] manual override wyczyszczony — kontekst obrazu się zmienił (url mismatch)');
            manualOverrideUntilContextChange = false;
            manualOverrideSignature = null;
            manualOverrideSourceUrl = null;
        }

        const hasPreviousSignature = Boolean(lastSourceSignature && nextSignature);
        const isSameImage = Boolean(
            hasPreviousSignature
            && lastSourceSignature === nextSignature
            && sourceImage
        );

        // Jeśli podpis obrazu się nie zmienił, zostaw aktualny obraz (np. po ręcznym obrocie)
        if (isSameImage) {
            drawCropImage();
            drawSelectionOverlay();
            generateCropPreview();
            updateCropZoomUI();
            return;
        }

        sourceImage = nextImage;
        sourceImageIsLocal = false;

        if (!sourceImage) {
            lastSourceSignature = null;
            sourceImageIsLocal = false;
            // czyszczenie manual override jeśli obraz zniknął
            manualOverrideUntilContextChange = false;
            manualOverrideSignature = null;
            disableCropControls();
            clearSelectionState();
            drawCropImage();
            return;
        }

        // Zaktualizuj podpis i odśwież płótno
        lastSourceSignature = nextSignature;
        // Jeżeli kontekst przybył z innego źródła, upewnij się że nie trzymamy flagi override
        manualOverrideUntilContextChange = false;
        manualOverrideSignature = null;
        updateCropCanvas();
    }

    return {
        setSourceImage: setSourceImageFromContext,
        clearSelection() {
            clearSelectionState();
            drawCropImage();
        },
        onTabVisible() {
            if (sourceImage) {
                drawCropImage();
                drawSelectionOverlay();
                generateCropPreview();
                updateCropZoomUI();
            }
            updateCropCanvas({ preserveViewport: true });
        },
    };
}
