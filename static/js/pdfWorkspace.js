import { MAX_CANVAS_HEIGHT, MAX_ZOOM, MIN_ZOOM, ZOOM_STEP } from './constants.js';

const DEFAULT_PREVIEW_DPI = 300;
const MIN_RENDER_DPI = 72;
const FALLBACK_MAX_RENDER_DPI = 1200;

export function initPdfWorkspace(dom, callbacks = {}) {
    const {
        fileInput,
        uploadBtn,
        imageCanvas,
        canvasWrapper,
        prevPageBtn,
        nextPageBtn,
        currentPageLabel,
        totalPagesLabel,
        pageInput,
        zoomInBtn,
        zoomOutBtn,
        zoomLabel,
        filenamePill,
        exportDpiInput,
        exportMaxDpiValue,
        exportMinDpiValue,
        exportDpiInfo,
        exportDpiPreview,
        exportDpiPreviewValue,
        exportDpiPreviewDimensions,
        dpiPresetRadios,
        downloadPageBtn,
        exportInfoLabel,
        exportStatusLabel,
        uploadActionsSection,
        uploadFromUploadsBtn,
        uploadsModal,
        uploadsList,
        uploadsCloseBtn,
        uploadSaveOnLoadCheckbox,
    } = dom;

    const {
        onImageRendered = () => {},
        onDocumentCleared = () => {},
    } = callbacks;

    const ctx = imageCanvas.getContext('2d');
    const uploadListeners = new Set();

    const state = {
        token: null,
        filename: null,
        lastImageUrl: null,
        currentPage: 1,
        totalPages: 1,
        currentImage: null,
        baseScale: 1,
        zoomLevel: 1,
        panX: 0,
        panY: 0,
        isPanning: false,
        activePointerId: null,
        lastPanPoint: { x: 0, y: 0 },
        imageDpi: null,
        pageWidthPx: null,
        pageHeightPx: null,
        pageWidthIn: null,
        pageHeightIn: null,
        maxRenderDpi: null,
        minRenderDpi: MIN_RENDER_DPI,
        desiredDpi: null,
        dpiPreset: 'auto',  // 'auto', '2x', '3x', 'max', 'custom'
        exportStatusMessage: '',
        isExporting: false,
    };

    function getMaxRenderDpi() {
        return state.maxRenderDpi || FALLBACK_MAX_RENDER_DPI;
    }

    // Simple status helper for upload/workspace messages
    let _uploadStatusTimer = null;
    function setStatus(message, autoHideMs = 4000) {
        try {
            if (!filenamePill) return;
            filenamePill.classList.remove('hidden');
            filenamePill.textContent = message;
            if (_uploadStatusTimer) {
                clearTimeout(_uploadStatusTimer);
                _uploadStatusTimer = null;
            }
            if (Number.isFinite(autoHideMs) && autoHideMs > 0) {
                _uploadStatusTimer = setTimeout(() => {
                    if (filenamePill) {
                        filenamePill.classList.add('hidden');
                        filenamePill.textContent = '';
                    }
                    _uploadStatusTimer = null;
                }, Math.max(0, autoHideMs));
            }
        } catch (err) {
            console.warn('setStatus error', err);
        }
    }

    function clampDpi(value) {
        const min = state.minRenderDpi || MIN_RENDER_DPI;
        const max = getMaxRenderDpi();
        if (!Number.isFinite(value)) {
            return min;
        }
        return Math.min(Math.max(value, min), max);
    }

    function calculateDpiFromPreset(preset) {
        const baseDpi = state.imageDpi ?? DEFAULT_PREVIEW_DPI;

        switch (preset) {
            case 'auto':
                return baseDpi;
            case '2x':
                return clampDpi(baseDpi * 2);
            case '3x':
                return clampDpi(baseDpi * 3);
            case 'max':
                return getMaxRenderDpi();
            case 'custom':
                return state.desiredDpi ?? baseDpi;
            default:
                return baseDpi;
        }
    }

    function estimateDimensions(dpi) {
        if (!state.pageWidthIn || !state.pageHeightIn || !dpi) {
            return { width: 0, height: 0 };
        }

        return {
            width: Math.round(state.pageWidthIn * dpi),
            height: Math.round(state.pageHeightIn * dpi)
        };
    }

    function updateDpiPreview() {
        if (!exportDpiPreview || !exportDpiPreviewValue || !exportDpiPreviewDimensions) {
            return;
        }

        const hasDocument = Boolean(state.token) && Boolean(state.currentImage);

        if (!hasDocument) {
            exportDpiPreview.style.display = 'none';
            return;
        }

        const dpi = calculateDpiFromPreset(state.dpiPreset);
        const dims = estimateDimensions(dpi);

        exportDpiPreviewValue.textContent = dpi;
        exportDpiPreviewDimensions.textContent = `${dims.width} × ${dims.height} px`;
        exportDpiPreview.style.display = 'block';
    }

    function setExportStatus(message = '', type = 'muted') {
        state.exportStatusMessage = message || '';
        if (!exportStatusLabel) {
            return;
        }

        let className = 'form-text text-muted';
        if (type === 'success') {
            className = 'form-text text-success';
        } else if (type === 'error') {
            className = 'form-text text-danger';
        }
        exportStatusLabel.className = className;
        exportStatusLabel.textContent = message || '';
    }

    function formatInches(value) {
        if (!Number.isFinite(value) || value <= 0) {
            return '--';
        }
        return value < 10 ? value.toFixed(2) : value.toFixed(1);
    }

    function updateExportUI() {
        const hasDocument = Boolean(state.token) && Boolean(state.currentImage);
        const maxDpi = getMaxRenderDpi();
        const minDpi = state.minRenderDpi || MIN_RENDER_DPI;

        // Aktualizuj zakres DPI
        if (exportMaxDpiValue) {
            exportMaxDpiValue.textContent = hasDocument ? maxDpi : '--';
        }
        if (exportMinDpiValue) {
            exportMinDpiValue.textContent = hasDocument ? minDpi : '--';
        }

        // Włącz/wyłącz presety
        if (dpiPresetRadios) {
            for (const radio of dpiPresetRadios) {
                radio.disabled = !hasDocument;
                radio.checked = hasDocument && radio.value === state.dpiPreset;
            }
        }

        // Pole własnego DPI
        if (exportDpiInput) {
            const isCustom = state.dpiPreset === 'custom';
            exportDpiInput.disabled = !hasDocument || !isCustom;

            if (!hasDocument) {
                exportDpiInput.value = '';
            } else if (isCustom) {
                const candidate = state.desiredDpi ?? state.imageDpi ?? DEFAULT_PREVIEW_DPI;
                exportDpiInput.value = candidate;
            } else {
                const dpi = calculateDpiFromPreset(state.dpiPreset);
                exportDpiInput.value = dpi;
            }
        }

        // Przycisk pobierania
        const disableExportButtons = !hasDocument || state.isExporting;
        if (downloadPageBtn) {
            downloadPageBtn.disabled = disableExportButtons;
        }

        // Info o aktualnym podglądzie
        if (exportInfoLabel) {
            if (!hasDocument) {
                exportInfoLabel.textContent = 'Brak załadowanego pliku';
            } else {
                const dpi = state.imageDpi ?? DEFAULT_PREVIEW_DPI;
                const widthPx = state.pageWidthPx ?? (state.currentImage ? state.currentImage.width : 0);
                const heightPx = state.pageHeightPx ?? (state.currentImage ? state.currentImage.height : 0);
                const widthIn = state.pageWidthIn ?? (dpi ? widthPx / dpi : 0);
                const heightIn = state.pageHeightIn ?? (dpi ? heightPx / dpi : 0);
                exportInfoLabel.textContent = `${widthPx}×${heightPx}px @ ${dpi} DPI (~${formatInches(widthIn)}″ × ${formatInches(heightIn)}″)`;
            }
        }

        // Podgląd docelowego DPI
        updateDpiPreview();

        if (exportStatusLabel && !state.exportStatusMessage) {
            exportStatusLabel.textContent = '';
            exportStatusLabel.className = 'form-text text-muted';
        }
    }

    function triggerDownload(filename, url) {
        if (!url) {
            return;
        }
        const link = document.createElement('a');
        link.href = url;
        if (filename) {
            link.download = filename;
        }
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }

    function updateFilenamePill(name) {
        if (!filenamePill) {
            return;
        }
        if (name) {
            filenamePill.textContent = name;
            filenamePill.classList.remove('hidden');
        } else {
            filenamePill.textContent = '';
            filenamePill.classList.add('hidden');
        }
    }

    function updateZoomUI() {
        if (!zoomLabel) {
            return;
        }

        const hasDocument = Boolean(state.token) && Boolean(state.currentImage);
        zoomLabel.textContent = hasDocument ? `${Math.round(state.zoomLevel * 100)}%` : '--%';

        if (zoomInBtn) {
            zoomInBtn.disabled = !hasDocument || state.zoomLevel >= MAX_ZOOM - 0.001;
        }
        if (zoomOutBtn) {
            zoomOutBtn.disabled = !hasDocument || state.zoomLevel <= MIN_ZOOM + 0.001;
        }
    }

    function updatePageUI() {
        const hasDocument = Boolean(state.token) && state.totalPages > 0;

        if (currentPageLabel) {
            currentPageLabel.textContent = hasDocument ? state.currentPage : '-';
        }
        if (totalPagesLabel) {
            totalPagesLabel.textContent = hasDocument ? state.totalPages : '-';
        }
        if (pageInput) {
            pageInput.disabled = !hasDocument;
            if (hasDocument) {
                pageInput.value = state.currentPage;
                pageInput.max = state.totalPages;
                pageInput.min = 1;
            } else {
                pageInput.value = '';
            }
        }
        if (prevPageBtn) {
            prevPageBtn.disabled = !hasDocument || state.currentPage <= 1;
        }
        if (nextPageBtn) {
            nextPageBtn.disabled = !hasDocument || state.currentPage >= state.totalPages;
        }

        updateZoomUI();
        updateExportUI();
    }

    function calculateBaseScale() {
        if (!state.currentImage) {
            return;
        }

        const wrapperWidth = canvasWrapper && canvasWrapper.clientWidth ? canvasWrapper.clientWidth : state.currentImage.width;
        const widthScale = wrapperWidth > 0 ? wrapperWidth / state.currentImage.width : 1;
        const heightScale = MAX_CANVAS_HEIGHT / state.currentImage.height;
        state.baseScale = Math.min(widthScale, heightScale, 1);

        if (!Number.isFinite(state.baseScale) || state.baseScale <= 0) {
            state.baseScale = 1;
        }
    }

    function applyCanvasSize() {
        if (!state.currentImage) {
            return;
        }

        const viewportWidth = Math.max(1, Math.floor(state.currentImage.width * state.baseScale));
        const viewportHeight = Math.max(1, Math.floor(state.currentImage.height * state.baseScale));
        imageCanvas.width = viewportWidth;
        imageCanvas.height = viewportHeight;
        imageCanvas.style.width = `${viewportWidth}px`;
        imageCanvas.style.height = `${viewportHeight}px`;
    }

    function clampPan() {
        if (!state.currentImage) {
            return;
        }

        const scale = state.baseScale * state.zoomLevel;
        const scaledWidth = state.currentImage.width * scale;
        const scaledHeight = state.currentImage.height * scale;

        if (scaledWidth <= imageCanvas.width) {
            state.panX = (imageCanvas.width - scaledWidth) / 2;
        } else {
            const minPanX = imageCanvas.width - scaledWidth;
            const maxPanX = 0;
            state.panX = Math.min(maxPanX, Math.max(minPanX, state.panX));
        }

        if (scaledHeight <= imageCanvas.height) {
            state.panY = (imageCanvas.height - scaledHeight) / 2;
        } else {
            const minPanY = imageCanvas.height - scaledHeight;
            const maxPanY = 0;
            state.panY = Math.min(maxPanY, Math.max(minPanY, state.panY));
        }
    }

    function drawCurrentImage() {
        if (!state.currentImage) {
            return;
        }

        const scale = state.baseScale * state.zoomLevel;
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.clearRect(0, 0, imageCanvas.width, imageCanvas.height);
        clampPan();
        ctx.setTransform(scale, 0, 0, scale, state.panX, state.panY);
        ctx.drawImage(state.currentImage, 0, 0);
        ctx.setTransform(1, 0, 0, 1, 0, 0);
    }

    function resetPan() {
        state.panX = 0;
        state.panY = 0;
        clampPan();
    }

    function changeZoom(delta, focusX = imageCanvas.width / 2, focusY = imageCanvas.height / 2) {
        if (!state.currentImage) {
            return;
        }

        const previousZoom = state.zoomLevel;
        let nextZoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, state.zoomLevel + delta));
        nextZoom = Math.round(nextZoom * 100) / 100;

        if (Math.abs(nextZoom - previousZoom) < 0.001) {
            return;
        }

        const previousScale = state.baseScale * state.zoomLevel;
        const newScale = state.baseScale * nextZoom;
        const imageX = (focusX - state.panX) / previousScale;
        const imageY = (focusY - state.panY) / previousScale;

        state.zoomLevel = nextZoom;
        state.panX = focusX - imageX * newScale;
        state.panY = focusY - imageY * newScale;

        drawCurrentImage();
        updateZoomUI();
    }

    function handlePointerDown(event) {
        if (!state.currentImage) {
            return;
        }

        state.isPanning = true;
        state.activePointerId = event.pointerId;
        state.lastPanPoint = { x: event.clientX, y: event.clientY };
        imageCanvas.setPointerCapture(event.pointerId);
        imageCanvas.classList.add('is-panning');
        event.preventDefault();
    }

    function handlePointerMove(event) {
        if (!state.isPanning || event.pointerId !== state.activePointerId) {
            return;
        }

        const deltaX = event.clientX - state.lastPanPoint.x;
        const deltaY = event.clientY - state.lastPanPoint.y;
        state.lastPanPoint = { x: event.clientX, y: event.clientY };
        state.panX += deltaX;
        state.panY += deltaY;
        drawCurrentImage();
        event.preventDefault();
    }

    function endPan(event) {
        if (event.pointerId !== state.activePointerId) {
            return;
        }

        state.isPanning = false;
        state.activePointerId = null;
        imageCanvas.classList.remove('is-panning');
        try {
            imageCanvas.releasePointerCapture(event.pointerId);
        } catch (error) {
            console.debug('Pointer capture already released', error);
        }
    }

    function emitUploadComplete() {
        uploadListeners.forEach((listener) => listener());
    }

    function handleResize() {
        if (!state.currentImage) {
            return;
        }

        const previousScale = state.baseScale * state.zoomLevel;
        const previousWidth = imageCanvas.width;
        const previousHeight = imageCanvas.height;
        const focusX = previousWidth / 2;
        const focusY = previousHeight / 2;

        calculateBaseScale();
        applyCanvasSize();

        const newScale = state.baseScale * state.zoomLevel;
        const imageX = (focusX - state.panX) / previousScale;
        const imageY = (focusY - state.panY) / previousScale;
        state.panX = imageCanvas.width / 2 - imageX * newScale;
        state.panY = imageCanvas.height / 2 - imageY * newScale;

        drawCurrentImage();
        updateZoomUI();
    }

    async function fetchPage(pageIndex) {
        if (!state.token) {
            return;
        }

        try {
            const response = await fetch(`/page/${state.token}/${pageIndex}`);
            if (!response.ok) {
                console.error('Nie udało się pobrać strony PDF.');
                return;
            }

            const data = await response.json();
            if (data.error) {
                alert(data.error);
                return;
            }

            if (typeof data.total_pages === 'number') {
                state.totalPages = data.total_pages;
            }
            state.currentPage = data.page ?? pageIndex;
            renderToCanvas(data);
            updatePageUI();
        } catch (error) {
            console.error('Błąd podczas pobierania strony PDF:', error);
        }
    }

    function renderToCanvas(imageData) {
        if (!imageData) {
            return;
        }

        const imageUrl = typeof imageData === 'string' ? imageData : imageData.image_url;
        if (!imageUrl) {
            return;
        }

        if (typeof imageData === 'object') {
            if (typeof imageData.image_dpi === 'number') {
                state.imageDpi = imageData.image_dpi;
            }
            if (typeof imageData.image_width_px === 'number') {
                state.pageWidthPx = imageData.image_width_px;
            }
            if (typeof imageData.image_height_px === 'number') {
                state.pageHeightPx = imageData.image_height_px;
            }
            if (typeof imageData.page_width_in === 'number') {
                state.pageWidthIn = imageData.page_width_in;
            }
            if (typeof imageData.page_height_in === 'number') {
                state.pageHeightIn = imageData.page_height_in;
            }
            if (typeof imageData.max_render_dpi === 'number') {
                state.maxRenderDpi = imageData.max_render_dpi;
            }
            if (typeof imageData.min_render_dpi === 'number') {
                state.minRenderDpi = imageData.min_render_dpi;
            }
            if (state.desiredDpi === null && typeof imageData.image_dpi === 'number') {
                state.desiredDpi = imageData.image_dpi;
            }
            state.exportStatusMessage = '';
            setExportStatus('');
            updateExportUI();
        }

        state.lastImageUrl = imageUrl;
        const img = new Image();
        img.onload = () => {
            state.currentImage = img;
            state.pageWidthPx = img.naturalWidth;
            state.pageHeightPx = img.naturalHeight;
            if (state.imageDpi) {
                state.pageWidthIn = state.pageWidthPx / state.imageDpi;
                state.pageHeightIn = state.pageHeightPx / state.imageDpi;
            }
            state.zoomLevel = 1;
            calculateBaseScale();
            applyCanvasSize();
            resetPan();
            drawCurrentImage();
            updateZoomUI();
            imageCanvas.classList.add('has-image');
            updateExportUI();
            onImageRendered(getDocumentContext());
        };

        const cacheBustedUrl = imageUrl.includes('?') ? `${imageUrl}&v=${Date.now()}` : `${imageUrl}?v=${Date.now()}`;
        img.src = cacheBustedUrl;
    }

    function clearUploadActions() {
        const existing = document.getElementById('uploadActionsContainer');
        if (existing) existing.remove();
    }

    function showUploadActions(payload) {
        clearUploadActions();
        if (!dom.uploadActionsSection) return;
        const container = document.createElement('div');
        container.id = 'uploadActionsContainer';
        container.className = 'd-flex gap-2 align-items-center ms-2';

        const downloadBtn = document.createElement('button');
        downloadBtn.type = 'button';
        downloadBtn.className = 'btn btn-sm btn-outline-primary';
        downloadBtn.textContent = '💾 Pobierz';
        downloadBtn.addEventListener('click', () => {
            const url = payload.image_url || payload.url;
            if (!url) {
                setStatus('Brak URL do pobrania');
                return;
            }
            const a = document.createElement('a');
            a.href = url;
            a.download = payload.filename || 'download.png';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            setStatus('Rozpoczęto pobieranie');
        });

        const copyBtn = document.createElement('button');
        copyBtn.type = 'button';
        copyBtn.className = 'btn btn-sm btn-outline-secondary';
        copyBtn.textContent = '📁 Pokaż ścieżkę';
        copyBtn.addEventListener('click', async () => {
            const path = payload.filename || payload.url || '';
            try {
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    await navigator.clipboard.writeText(path);
                    setStatus('Ścieżka skopiowana do schowka');
                } else {
                    setStatus(`Ścieżka: ${path}`);
                }
            } catch (err) {
                console.warn('Nie udało się skopiować ścieżki', err);
                setStatus(`Ścieżka: ${path}`);
            }
        });

        const closeBtn = document.createElement('button');
        closeBtn.type = 'button';
        closeBtn.className = 'btn btn-sm btn-outline-secondary';
        closeBtn.textContent = '✖';
        closeBtn.addEventListener('click', clearUploadActions);

        container.appendChild(downloadBtn);
        container.appendChild(copyBtn);
        container.appendChild(closeBtn);

        dom.uploadActionsSection.appendChild(container);

        setTimeout(clearUploadActions, 20000);
    }

    async function handleUpload() {
        const file = fileInput ? fileInput.files[0] : null;
        if (!file) {
            return;
        }

        state.desiredDpi = null;
        state.imageDpi = null;
        state.pageWidthPx = null;
        state.pageHeightPx = null;
        state.pageWidthIn = null;
        state.pageHeightIn = null;
        state.maxRenderDpi = null;
        state.minRenderDpi = MIN_RENDER_DPI;
        state.exportStatusMessage = '';
        state.isExporting = false;
        setExportStatus('');
        updateExportUI();

        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch('/upload', {
                method: 'POST',
                body: formData,
            });
            const data = await response.json();

            if (data.error) {
                alert(data.error);
                return;
            }

            state.token = data.token || null;
            state.totalPages = data.total_pages || 1;
            state.currentPage = data.page || 1;
            state.filename = data.filename || null;
            updateFilenamePill(state.filename);
            renderToCanvas(data);
            updatePageUI();
            emitUploadComplete();

            // Pokaż akcje przy wczytanym pliku: pobierz, pokaż ścieżkę
            showUploadActions(data);
        } catch (error) {
            console.error('Błąd podczas przesyłania pliku PDF:', error);
            alert('Nie udało się wczytać pliku. Spróbuj ponownie.');
        }
    }

    function changePage(delta) {
        const nextPage = state.currentPage + delta;
        if (nextPage < 1 || nextPage > state.totalPages) {
            return;
        }
        fetchPage(nextPage);
    }

    function showUploadsModal(files) {
        if (!uploadsModal || !uploadsList) return;
        uploadsList.innerHTML = '';
        if (!Array.isArray(files) || files.length === 0) {
            uploadsList.innerHTML = '<p class="text-muted">Brak plików w katalogu uploads.</p>';
        } else {
            const list = document.createElement('div');
            list.className = 'd-flex flex-column gap-2';
            files.forEach((f) => {
                const row = document.createElement('div');
                row.className = 'd-flex justify-content-between align-items-center p-2 border rounded';
                const left = document.createElement('div');
                left.className = 'd-flex flex-column';
                // Thumbnail (if available)
                if (f.thumb_url) {
                    const img = document.createElement('img');
                    img.src = f.thumb_url;
                    img.alt = f.name;
                    img.style.width = '96px';
                    img.style.height = 'auto';
                    img.style.objectFit = 'contain';
                    img.style.marginBottom = '6px';
                    left.appendChild(img);
                } else if (f.url && /\.(png|jpe?g|webp|bmp|tiff?)$/i.test(f.name)) {
                    const img = document.createElement('img');
                    img.src = f.url + (f.url.includes('?') ? '&v=' + Date.now() : '?v=' + Date.now());
                    img.alt = f.name;
                    img.style.width = '96px';
                    img.style.height = 'auto';
                    img.style.objectFit = 'contain';
                    img.style.marginBottom = '6px';
                    left.appendChild(img);
                }
                const name = document.createElement('div');
                name.textContent = f.name;
                const meta = document.createElement('div');
                meta.className = 'small text-muted';
                meta.textContent = `${f.size_kb} KB • ${f.mtime}`;
                left.appendChild(name);
                left.appendChild(meta);
                const right = document.createElement('div');
                right.className = 'd-flex gap-2';
                const loadBtn = document.createElement('button');
                loadBtn.type = 'button';
                loadBtn.className = 'btn btn-sm btn-outline-success';
                loadBtn.textContent = 'Wczytaj';
                loadBtn.addEventListener('click', async () => {
                    try {
                        setStatus(`Wczytywanie ${f.name}...`);
                        const resp = await fetch(`/uploads/load/${encodeURIComponent(f.name)}`);
                        if (!resp.ok) {
                            throw new Error(`HTTP ${resp.status}`);
                        }
                        const payload = await resp.json();
                        if (payload.error) {
                            throw new Error(payload.error);
                        }
                        // Use existing renderToCanvas flow
                        renderToCanvas(payload);
                        if (uploadsModal && typeof uploadsModal.close === 'function') {
                            uploadsModal.close();
                        }
                        setStatus(`✅ Wczytano ${f.name}`);
                    } catch (err) {
                        console.error('Nie udało się wczytać pliku z uploads', err);
                        setStatus('❌ Nie udało się wczytać pliku');
                    }
                });
                const showBtn = document.createElement('button');
                showBtn.type = 'button';
                showBtn.className = 'btn btn-sm btn-outline-secondary';
                showBtn.textContent = 'Pokaż ścieżkę';
                showBtn.addEventListener('click', async () => {
                    try {
                        if (navigator.clipboard && navigator.clipboard.writeText) {
                            await navigator.clipboard.writeText(f.name);
                            setStatus('Ścieżka skopiowana do schowka');
                        } else {
                            setStatus(`Ścieżka: ${f.name}`);
                        }
                    } catch (err) {
                        console.warn('Nie udało się skopiować ścieżki', err);
                        setStatus(`Ścieżka: ${f.name}`);
                    }
                });
                right.appendChild(loadBtn);
                right.appendChild(showBtn);
                row.appendChild(left);
                row.appendChild(right);
                list.appendChild(row);
            });
            uploadsList.appendChild(list);
        }
        try {
            if (typeof uploadsModal.showModal === 'function') {
                uploadsModal.showModal();
            } else {
                uploadsModal.classList.remove('hidden');
            }
        } catch (err) {
            uploadsModal.classList.remove('hidden');
        }
    }

    async function exportCurrentPage(options = {}) {
        if (!state.token || state.isExporting) {
            return;
        }

        const { dpi } = options;
        let requestedDpi;

        if (dpi !== undefined) {
            requestedDpi = dpi;
        } else {
            requestedDpi = calculateDpiFromPreset(state.dpiPreset);
        }

        const normalizedDpi = clampDpi(Math.round(requestedDpi));
        state.desiredDpi = normalizedDpi;

        if (exportDpiInput && state.dpiPreset === 'custom') {
            exportDpiInput.value = normalizedDpi;
        }

        state.isExporting = true;
        setExportStatus('Przygotowywanie pliku PNG...', 'muted');
        updateExportUI();

        try {
            const params = new URLSearchParams({ dpi: String(normalizedDpi) });
            const response = await fetch(`/page/${state.token}/${state.currentPage}/export?${params.toString()}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json();
            if (data.error) {
                throw new Error(data.error);
            }
            if (!data.download_url) {
                throw new Error('Brak linku pobierania');
            }

            triggerDownload(typeof data.filename === 'string' ? data.filename : '', data.download_url);

            const appliedDpi = typeof data.applied_dpi === 'number'
                ? data.applied_dpi
                : (typeof data.image_dpi === 'number' ? data.image_dpi : normalizedDpi);
            const requestedDpi = typeof data.requested_dpi === 'number'
                ? data.requested_dpi
                : normalizedDpi;
            const wasClamped = data.clamped === true;

            state.imageDpi = appliedDpi;
            state.desiredDpi = appliedDpi;

            if (typeof data.image_width_px === 'number') {
                state.pageWidthPx = data.image_width_px;
            }
            if (typeof data.image_height_px === 'number') {
                state.pageHeightPx = data.image_height_px;
            }
            if (typeof data.max_render_dpi === 'number') {
                state.maxRenderDpi = data.max_render_dpi;
            }
            if (typeof data.min_render_dpi === 'number') {
                state.minRenderDpi = data.min_render_dpi;
            }
            if (state.imageDpi) {
                if (state.pageWidthPx) {
                    state.pageWidthIn = state.pageWidthPx / state.imageDpi;
                }
                if (state.pageHeightPx) {
                    state.pageHeightIn = state.pageHeightPx / state.imageDpi;
                }
            }

            updateExportUI();

            let statusMessage = typeof data.filename === 'string'
                ? `Zapisano ${data.filename} (${appliedDpi} DPI).`
                : `Zapisano PNG (${appliedDpi} DPI).`;
            if (wasClamped && requestedDpi !== appliedDpi) {
                statusMessage += ` (Ograniczono z ${requestedDpi} do ${appliedDpi} DPI.)`;
            }
            setExportStatus(statusMessage, 'success');
        } catch (error) {
            console.error('Błąd eksportu strony PDF:', error);
            setExportStatus('Nie udało się przygotować pliku PNG.', 'error');
        } finally {
            state.isExporting = false;
            // If we loaded a regenerated preview image, apply canvas sizing and redraw
            if (state.currentImage) {
                calculateBaseScale();
                applyCanvasSize();
                resetPan();
                drawCurrentImage();
                onImageRendered(getDocumentContext());
            }
            updateExportUI();
        }
    }

    function resetDocument() {
        state.token = null;
        state.filename = null;
        state.lastImageUrl = null;
        state.currentPage = 1;
        state.totalPages = 1;
        state.currentImage = null;
        state.baseScale = 1;
        state.zoomLevel = 1;
        state.panX = 0;
        state.panY = 0;
        imageCanvas.classList.remove('has-image');
        ctx.clearRect(0, 0, imageCanvas.width, imageCanvas.height);
        state.imageDpi = null;
        state.pageWidthPx = null;
        state.pageHeightPx = null;
        state.pageWidthIn = null;
        state.pageHeightIn = null;
        state.maxRenderDpi = null;
        state.minRenderDpi = MIN_RENDER_DPI;
        state.desiredDpi = null;
        state.isExporting = false;
        state.exportStatusMessage = '';
        setExportStatus('');
        updateFilenamePill(null);
        if (fileInput) {
            fileInput.value = '';
        }
        updatePageUI();
        onDocumentCleared();
    }

    function wireEvents() {
        if (uploadBtn) {
            uploadBtn.addEventListener('click', handleUpload);
        }
        if (uploadFromUploadsBtn) {
            uploadFromUploadsBtn.addEventListener('click', async () => {
                try {
                    setStatus('Pobieram listę plików z uploads...');
                    const res = await fetch('/uploads/list');
                    if (!res.ok) {
                        throw new Error(`HTTP ${res.status}`);
                    }
                    const data = await res.json();
                    showUploadsModal(data.files || []);
                } catch (err) {
                    console.error('Nie udało się pobrać listy uploads', err);
                    setStatus('❌ Nie udało się pobrać listy plików z serwera');
                }
            });
        }
        if (uploadsCloseBtn) {
            uploadsCloseBtn.addEventListener('click', () => {
                if (uploadsModal && typeof uploadsModal.close === 'function') {
                    uploadsModal.close();
                }
            });
        }

        // Inicjalizacja checkboxa auto-save dla uploadu lokalnego
        const saveCheckbox = document.getElementById('uploadSaveOnLoadCheckbox');
        try {
            const stored = localStorage.getItem('autoSaveOnLoad');
            if (saveCheckbox) {
                if (stored === null) {
                    // domyślnie włączone
                    saveCheckbox.checked = true;
                    localStorage.setItem('autoSaveOnLoad', 'true');
                } else {
                    saveCheckbox.checked = stored === 'true';
                }
                saveCheckbox.addEventListener('change', (e) => {
                    localStorage.setItem('autoSaveOnLoad', e.target.checked ? 'true' : 'false');
                    setStatus(e.target.checked ? '📁 Automatyczne zapisywanie włączone' : '📁 Automatyczne zapisywanie wyłączone');
                });
            }
        } catch (err) {
            console.warn('Nie udało się odczytać ustawienia autoSaveOnLoad', err);
        }
        if (prevPageBtn) {
            prevPageBtn.addEventListener('click', () => changePage(-1));
        }

        if (nextPageBtn) {
            nextPageBtn.addEventListener('click', () => changePage(1));
        }

        if (pageInput) {
            pageInput.addEventListener('change', () => {
                const nextPage = Number(pageInput.value);
                if (Number.isNaN(nextPage)) {
                    pageInput.value = state.currentPage;
                    return;
                }
                const normalized = Math.min(state.totalPages, Math.max(1, Math.floor(nextPage)));
                if (normalized !== state.currentPage) {
                    fetchPage(normalized);
                } else {
                    pageInput.value = state.currentPage;
                }
            });

            pageInput.addEventListener('keyup', (event) => {
                if (event.key === 'Enter') {
                    event.preventDefault();
                    const nextPage = Number(pageInput.value);
                    if (Number.isNaN(nextPage)) {
                        pageInput.value = state.currentPage;
                        return;
                    }
                    const normalized = Math.min(state.totalPages, Math.max(1, Math.floor(nextPage)));
                    if (normalized !== state.currentPage) {
                        fetchPage(normalized);
                    } else {
                        pageInput.value = state.currentPage;
                    }
                    pageInput.blur();
                }
            });
        }

        if (zoomInBtn) {
            zoomInBtn.addEventListener('click', () => changeZoom(ZOOM_STEP));
        }

        if (zoomOutBtn) {
            zoomOutBtn.addEventListener('click', () => changeZoom(-ZOOM_STEP));
        }

        imageCanvas.addEventListener('pointerdown', handlePointerDown);
        imageCanvas.addEventListener('pointermove', handlePointerMove);
        imageCanvas.addEventListener('pointerup', endPan);
        imageCanvas.addEventListener('pointercancel', endPan);

        window.addEventListener('resize', handleResize);

        // Handler dla presetów DPI
        if (dpiPresetRadios) {
            for (const radio of dpiPresetRadios) {
                radio.addEventListener('change', () => {
                    if (!state.token || !radio.checked) {
                        return;
                    }

                    state.dpiPreset = radio.value;

                    if (radio.value === 'custom') {
                        // Przejdź do trybu własnego - user może edytować pole
                        const currentDpi = state.desiredDpi ?? state.imageDpi ?? DEFAULT_PREVIEW_DPI;
                        state.desiredDpi = currentDpi;
                    } else {
                        // Oblicz DPI z presetu
                        state.desiredDpi = calculateDpiFromPreset(radio.value);
                    }

                    setExportStatus('');
                    updateExportUI();
                });
            }
        }

        // Handler dla własnego DPI
        if (exportDpiInput) {
            exportDpiInput.addEventListener('change', () => {
                if (!state.token) {
                    exportDpiInput.value = '';
                    return;
                }

                const parsed = Number.parseInt(exportDpiInput.value, 10);
                if (Number.isNaN(parsed)) {
                    const fallback = state.imageDpi ?? DEFAULT_PREVIEW_DPI;
                    state.desiredDpi = fallback;
                    exportDpiInput.value = fallback;
                } else {
                    const normalized = clampDpi(parsed);
                    state.desiredDpi = normalized;
                    exportDpiInput.value = normalized;
                }

                // Automatycznie przełącz na "Własne"
                state.dpiPreset = 'custom';

                setExportStatus('');
                updateExportUI();
            });

            // Focus na polu automatycznie przełącza na "Własne"
            exportDpiInput.addEventListener('focus', () => {
                if (!state.token) {
                    return;
                }

                if (state.dpiPreset !== 'custom') {
                    state.dpiPreset = 'custom';
                    state.desiredDpi = calculateDpiFromPreset(state.dpiPreset);
                    updateExportUI();
                }
            });
        }

        // Przycisk pobierania
        if (downloadPageBtn) {
            downloadPageBtn.addEventListener('click', () => {
                const dpi = calculateDpiFromPreset(state.dpiPreset);
                void exportCurrentPage({ dpi });
            });
        }

    }


    function getDocumentContext() {
        return {
            token: state.token,
            filename: state.filename,
            currentPage: state.currentPage,
            totalPages: state.totalPages,
            lastImageUrl: state.lastImageUrl,
            image: state.currentImage,
            imageDpi: state.imageDpi,
            pageWidthPx: state.pageWidthPx,
            pageHeightPx: state.pageHeightPx,
            maxRenderDpi: getMaxRenderDpi(),
            minRenderDpi: state.minRenderDpi,
        };
    }

    function onUploadComplete(callback) {
        if (typeof callback === 'function') {
            uploadListeners.add(callback);
        }
    }

    wireEvents();
    updatePageUI();

    return {
        getDocumentContext,
        resetDocument,
        onUploadComplete,
    };
}
