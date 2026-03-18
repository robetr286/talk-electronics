/**
 * Moduł: Narzędzia retuszu canvas
 * Pozwala na manualną edycję obrazów binarnych (pędzel biały/czarny, gumka, undo/redo)
 */

export function initCanvasRetouch(dom = {}, dependencies = {}) {
    const {
        modeToggleBtn,
        modeLabel,
        whiteBrushBtn,
        blackBrushBtn,
        grayBrushBtn,
        eraserBtn,
        brushSizeSlider,
        brushSizeValue,
        grayControls,
        graySlider,
        grayValue,
        grayPreview,
        undoBtn,
        redoBtn,
        binarizeBtn,
        invertBtn,
        loadFromCropBtn,
        loadFromRetouchBtn,
        loadFileBtn,
        loadFileInput,
        resetBtn,
        downloadBtn,
        clearBtn,
        statusLabel,
        sourceImage,
        sourcePlaceholder,
        editorCanvas,
        editorPlaceholder,
        sourceZoomInBtn,
        sourceZoomOutBtn,
        sourceZoomResetBtn,
        sourceZoomLabel,
        editorZoomInBtn,
        editorZoomOutBtn,
        editorZoomResetBtn,
        editorZoomLabel,
    } = dom;

    const {
        getRetouchBuffer = () => null,
        getCropBuffer = () => null,
    } = dependencies;

    const state = {
        editMode: 'binary', // 'binary' | 'grayscale'
        activeTool: 'white-brush', // 'white-brush' | 'black-brush' | 'gray-brush' | 'eraser'
        brushSize: 10,
        grayBrushColor: 128, // 0-255 dla gray-brush
        eraserColor: null, // Smart eraser - przechowuje pobrany kolor
        isDrawing: false,
        originalImage: null,
        undoStack: [],
        redoStack: [],
        maxUndoSteps: 20,
        sourceZoom: 1.0,
        editorZoom: 1.0,
        editorPan: { x: 0, y: 0 },
        isPanning: false,
        lastPanPoint: null,
    };

    function setStatus(message) {
        if (statusLabel) {
            statusLabel.textContent = message;
        }
    }

    function toggleVisibility(element, placeholder, shouldShow) {
        if (!element || !placeholder) return;
        if (shouldShow) {
            element.classList.remove('hidden');
            placeholder.classList.add('hidden');
        } else {
            element.classList.add('hidden');
            placeholder.classList.remove('hidden');
        }
    }

    function setActiveTool(tool) {
        state.activeTool = tool;

        // Reset smart eraser color when switching tools
        if (tool !== 'eraser') {
            state.eraserColor = null;
        }

        // Aktualizuj przyciski
        [whiteBrushBtn, blackBrushBtn, grayBrushBtn, eraserBtn].forEach(btn => {
            if (btn) btn.classList.remove('active');
        });

        if (tool === 'white-brush' && whiteBrushBtn) {
            whiteBrushBtn.classList.add('active');
        } else if (tool === 'black-brush' && blackBrushBtn) {
            blackBrushBtn.classList.add('active');
        } else if (tool === 'gray-brush' && grayBrushBtn) {
            grayBrushBtn.classList.add('active');
        } else if (tool === 'eraser' && eraserBtn) {
            eraserBtn.classList.add('active');
        }

        // Pokaż/ukryj kontrolki szarego pędzla
        if (grayControls) {
            grayControls.style.display = tool === 'gray-brush' ? 'flex' : 'none';
        }

        const toolNames = {
            'white-brush': 'Pędzel biały',
            'black-brush': 'Pędzel czarny',
            'gray-brush': 'Pędzel szary',
            'eraser': 'Smart Gumka'
        };
        setStatus(`Narzędzie: ${toolNames[tool] || tool}`);
    }

    function toggleEditMode() {
        state.editMode = state.editMode === 'binary' ? 'grayscale' : 'binary';

        // Aktualizuj etykietę
        if (modeLabel) {
            modeLabel.textContent = state.editMode === 'binary' ? 'Binarny' : 'Skala szarości';
        }

        // Pokaż/ukryj narzędzia zależnie od trybu
        if (state.editMode === 'binary') {
            // Tryb binarny - ukryj gray brush
            if (grayBrushBtn) grayBrushBtn.style.display = 'none';
            if (grayControls) grayControls.style.display = 'none';
            // Przełącz na white-brush jeśli był gray-brush
            if (state.activeTool === 'gray-brush') {
                setActiveTool('white-brush');
            }
        } else {
            // Tryb grayscale - pokaż gray brush
            if (grayBrushBtn) grayBrushBtn.style.display = 'inline-block';
        }

        setStatus(`Tryb edycji: ${state.editMode === 'binary' ? 'Binarny (tylko czarny/biały)' : 'Skala szarości (0-255)'}`);
    }

    function updateGrayBrushColor(value) {
        state.grayBrushColor = Math.max(0, Math.min(255, parseInt(value) || 128));

        // Aktualizuj UI
        if (grayValue) {
            grayValue.textContent = state.grayBrushColor;
        }
        if (grayPreview) {
            const hex = state.grayBrushColor.toString(16).padStart(2, '0');
            grayPreview.style.background = `#${hex}${hex}${hex}`;
        }
    }

    function saveToUndoStack() {
        if (!editorCanvas) return;
        const ctx = editorCanvas.getContext('2d', { willReadFrequently: true });
        const imageData = ctx.getImageData(0, 0, editorCanvas.width, editorCanvas.height);

        state.undoStack.push(imageData);
        if (state.undoStack.length > state.maxUndoSteps) {
            state.undoStack.shift();
        }
        state.redoStack = []; // Wyczyść redo po nowej akcji

        updateUndoRedoButtons();
    }

    function undo() {
        if (state.undoStack.length === 0) return;

        const ctx = editorCanvas.getContext('2d', { willReadFrequently: true });
        const currentState = ctx.getImageData(0, 0, editorCanvas.width, editorCanvas.height);
        state.redoStack.push(currentState);

        const previousState = state.undoStack.pop();
        ctx.putImageData(previousState, 0, 0);

        updateUndoRedoButtons();
        setStatus('Cofnięto ostatnią zmianę.');
    }

    function redo() {
        if (state.redoStack.length === 0) return;

        const ctx = editorCanvas.getContext('2d', { willReadFrequently: true });
        const currentState = ctx.getImageData(0, 0, editorCanvas.width, editorCanvas.height);
        state.undoStack.push(currentState);

        const nextState = state.redoStack.pop();
        ctx.putImageData(nextState, 0, 0);

        updateUndoRedoButtons();
        setStatus('Ponowiono cofniętą zmianę.');
    }

    function updateUndoRedoButtons() {
        if (undoBtn) {
            undoBtn.disabled = state.undoStack.length === 0;
        }
        if (redoBtn) {
            redoBtn.disabled = state.redoStack.length === 0;
        }
    }

    function drawOnCanvas(x, y) {
        if (!editorCanvas) return;
        const ctx = editorCanvas.getContext('2d', { willReadFrequently: true });
        const brushSize = state.brushSize;

        ctx.beginPath();
        ctx.arc(x, y, brushSize / 2, 0, Math.PI * 2);

        if (state.activeTool === 'white-brush') {
            ctx.fillStyle = '#FFFFFF';
            ctx.fill();
        } else if (state.activeTool === 'black-brush') {
            ctx.fillStyle = '#000000';
            ctx.fill();
        } else if (state.activeTool === 'gray-brush') {
            // Pędzel szary - używa wartości z suwaka (0-255)
            const gray = Math.max(0, Math.min(255, Math.round(state.grayBrushColor)));
            const hex = gray.toString(16).padStart(2, '0');
            ctx.fillStyle = `#${hex}${hex}${hex}`;
            ctx.fill();
        } else if (state.activeTool === 'eraser') {
            // Smart Gumka
            if (state.eraserColor === null) {
                // Przy pierwszym użyciu - pobierz kolor z miejsca kliknięcia
                const imageData = ctx.getImageData(Math.floor(x), Math.floor(y), 1, 1);
                const [r, g, b] = imageData.data;
                state.eraserColor = { r, g, b };
                setStatus(`🧹 Gumka: pobrany kolor RGB(${r}, ${g}, ${b})`);
            }
            // Maluj pobranym kolorem
            const { r, g, b } = state.eraserColor;
            ctx.fillStyle = `rgb(${r}, ${g}, ${b})`;
            ctx.fill();
        }
    }

    function getCanvasCoordinates(event) {
        if (!editorCanvas) return null;
        const rect = editorCanvas.getBoundingClientRect();

        // Uwzględnij zoom w obliczeniach
        const scaleX = editorCanvas.width / (rect.width / state.editorZoom);
        const scaleY = editorCanvas.height / (rect.height / state.editorZoom);

        return {
            x: (event.clientX - rect.left) * scaleX / state.editorZoom,
            y: (event.clientY - rect.top) * scaleY / state.editorZoom,
        };
    }

    function handleMouseDown(event) {
        const coords = getCanvasCoordinates(event);
        if (!coords) return;

        state.isDrawing = true;
        saveToUndoStack(); // Zapisz stan przed rozpoczęciem rysowania
        drawOnCanvas(coords.x, coords.y);
    }

    function handleMouseMove(event) {
        if (!state.isDrawing) return;
        const coords = getCanvasCoordinates(event);
        if (!coords) return;
        drawOnCanvas(coords.x, coords.y);
    }

    function handleMouseUp() {
        state.isDrawing = false;
    }

    function loadImageToCanvas(imgElement, options = {}) {
        if (!editorCanvas || !imgElement) return;

        const { autoInvert = true } = options;

        const ctx = editorCanvas.getContext('2d', { willReadFrequently: true });

        // DOPASOWANIE: Skaluj obraz do maksymalnej szerokości kontenera
        const containerMaxWidth = 800;
        const containerMaxHeight = 600;
        const naturalWidth = imgElement.naturalWidth;
        const naturalHeight = imgElement.naturalHeight;

        // Oblicz współczynnik skalowania aby zmieścić w kontenerze
        const scaleX = containerMaxWidth / naturalWidth;
        const scaleY = containerMaxHeight / naturalHeight;
        const scale = Math.min(scaleX, scaleY, 1.0); // Nie powiększaj ponad 100%

        // Ustaw rozmiar canvas na przeskalowany obraz
        const canvasWidth = Math.round(naturalWidth * scale);
        const canvasHeight = Math.round(naturalHeight * scale);
        editorCanvas.width = canvasWidth;
        editorCanvas.height = canvasHeight;

        // Rysuj obraz w przeskalowanym rozmiarze
        ctx.drawImage(imgElement, 0, 0, canvasWidth, canvasHeight);

        // INWERSJA KOLORÓW: czarne tło + białe linie (jeśli autoInvert = true)
        if (autoInvert) {
            const imageData = ctx.getImageData(0, 0, editorCanvas.width, editorCanvas.height);
            const data = imageData.data;
            for (let i = 0; i < data.length; i += 4) {
                data[i] = 255 - data[i];       // R
                data[i + 1] = 255 - data[i + 1]; // G
                data[i + 2] = 255 - data[i + 2]; // B
                // Alpha (data[i + 3]) pozostaje bez zmian
            }
            ctx.putImageData(imageData, 0, 0);
        }

        // Zapisz oryginalny stan
        state.originalImage = ctx.getImageData(0, 0, editorCanvas.width, editorCanvas.height);
        state.undoStack = [];
        state.redoStack = [];

        // RESET SMART GUMKI - wymuś pobranie nowego koloru tła
        state.eraserColor = null;

        // Resetuj zoom do 100% - canvas jest już odpowiednio przeskalowany
        updateEditorZoom(1.0);

        updateUndoRedoButtons();

        toggleVisibility(editorCanvas, editorPlaceholder, true);
        if (resetBtn) resetBtn.disabled = false;
        if (downloadBtn) downloadBtn.disabled = false;
        if (binarizeBtn) binarizeBtn.disabled = false;

        const statusMsg = autoInvert
            ? 'Obraz załadowany (czarne tło, białe linie). Wybierz narzędzie i zacznij edycję.'
            : 'Obraz załadowany bez inwersji. Użyj "Binaryzuj" aby przekonwertować do czarno-białego, lub "Odwróć kolory" dla czarnego tła.';
        setStatus(statusMsg);
    }

    async function loadFromCropBuffer() {
        const crop = getCropBuffer();
        if (!crop) {
            alert('Brak zapisanego wycinka. Najpierw przejdź do zakładki "Kadrowanie" i zapisz fragment.');
            return;
        }

        try {
            setStatus('Ładowanie oryginalnego wycinka z kadrowania...');

            // crop może mieć objectUrl (lokalny blob) lub url (zdalny)
            let imageUrl = crop.objectUrl || crop.url;

            if (!imageUrl) {
                throw new Error('Brak URL obrazu w buforze kadrowania');
            }

            // Jeśli to już jest blob URL, użyj go bezpośrednio
            if (imageUrl.startsWith('blob:')) {
                const img = new Image();
                img.onload = () => {
                    if (sourceImage) {
                        // Ustaw onload PRZED ustawieniem src
                        sourceImage.onload = () => {
                            autoFitSourceImage();
                            sourceImage.onload = null; // Wyczyść po jednorazowym użyciu
                        };
                        sourceImage.src = img.src;
                        toggleVisibility(sourceImage, sourcePlaceholder, true);
                    }
                    loadImageToCanvas(img, { autoInvert: false }); // BEZ autowersji
                    setStatus('Załadowano oryginalny wycinek (bez obróbki). Użyj "Odwróć kolory" jeśli potrzebujesz czarne tło.');
                };
                img.onerror = () => {
                    setStatus('Nie udało się załadować wycinka.');
                };
                img.src = imageUrl;
            } else {
                // Pobierz z serwera
                const response = await fetch(imageUrl);
                if (!response.ok) throw new Error('Nie można pobrać obrazu');

                const blob = await response.blob();
                const img = new Image();
                img.onload = () => {
                    if (sourceImage) {
                        // Ustaw onload PRZED ustawieniem src
                        sourceImage.onload = () => {
                            autoFitSourceImage();
                            sourceImage.onload = null; // Wyczyść po jednorazowym użyciu
                        };
                        sourceImage.src = img.src;
                        toggleVisibility(sourceImage, sourcePlaceholder, true);
                    }
                    loadImageToCanvas(img, { autoInvert: false }); // BEZ autowersji
                    setStatus('Załadowano oryginalny wycinek (bez obróbki). Użyj "Odwróć kolory" jeśli potrzebujesz czarne tło.');
                };
                img.onerror = () => {
                    setStatus('Nie udało się załadować wycinka.');
                };
                img.src = URL.createObjectURL(blob);
            }
        } catch (error) {
            console.error('Błąd ładowania z kadrowania:', error);
            setStatus('Nie udało się załadować wycinka z kadrowania.');
            alert('Nie udało się załadować obrazu. Sprawdź konsolę deweloperską.');
        }
    }

    async function loadFromRetouchBuffer() {
        const buffer = getRetouchBuffer();
        if (!buffer) {
            alert('Brak materiału w buforze retuszu. Najpierw zastosuj automatyczne czyszczenie w zakładce "Automatyczny retusz".');
            return;
        }

        try {
            setStatus('Ładowanie z bufora retuszu...');

            // buffer może mieć objectUrl (lokalny blob) lub serverUrl/url (zdalny)
            let imageUrl = buffer.objectUrl || buffer.serverUrl || buffer.resultUrl || buffer.url;

            if (!imageUrl) {
                throw new Error('Brak URL obrazu w buforze');
            }

            // Jeśli to już jest blob URL, użyj go bezpośrednio
            if (imageUrl.startsWith('blob:')) {
                const img = new Image();
                img.onload = () => {
                    if (sourceImage) {
                        // Ustaw onload PRZED ustawieniem src
                        sourceImage.onload = () => {
                            autoFitSourceImage();
                            sourceImage.onload = null; // Wyczyść po jednorazowym użyciu
                        };
                        sourceImage.src = img.src;
                        toggleVisibility(sourceImage, sourcePlaceholder, true);
                    }
                    loadImageToCanvas(img);
                    setStatus('Załadowano obraz z bufora retuszu.');
                };
                img.onerror = () => {
                    setStatus('Nie udało się załadować obrazu z bufora retuszu.');
                };
                img.src = imageUrl;
            } else {
                // Pobierz z serwera
                const response = await fetch(imageUrl);
                if (!response.ok) throw new Error('Nie można pobrać obrazu');

                const blob = await response.blob();
                const img = new Image();
                img.onload = () => {
                    if (sourceImage) {
                        // Ustaw onload PRZED ustawieniem src
                        sourceImage.onload = () => {
                            autoFitSourceImage();
                            sourceImage.onload = null; // Wyczyść po jednorazowym użyciu
                        };
                        sourceImage.src = img.src;
                        toggleVisibility(sourceImage, sourcePlaceholder, true);
                    }
                    loadImageToCanvas(img);
                    setStatus('Załadowano obraz z bufora retuszu.');
                };
                img.onerror = () => {
                    setStatus('Nie udało się załadować obrazu z bufora retuszu.');
                };
                img.src = URL.createObjectURL(blob);
            }
        } catch (error) {
            console.error('Błąd ładowania z bufora:', error);
            setStatus('Nie udało się załadować obrazu z bufora retuszu.');
            alert('Nie udało się załadować obrazu. Sprawdź konsolę deweloperską.');
        }
    }

    function handleFileUpload(file) {
        if (!file) return;

        const img = new Image();
        img.onload = () => {
            if (sourceImage) {
                // Ustaw onload PRZED ustawieniem src
                sourceImage.onload = () => {
                    autoFitSourceImage();
                    sourceImage.onload = null; // Wyczyść po jednorazowym użyciu
                };
                sourceImage.src = img.src;
                toggleVisibility(sourceImage, sourcePlaceholder, true);
            }
            loadImageToCanvas(img);
        };
        img.src = URL.createObjectURL(file);
        setStatus(`Wczytano plik: ${file.name}`);
    }

    function resetToOriginal() {
        if (!state.originalImage || !editorCanvas) return;

        const ctx = editorCanvas.getContext('2d', { willReadFrequently: true });
        ctx.putImageData(state.originalImage, 0, 0);

        state.undoStack = [];
        state.redoStack = [];
        updateUndoRedoButtons();
        setStatus('Przywrócono oryginalny obraz.');
    }

    function invertColors() {
        if (!editorCanvas) return;

        saveToUndoStack();
        const ctx = editorCanvas.getContext('2d', { willReadFrequently: true });
        const imageData = ctx.getImageData(0, 0, editorCanvas.width, editorCanvas.height);
        const data = imageData.data;

        for (let i = 0; i < data.length; i += 4) {
            data[i] = 255 - data[i];       // R
            data[i + 1] = 255 - data[i + 1]; // G
            data[i + 2] = 255 - data[i + 2]; // B
        }

        ctx.putImageData(imageData, 0, 0);
        setStatus('Odwrócono kolory obrazu.');
    }

    function binarizeImage() {
        if (!editorCanvas) return;

        saveToUndoStack();
        const ctx = editorCanvas.getContext('2d', { willReadFrequently: true });
        const imageData = ctx.getImageData(0, 0, editorCanvas.width, editorCanvas.height);
        const data = imageData.data;

        // Konwersja do grayscale i obliczanie histogramu
        const histogram = new Array(256).fill(0);
        const grayValues = new Uint8Array(data.length / 4);

        for (let i = 0, j = 0; i < data.length; i += 4, j++) {
            // Konwersja RGB do grayscale (luminance)
            const gray = Math.round(0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2]);
            grayValues[j] = gray;
            histogram[gray]++;
        }

        // Algorytm Otsu - znajdź optymalny próg
        const total = grayValues.length;
        let sum = 0;
        for (let i = 0; i < 256; i++) {
            sum += i * histogram[i];
        }

        let sumB = 0;
        let wB = 0;
        let wF = 0;
        let maxVariance = 0;
        let threshold = 0;

        for (let t = 0; t < 256; t++) {
            wB += histogram[t];
            if (wB === 0) continue;

            wF = total - wB;
            if (wF === 0) break;

            sumB += t * histogram[t];
            const mB = sumB / wB;
            const mF = (sum - sumB) / wF;

            const variance = wB * wF * (mB - mF) * (mB - mF);

            if (variance > maxVariance) {
                maxVariance = variance;
                threshold = t;
            }
        }

        // Zastosuj próg - konwersja do czarno-białego
        for (let i = 0, j = 0; i < data.length; i += 4, j++) {
            const binaryValue = grayValues[j] > threshold ? 255 : 0;
            data[i] = binaryValue;       // R
            data[i + 1] = binaryValue;   // G
            data[i + 2] = binaryValue;   // B
            // Alpha pozostaje bez zmian
        }

        ctx.putImageData(imageData, 0, 0);
        setStatus(`Obraz zbinaryzowany (próg Otsu: ${threshold}). Użyj "Odwróć kolory" jeśli potrzebujesz czarnego tła.`);
    }

    function downloadResult() {
        if (!editorCanvas) return;

        editorCanvas.toBlob((blob) => {
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `canvas-retouch-${Date.now()}.png`;
            a.click();
            URL.revokeObjectURL(url);
            setStatus('Pobrano wynik edycji.');
        });
    }

    function clearCanvas() {
        if (sourceImage) sourceImage.src = '';
        toggleVisibility(sourceImage, sourcePlaceholder, false);

        if (editorCanvas) {
            const ctx = editorCanvas.getContext('2d', { willReadFrequently: true });
            ctx.clearRect(0, 0, editorCanvas.width, editorCanvas.height);
        }
        toggleVisibility(editorCanvas, editorPlaceholder, false);

        state.originalImage = null;
        state.undoStack = [];
        state.redoStack = [];
        updateUndoRedoButtons();

        if (resetBtn) resetBtn.disabled = true;
        if (downloadBtn) downloadBtn.disabled = true;
        if (binarizeBtn) binarizeBtn.disabled = true;

        setStatus('Wyczyszczono canvas. Wczytaj nowy obraz.');
    }

    // Funkcje zoom dla obrazu źródłowego
    function autoFitSourceImage() {
        // SourceImage używa CSS max-width: 100%, resetujemy do naturalnego rozmiaru
        sourceZoomReset();
        if (sourceImage && !sourceImage.classList.contains('hidden')) {
            updateSourceZoom(1.0);
        }
    }

    function updateSourceZoom(newZoom) {
        state.sourceZoom = Math.max(0.1, Math.min(5.0, newZoom));

        if (sourceImage && !sourceImage.classList.contains('hidden')) {
            sourceImage.style.transform = `scale(${state.sourceZoom})`;
            sourceImage.style.transformOrigin = 'center center';
            if (sourcePlaceholder) {
                sourcePlaceholder.classList.add('hidden');
            }
        }

        if (sourceZoomLabel) {
            sourceZoomLabel.textContent = `${Math.round(state.sourceZoom * 100)}%`;
        }
    }

    function sourceZoomIn() {
        updateSourceZoom(state.sourceZoom + 0.1);
    }

    function sourceZoomOut() {
        updateSourceZoom(state.sourceZoom - 0.1);
    }

    function sourceZoomReset() {
        if (sourceImage) {
            sourceImage.style.width = '';
            sourceImage.style.height = '';
            sourceImage.style.maxWidth = '100%';
            sourceImage.style.maxHeight = '600px';
            sourceImage.style.transform = 'scale(1)';
            sourceImage.style.transformOrigin = 'center center';
        }
        if (sourcePlaceholder && sourceImage && sourceImage.src) {
            sourcePlaceholder.classList.add('hidden');
        }

    const stage = document.getElementById('canvasSourceStage');
        if (stage) {
            stage.style.justifyContent = '';
            stage.style.alignItems = '';
            stage.scrollTop = 0;
            stage.scrollLeft = 0;
        }

        state.sourceZoom = 1.0;
        if (sourceZoomLabel) {
            sourceZoomLabel.textContent = '100%';
        }
    }

    // Funkcje zoom dla canvas edytora
    function updateEditorZoom(newZoom) {
        state.editorZoom = Math.max(0.1, Math.min(5.0, newZoom));
        if (editorCanvas) {
            editorCanvas.style.transform = `scale(${state.editorZoom})`;
            editorCanvas.style.transformOrigin = 'top left';
        }
        if (editorZoomLabel) {
            editorZoomLabel.textContent = `${Math.round(state.editorZoom * 100)}%`;
        }
    }

    function editorZoomIn() {
        updateEditorZoom(state.editorZoom + 0.1);
    }

    function editorZoomOut() {
        updateEditorZoom(state.editorZoom - 0.1);
    }

    function editorZoomReset() {
        updateEditorZoom(1.0);
    }

    // Event listeners
    if (modeToggleBtn) {
        modeToggleBtn.addEventListener('click', toggleEditMode);
    }

    if (whiteBrushBtn) {
        whiteBrushBtn.addEventListener('click', () => setActiveTool('white-brush'));
    }
    if (blackBrushBtn) {
        blackBrushBtn.addEventListener('click', () => setActiveTool('black-brush'));
    }
    if (grayBrushBtn) {
        grayBrushBtn.addEventListener('click', () => setActiveTool('gray-brush'));
    }
    if (eraserBtn) {
        eraserBtn.addEventListener('click', () => {
            state.eraserColor = null; // Reset smart eraser
            setActiveTool('eraser');
        });
    }

    if (brushSizeSlider && brushSizeValue) {
        brushSizeSlider.addEventListener('input', (e) => {
            state.brushSize = parseInt(e.target.value);
            brushSizeValue.textContent = `${state.brushSize} px`;
        });
    }

    if (graySlider) {
        graySlider.addEventListener('input', (e) => {
            updateGrayBrushColor(e.target.value);
        });
        // Initialize preview
        updateGrayBrushColor(state.grayBrushColor);
    }

    if (undoBtn) {
        undoBtn.addEventListener('click', undo);
    }
    if (redoBtn) {
        redoBtn.addEventListener('click', redo);
    }
    if (binarizeBtn) {
        binarizeBtn.addEventListener('click', binarizeImage);
    }
    if (invertBtn) {
        invertBtn.addEventListener('click', invertColors);
    }

    if (loadFromCropBtn) {
        loadFromCropBtn.addEventListener('click', loadFromCropBuffer);
    }
    if (loadFromRetouchBtn) {
        loadFromRetouchBtn.addEventListener('click', loadFromRetouchBuffer);
    }
    if (loadFileBtn && loadFileInput) {
        loadFileBtn.addEventListener('click', () => loadFileInput.click());
        loadFileInput.addEventListener('change', (e) => {
            const file = e.target.files?.[0];
            if (file) handleFileUpload(file);
            loadFileInput.value = '';
        });
    }

    if (resetBtn) {
        resetBtn.addEventListener('click', resetToOriginal);
    }
    if (downloadBtn) {
        downloadBtn.addEventListener('click', downloadResult);
    }
    if (clearBtn) {
        clearBtn.addEventListener('click', clearCanvas);
    }

    // Canvas mouse events - tylko rysowanie
    if (editorCanvas) {
        editorCanvas.addEventListener('mousedown', handleMouseDown);
        editorCanvas.addEventListener('mousemove', handleMouseMove);
        editorCanvas.addEventListener('mouseup', handleMouseUp);
        editorCanvas.addEventListener('mouseleave', handleMouseUp);

        // Wheel zoom dla canvas (bez pan - użyj scrollbarów)
        editorCanvas.addEventListener('wheel', (event) => {
            event.preventDefault();
            const delta = event.deltaY < 0 ? 0.1 : -0.1;
            updateEditorZoom(state.editorZoom + delta);
        }, { passive: false });
    }

    // Zoom controls dla obrazu źródłowego
    if (sourceZoomInBtn) {
        sourceZoomInBtn.addEventListener('click', sourceZoomIn);
    }
    if (sourceZoomOutBtn) {
        sourceZoomOutBtn.addEventListener('click', sourceZoomOut);
    }
    if (sourceZoomResetBtn) {
        sourceZoomResetBtn.addEventListener('click', sourceZoomReset);
    }

    // Zoom controls dla canvas edytora
    if (editorZoomInBtn) {
        editorZoomInBtn.addEventListener('click', editorZoomIn);
    }
    if (editorZoomOutBtn) {
        editorZoomOutBtn.addEventListener('click', editorZoomOut);
    }
    if (editorZoomResetBtn) {
        editorZoomResetBtn.addEventListener('click', editorZoomReset);
    }

    // Inicjalizacja
    setActiveTool('white-brush');
    setStatus('Wczytaj obraz do edycji canvas.');
    updateUndoRedoButtons();
    updateSourceZoom(1.0);
    updateEditorZoom(1.0);

    function getCanvasImage() {
        if (!editorCanvas || !editorCanvas.width || !editorCanvas.height) {
            return null;
        }
        try {
            const blobPromise = new Promise((resolve) => {
                editorCanvas.toBlob((blob) => {
                    if (blob) {
                        const objectUrl = URL.createObjectURL(blob);
                        resolve({
                            url: objectUrl,
                            objectUrl,
                            blob,
                            filename: 'canvas-retouch.png',
                            label: 'Obraz z narzędzi retuszu',
                            type: 'canvas-retouch',
                            width: editorCanvas.width,
                            height: editorCanvas.height,
                        });
                    } else {
                        resolve(null);
                    }
                }, 'image/png');
            });
            return blobPromise;
        } catch (error) {
            console.error('Błąd podczas eksportu obrazu z kanwy:', error);
            return null;
        }
    }

    return {
        onTabVisible() {
            // Można automatycznie załadować z bufora retuszu
        },
        onTabHidden() {
            state.isDrawing = false;
        },
        getCanvasImage,
    };
}
