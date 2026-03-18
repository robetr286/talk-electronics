import { formatTimestamp, parseTimestamp } from './utils/timestamp.js';

export function initImageProcessing(dom = {}, dependencies = {}) {
    const {
        historySelect,
        loadPageBtn,
        savePageBtn,
        loadFileBtn,
        loadFileInput,
        originalImage,
        originalPlaceholder,
        resultImage,
        resultPlaceholder,
        applyBtn,
        resetBtn,
        saveResultBtn,
    downloadBtn,
    sendToRetouchBtn,
    filterSelect,
    manualControls,
    adaptiveControls,
    otsuInfo,
    thresholdSlider,
    thresholdValue,
    adaptiveWindow,
    adaptiveWindowValue,
    adaptiveOffset,
    adaptiveOffsetValue,
        statusLabel,
        zoomInBtn,
        zoomOutBtn,
        zoomResetBtn,
        zoomLabel,
        historyList,
        historyClearBtn,
    } = dom;

    const { getDocumentContext = () => ({}), notifyRetouchBuffer = () => {} } = dependencies;

    const state = {
        history: [],
        current: null,
        processed: null,
        zoomLevel: 1,
        pan: { x: 0, y: 0 },
        isPanning: false,
        panStart: { x: 0, y: 0 },
        pointerId: null,
        filter: {
            type: 'manual',
            threshold: 128,
            adaptiveWindow: 15,
            adaptiveOffset: 5,
        },
        historyLoaded: false,
        isSyncingHistory: false,
    };

    let retouchNotifier = typeof notifyRetouchBuffer === 'function' ? notifyRetouchBuffer : () => {};

    function registerRetouchNotifier(callback) {
        retouchNotifier = typeof callback === 'function' ? callback : () => {};
    }

    function cacheBust(url) {
        if (!url) {
            return null;
        }
        if (!/^https?:/i.test(url)) {
            return url;
        }
        const separator = url.includes('?') ? '&' : '?';
        return `${url}${separator}t=${Date.now()}`;
    }

    function extractUploadFilename(url) {
        if (typeof url !== 'string' || !url) {
            return null;
        }
        try {
            const parsed = new URL(url, window.location.origin);
            const pathname = parsed.pathname || '';
            if (pathname.startsWith('/uploads/')) {
                return pathname.slice('/uploads/'.length);
            }
            return null;
        } catch (error) {
            if (url.startsWith('/uploads/')) {
                return url.slice('/uploads/'.length).split('?')[0];
            }
            return null;
        }
    }

    function resolvePreviewUrl(entry) {
        if (!entry || typeof entry !== 'object') {
            return null;
        }
        if (typeof entry.previewUrl === 'string' && entry.previewUrl) {
            return entry.previewUrl;
        }
        if (entry.meta && typeof entry.meta === 'object') {
            const metaPreview = entry.meta.previewUrl || entry.meta.preview_url;
            if (typeof metaPreview === 'string' && metaPreview) {
                return metaPreview;
            }
        }
        if (entry.payload && typeof entry.payload === 'object') {
            const payloadPreview = entry.payload.previewUrl || entry.payload.preview_url;
            if (typeof payloadPreview === 'string' && payloadPreview) {
                return payloadPreview;
            }
            const source = entry.payload.source;
            if (source && typeof source === 'object') {
                const sourcePreview = source.imageUrl || source.image_url || source.url;
                if (typeof sourcePreview === 'string' && sourcePreview) {
                    return sourcePreview;
                }
            }
        }
        return null;
    }

    function getEntryDownloadUrl(entry) {
        const preview = resolvePreviewUrl(entry);
        if (typeof preview === 'string' && preview) {
            return preview;
        }
        if (entry && typeof entry.url === 'string' && entry.url) {
            return entry.url;
        }
        return null;
    }

    function getEntryImageUrl(entry) {
        if (!entry) {
            return null;
        }
        if (entry.objectUrl) {
            return entry.objectUrl;
        }
        const downloadUrl = getEntryDownloadUrl(entry);
        if (typeof downloadUrl === 'string' && downloadUrl) {
            return cacheBust(downloadUrl);
        }
        return null;
    }

    function buildPageHistoryEntry(doc) {
        if (!doc || !doc.lastImageUrl) {
            return null;
        }
        const createdAt = new Date().toISOString();
        const pageNumber = doc.currentPage || doc.page || 1;
        const labelBase = doc.filename ? `PDF: ${doc.filename}` : 'Strona PDF';
        const entry = {
            id: `page-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
            url: doc.lastImageUrl,
            label: `${labelBase} (strona ${pageNumber})`,
            type: 'page',
            meta: {
                createdAt,
                typeLabel: 'Strona PDF',
                filename: doc.filename || null,
                sourcePage: pageNumber,
                totalPages: doc.totalPages || doc.total_pages || null,
            },
            payload: {
                documentToken: doc.token || null,
                page: pageNumber,
                filename: doc.filename || null,
                lastImageUrl: doc.lastImageUrl,
            },
        };
        const relative = extractUploadFilename(doc.lastImageUrl);

        if (relative) {
            entry.storage = {
                type: 'upload',
                filename: relative,
            };
        }
        return entry;
    }

    function revokeEntryUrl(entry) {
        if (entry && entry.objectUrl) {
            URL.revokeObjectURL(entry.objectUrl);
            entry.objectUrl = null;
        }
    }

    function toggleVisibility(imageEl, placeholderEl, shouldShowImage) {
        if (!imageEl || !placeholderEl) {
            return;
        }
        if (shouldShowImage) {
            imageEl.classList.remove('hidden');
            placeholderEl.classList.add('hidden');
        } else {
            imageEl.classList.add('hidden');
            placeholderEl.classList.remove('hidden');
        }
    }

    function setStatus(message) {
        if (statusLabel) {
            statusLabel.textContent = message;
        }
    }

    function updateProcessedButtons() {
        const hasProcessed = Boolean(state.processed && state.processed.url);
        if (saveResultBtn) {
            const canSave = hasProcessed && state.processed && !state.processed.persistent;
            saveResultBtn.disabled = !canSave;
        }
        if (downloadBtn) {
            downloadBtn.disabled = !hasProcessed;
        }
        if (sendToRetouchBtn) {
            sendToRetouchBtn.disabled = !hasProcessed;
        }
    }

    async function ensureEntryBlob(entry) {
        if (!entry) {
            throw new Error('Brak wpisu do pobrania bloba.');
        }
        if (entry.blob instanceof Blob) {
            return entry.blob;
        }
        if (entry.url) {
            const response = await fetch(entry.url);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const blob = await response.blob();
            entry.blob = blob;
            return blob;
        }
        throw new Error('Brak URL w wpisie.');
    }

    // Upewnij się, że wpis ma 'objectUrl' (blob: lub data: albo wygenerowane z blob)
    async function ensureEntryObjectUrl(entry) {
        if (!entry) {
            return null;
        }
        // jeśli mamy już objectUrl - zwróć
        if (entry.objectUrl) {
            return entry.objectUrl;
        }
        // jeśli entry.url jest data: lub blob: - ustaw jako objectUrl
        if (entry.url && /^(data|blob):/i.test(entry.url)) {
            entry.objectUrl = entry.url;
            return entry.objectUrl;
        }
        // spróbuj pobrać blob i utworzyć object URL
        try {
            const blob = await ensureEntryBlob(entry);
            if (blob instanceof Blob) {
                const obj = URL.createObjectURL(blob);
                entry.objectUrl = obj;
                // zachowaj blob w cache entry
                entry.blob = blob;
                return obj;
            }
            return null;
        } catch (err) {
            console.warn('[imageProcessing] ensureEntryObjectUrl failed:', err);
            return null;
        }
    }

    function buildUploadMetadata(entry, { includeProcessedId = false } = {}) {
        if (!entry) {
            return {};
        }
        const createdAt = entry.meta?.createdAt || new Date().toISOString();
        const meta = { ...(entry.meta || {}) };
        if (!meta.createdAt) {
            meta.createdAt = createdAt;
        }
        if (!meta.typeLabel && entry.meta?.typeLabel) {
            meta.typeLabel = entry.meta.typeLabel;
        }
        if (!meta.filter && entry.meta?.filter) {
            meta.filter = entry.meta.filter;
        }
        if (!meta.threshold && typeof entry.meta?.threshold === 'number') {
            meta.threshold = entry.meta.threshold;
        }
        if (!meta.thresholdLabel && entry.meta?.thresholdLabel) {
            meta.thresholdLabel = entry.meta.thresholdLabel;
        }
        if (!meta.sourceId && entry.basedOn?.id) {
            meta.sourceId = entry.basedOn.id;
        }
        if (includeProcessedId && entry.savedEntryId && !meta.processedId) {
            meta.processedId = entry.savedEntryId;
        }

        const metadata = {
            createdAt,
            filter: entry.meta?.filter,
            filterKey: entry.filterOptions?.type,
            threshold: entry.meta?.threshold,
            thresholdLabel: entry.meta?.thresholdLabel,
            stats: entry.stats,
            sourceId: entry.basedOn?.id || null,
            processedId: includeProcessedId ? entry.savedEntryId || null : undefined,
            filterOptions: entry.filterOptions,
            meta,
        };
        return metadata;
    }

    async function transferProcessedToRetouch({ silent = false } = {}) {
        let source = state.processed;
        // Fallback: jeśli brak bieżącego wyniku, sprawdź czy wybrany element historii to wynik obróbki
        if (!source || !source.url) {
            if (state.current && (state.current.type === 'processed' || state.current.type === 'retouch') && state.current.url) {
                source = state.current;
            }
        }

        if (!source || !source.url) {
            const error = new Error('Brak wyniku z binaryzacji do przekazania.');
            error.code = 'NO_PROCESSED_RESULT';
            throw error;
        }
        if (!silent && sendToRetouchBtn) {
            sendToRetouchBtn.disabled = true;
        }
        if (!silent) {
            setStatus('Przekazywanie materiału do retuszu...');
        }
        try {
            const blob = await ensureEntryBlob(source);
            const formData = new FormData();
            formData.append('file', blob, `retouch_${Date.now()}.png`);
            const metadata = buildUploadMetadata(source, { includeProcessedId: true });
            formData.append('metadata', JSON.stringify(metadata));
            const response = await fetch('/processing/send-to-retouch', {
                method: 'POST',
                body: formData,
            });
            if (!response.ok) {
                const error = new Error('Serwer odrzucił przekazanie do retuszu.');
                error.code = 'RET_TOUCH_UPLOAD_FAILED';
                error.status = response.status;
                throw error;
            }
            const data = await response.json();
            const entry = data?.entry || data;
            retouchNotifier(entry);
            if (!silent) {
                setStatus('Wynik przekazano do retuszu.');
            }
            return entry;
        } finally {
            updateProcessedButtons();
        }
    }

    function clamp(value, min, max) {
        if (!Number.isFinite(value)) {
            return min;
        }
        return Math.min(max, Math.max(min, value));
    }

    function updateFilterUi() {
        const { filter } = state;
        if (manualControls) {
            manualControls.classList.toggle('hidden', filter.type !== 'manual');
        }
        if (adaptiveControls) {
            adaptiveControls.classList.toggle('hidden', filter.type !== 'adaptive-mean');
        }
        if (otsuInfo) {
            otsuInfo.classList.toggle('hidden', filter.type !== 'otsu');
        }
        if (filterSelect && filterSelect.value !== filter.type) {
            filterSelect.value = filter.type;
        }
        if (thresholdSlider && filter.type === 'manual') {
            thresholdSlider.value = String(filter.threshold);
        }
        if (thresholdValue) {
            thresholdValue.textContent = String(filter.threshold);
        }
        if (adaptiveWindow && filter.type === 'adaptive-mean') {
            adaptiveWindow.value = String(filter.adaptiveWindow);
        }
        if (adaptiveWindowValue) {
            adaptiveWindowValue.textContent = `${filter.adaptiveWindow} px`;
        }
        if (adaptiveOffset && filter.type === 'adaptive-mean') {
            adaptiveOffset.value = String(filter.adaptiveOffset);
        }
        if (adaptiveOffsetValue) {
            adaptiveOffsetValue.textContent = String(filter.adaptiveOffset);
        }
    }

    function setFilterType(nextType) {
        if (!nextType) {
            return;
        }
        if (nextType === state.filter.type) {
            updateFilterUi();
            return;
        }
        state.filter.type = nextType;
        updateFilterUi();
    }

    // Use shared formatTimestamp util
    // formatTimestamp available via import at top of file

    function summarizeEntryMeta(entry) {
        const details = [];
        const { meta = {}, type } = entry;
        if (meta.typeLabel) {
            details.push(meta.typeLabel);
        } else if (type === 'crop') {
            details.push('Fragment kadrowania');
        } else if (type === 'processed') {
            details.push('Wynik obróbki');
        } else if (type === 'retouch') {
            details.push('Wynik retuszu');
        } else if (type === 'upload') {
            details.push('Import z dysku');
        }
        if (meta.sourcePage) {
            details.push(`Strona: ${meta.sourcePage}`);
        }
        if (meta.filename) {
            details.push(`Plik: ${meta.filename}`);
        }
        if (meta.sizeKb) {
            details.push(`Rozmiar: ${meta.sizeKb} KB`);
        }
        if (meta.filter) {
            details.push(`Filtr: ${meta.filter}`);
        }
        if (meta.thresholdLabel) {
            details.push(meta.thresholdLabel);
        }
        if (typeof meta.threshold === 'number') {
            details.push(`Prog: ${Math.round(meta.threshold)}`);
        }
        if (meta.width && meta.height) {
            details.push(`Wymiary: ${meta.width}×${meta.height}`);
        }
        if (type === 'symbol-detection') {
            if (meta.detector) {
                details.push(`Detektor: ${meta.detector}`);
            }
            if (meta.detections !== undefined) {
                details.push(`Detekcje: ${meta.detections}`);
            }
            if (meta.sourceLabel) {
                details.push(`Źródło: ${meta.sourceLabel}`);
            }
        }
        if (meta.createdAt) {
            details.push(`Dodano: ${formatTimestamp(meta.createdAt)}`);
        }
        if (details.length === 0) {
            return '';
        }
        return details.join(' • ');
    }

    function renderHistoryList() {
        if (!historyList) {
            return;
        }
        historyList.innerHTML = '';
        if (!state.historyLoaded) {
            const loading = document.createElement('div');
            loading.className = 'processing-history-empty';
            loading.textContent = 'Ładowanie historii...';
            historyList.append(loading);
            if (historyClearBtn) {
                historyClearBtn.disabled = true;
            }
            return;
        }

        if (!state.history.length) {
            const emptyItem = document.createElement('div');
            emptyItem.className = 'processing-history-empty';
            emptyItem.textContent = 'Brak zapisanych fragmentów';
            historyList.append(emptyItem);
            if (historyClearBtn) {
                historyClearBtn.disabled = true;
            }
            return;
        }
        if (historyClearBtn) {
            historyClearBtn.disabled = false;
        }
        const activeId = state.current && state.current.id ? state.current.id : null;
        const entries = [...state.history].reverse();
        entries.forEach((entry) => {
            const item = document.createElement('li');
            item.className = 'processing-history-item';
            item.dataset.entryId = entry.id;
            item.dataset.active = String(entry.id === activeId);

            const thumb = document.createElement('div');
            thumb.className = 'processing-history-thumb';
            const previewUrl = getEntryImageUrl(entry);
            if (previewUrl) {
                const img = document.createElement('img');
                img.src = previewUrl;
                img.alt = entry.label || 'Podgląd fragmentu';
                img.loading = 'lazy';
                img.decoding = 'async';
                thumb.append(img);
            } else {
                thumb.dataset.empty = 'true';
                thumb.textContent = 'Brak podglądu';
            }

            const info = document.createElement('div');
            const title = document.createElement('div');
            title.className = 'fw-semibold';
            title.textContent = entry.label;
            info.append(title);

            const meta = summarizeEntryMeta(entry);
            if (meta) {
                const metaEl = document.createElement('p');
                metaEl.className = 'processing-history-meta';
                metaEl.textContent = meta;
                info.append(metaEl);
            }

            const actions = document.createElement('div');
            actions.className = 'processing-history-actions';

            const useBtn = document.createElement('button');
            useBtn.type = 'button';
            useBtn.className = 'btn btn-outline-success btn-sm';
            useBtn.dataset.action = 'use';
            useBtn.dataset.entryId = entry.id;
            useBtn.textContent = 'Wybierz';

            const removeBtn = document.createElement('button');
            removeBtn.type = 'button';
            removeBtn.className = 'btn btn-outline-danger btn-sm';
            removeBtn.dataset.action = 'remove';
            removeBtn.dataset.entryId = entry.id;
            removeBtn.textContent = 'Usuń';

            actions.append(useBtn, removeBtn);
            item.append(thumb, info, actions);
            historyList.append(item);
        });
    }

    function refreshHistoryUi() {
        console.log('[imageProcessing] refreshHistoryUi - aktualizuję UI historii');
        updateHistorySelect();
        renderHistoryList();
    }

    function updateZoomLabel() {
        if (zoomLabel) {
            zoomLabel.textContent = `${Math.round(state.zoomLevel * 100)}%`;
        }
        if (zoomOutBtn) {
            zoomOutBtn.disabled = state.zoomLevel <= 0.25;
        }
        if (zoomInBtn) {
            zoomInBtn.disabled = state.zoomLevel >= 4;
        }
        if (zoomResetBtn) {
            zoomResetBtn.disabled = state.zoomLevel === 1 && state.pan.x === 0 && state.pan.y === 0;
        }
    }

    function applyTransform(target) {
        if (!target) {
            return;
        }
        const translate = `translate(${state.pan.x}px, ${state.pan.y}px)`;
        const scale = `scale(${state.zoomLevel})`;
        target.style.transform = `${translate} ${scale}`;
        target.style.transformOrigin = 'center center';
    }

    function resetTransform(target) {
        state.zoomLevel = 1;
        state.pan = { x: 0, y: 0 };
        applyTransform(target);
        updateZoomLabel();
    }

    function updateZoom(delta, focusPoint = null) {
        const prevLevel = state.zoomLevel;
        const nextLevel = Math.min(4, Math.max(0.25, prevLevel + delta));
        if (Math.abs(nextLevel - prevLevel) < 0.001) {
            return;
        }
        state.zoomLevel = nextLevel;

        if (focusPoint) {
            const offsetX = focusPoint.x - state.pan.x;
            const offsetY = focusPoint.y - state.pan.y;
            state.pan.x = focusPoint.x - (offsetX * nextLevel) / prevLevel;
            state.pan.y = focusPoint.y - (offsetY * nextLevel) / prevLevel;
        }

        applyTransform(originalImage);
        applyTransform(resultImage);
        updateZoomLabel();
    }

    function handlePointerDown(event, target) {
        if (!target) {
            return;
        }
        event.preventDefault();
        state.isPanning = true;
        state.pointerId = event.pointerId;
        state.panStart = { x: event.clientX - state.pan.x, y: event.clientY - state.pan.y };
        target.classList.add('is-panning');
        target.setPointerCapture(event.pointerId);
    }

    function handlePointerMove(event, target) {
        if (!state.isPanning || event.pointerId !== state.pointerId || !target) {
            return;
        }
        state.pan.x = event.clientX - state.panStart.x;
        state.pan.y = event.clientY - state.panStart.y;
        applyTransform(originalImage);
        applyTransform(resultImage);
    }

    function handlePointerUp(event, target) {
        if (event.pointerId !== state.pointerId || !target) {
            return;
        }
        state.isPanning = false;
        state.pointerId = null;
        target.classList.remove('is-panning');
        try {
            target.releasePointerCapture(event.pointerId);
        } catch (error) {
            console.debug('Pointer capture already released', error);
        }
        updateZoomLabel();
    }

    function handleWheel(event) {
        event.preventDefault();
        const rect = event.currentTarget.getBoundingClientRect();
        const focus = {
            x: event.clientX - rect.left,
            y: event.clientY - rect.top,
        };
        const delta = event.deltaY < 0 ? 0.1 : -0.1;
        updateZoom(delta, focus);
    }

    function wireZoomControls(stageEl) {
        if (!stageEl) {
            return;
        }
        stageEl.classList.add('zoomable');
        stageEl.addEventListener('pointerdown', (event) => handlePointerDown(event, stageEl));
        stageEl.addEventListener('pointermove', (event) => handlePointerMove(event, stageEl));
        stageEl.addEventListener('pointerup', (event) => handlePointerUp(event, stageEl));
        stageEl.addEventListener('pointercancel', (event) => handlePointerUp(event, stageEl));
        stageEl.addEventListener('wheel', handleWheel, { passive: false });
        stageEl.addEventListener('contextmenu', (event) => event.preventDefault());
    }

    function clearResultStage() {
        if (state.processed) {
            if (!state.processed.persistent && state.processed.objectUrl) {
                URL.revokeObjectURL(state.processed.objectUrl);
            }
            state.processed.blob = null;
        }
        state.processed = null;
        if (resultImage) {
            resultImage.src = '';
            resultImage.style.transform = '';
        }
        toggleVisibility(resultImage, resultPlaceholder, false);
        if (resetBtn) {
            resetBtn.disabled = true;
        }
        updateProcessedButtons();
    }

    function enableProcessingControls(enabled) {
        if (applyBtn) {
            applyBtn.disabled = !enabled;
        }
    }

    function setOriginal(entry) {
        console.log('[imageProcessing] setOriginal wywołane z entry:', entry);
        state.current = entry;
        const imageUrl = getEntryImageUrl(entry);
        console.log('[imageProcessing] imageUrl:', imageUrl);
        toggleVisibility(originalImage, originalPlaceholder, Boolean(imageUrl));
        clearResultStage();
        enableProcessingControls(Boolean(imageUrl));
        resetTransform(originalImage);
        resetTransform(resultImage);
        if (originalImage) {
            if (imageUrl) {
                console.log('[imageProcessing] Ustawiam originalImage.src na:', imageUrl);
                originalImage.src = imageUrl;
                applyTransform(originalImage);
                if (!entry.objectUrl) {
                    void ensureEntryObjectUrl(entry).then((objectUrl) => {
                        if (!objectUrl) {
                            return;
                        }
                        const isCurrent = state.current && state.current.id === entry.id;
                        if (isCurrent && originalImage.src !== objectUrl) {
                            originalImage.src = objectUrl;
                            applyTransform(originalImage);
                        }
                    });
                }
            } else {
                originalImage.src = '';
            }
        }
        const downloadUrl = getEntryDownloadUrl(entry);
        if (downloadUrl) {
            const label = entry.label ? `: ${entry.label}` : '';
            setStatus(`Gotowy do obróbki${label}`.trim());
        } else {
            setStatus('Wybierz fragment, aby rozpocząć obróbkę.');
        }
        if (historySelect && entry.id) {
            const exists = state.history.some((historyEntry) => historyEntry.id === entry.id);
            console.log('[imageProcessing] Ustawiam historySelect.value na:', exists ? entry.id : historySelect.value);
            historySelect.value = exists ? entry.id : historySelect.value;
        }
        renderHistoryList();
    }

    function updateHistorySelect() {
        if (!historySelect) {
            console.warn('[imageProcessing] historySelect nie istnieje');
            return;
        }
        console.log('[imageProcessing] updateHistorySelect - liczba wpisów:', state.history.length);
        historySelect.innerHTML = '';
        if (!state.historyLoaded) {
            const option = document.createElement('option');
            option.value = '';
            option.textContent = 'Ładowanie...';
            historySelect.append(option);
            historySelect.disabled = true;
            return;
        }

        if (state.history.length === 0) {
            const option = document.createElement('option');
            option.value = '';
            option.textContent = 'Brak zapisanych fragmentów';
            historySelect.append(option);
            historySelect.disabled = true;
            return;
        }
        historySelect.disabled = false;
        state.history.forEach((entry) => {
            const option = document.createElement('option');
            option.value = entry.id;
            option.textContent = entry.label;
            historySelect.append(option);
        });
        const hasCurrentInHistory = Boolean(
            state.current &&
            state.current.id &&
            state.history.some((entry) => entry.id === state.current.id),
        );
        const activeId = hasCurrentInHistory
            ? state.current.id
            : state.history[state.history.length - 1].id;
        console.log('[imageProcessing] Ustawiam aktywny wpis na:', activeId);
        historySelect.value = activeId;
    }

    function findHistoryEntry(id) {
        return state.history.find((entry) => entry.id === id) || null;
    }

    function sortHistory() {
        state.history.sort((a, b) => {
            const timeA = new Date(a?.meta?.createdAt || 0).getTime();
            const timeB = new Date(b?.meta?.createdAt || 0).getTime();
            return timeA - timeB;
        });
    }

    function integrateHistoryEntry(entry, { setAsCurrent = false } = {}) {
        console.log('[imageProcessing] integrateHistoryEntry wywołane:', { entry, setAsCurrent });
        if (!entry || !entry.id) {
            console.warn('[imageProcessing] Brak entry lub entry.id');
            return;
        }
        const index = state.history.findIndex((item) => item.id === entry.id);
        if (index === -1) {
            console.log('[imageProcessing] Dodaję nowy wpis do historii');
            state.history.push(entry);
        } else {
            console.log('[imageProcessing] Aktualizuję istniejący wpis w historii');
            revokeEntryUrl(state.history[index]);
            state.history[index] = entry;
        }
        sortHistory();
        refreshHistoryUi();
        console.log('[imageProcessing] Historia po integracji:', state.history.length, 'wpisów');
        if (setAsCurrent) {
            console.log('[imageProcessing] Ustawiam jako current przez setOriginal');
            setOriginal(entry);
        }
    }

    function removeHistoryEntryLocally(entryId) {
        const index = state.history.findIndex((entry) => entry.id === entryId);
        if (index === -1) {
            return null;
        }
        const [entry] = state.history.splice(index, 1);
        revokeEntryUrl(entry);
        if (state.current && state.current.id === entryId) {
            resetOriginal();
        }
        if (state.processed && state.processed.savedEntryId === entryId) {
            state.processed.persistent = false;
            state.processed.savedEntryId = null;
        }
        sortHistory();
        refreshHistoryUi();
        return entry;
    }

    function clearHistoryState({ silent = false } = {}) {
        state.history.forEach(revokeEntryUrl);
        state.history = [];
        refreshHistoryUi();
        if (!silent) {
            setStatus('Wyczyszczono historię fragmentów.');
        }
    }

    function prepareEntryForServer(entry) {
        return JSON.parse(
            JSON.stringify(entry, (key, value) => {
                if (key === 'objectUrl') {
                    return undefined;
                }
                return value;
            }),
        );
    }

    async function fetchHistoryFromServer() {
        if (state.isSyncingHistory) {
            return;
        }
        state.isSyncingHistory = true;
        try {
            const response = await fetch('/processing/history?scope=image-processing', {
                method: 'GET',
                headers: { Accept: 'application/json' },
            });
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const payload = await response.json();
            const entries = Array.isArray(payload)
                ? payload
                : Array.isArray(payload?.entries)
                    ? payload.entries
                    : [];
            const validTypes = new Set(['crop', 'upload', 'processed', 'page', 'retouch']);
            clearHistoryState({ silent: true });
            state.history = entries.filter((entry) => !entry?.type || validTypes.has(entry.type));
            sortHistory();
            refreshHistoryUi();
            if (state.current && state.current.id) {
                const exists = findHistoryEntry(state.current.id);
                if (!exists && state.current.type !== 'page') {
                    resetOriginal();
                }
            }
            state.historyLoaded = true;
        } catch (error) {
            console.error('Nie udało się pobrać historii z serwera', error);
            if (!state.historyLoaded) {
                setStatus('Nie udało się pobrać historii z serwera. Fragmenty będą dostępne lokalnie.');
            }
        } finally {
            state.isSyncingHistory = false;
        }
    }

    async function persistHistoryEntry(entry, { setAsCurrent = false, statusMessage = null } = {}) {
        try {
            const payload = prepareEntryForServer(entry);
            const response = await fetch('/processing/history', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json();
            const savedEntry = data?.entry || data;
            integrateHistoryEntry(savedEntry, { setAsCurrent });
            if (statusMessage) {
                setStatus(statusMessage);
            }
            return savedEntry;
        } catch (error) {
            console.error('Nie udało się zapisać historii', error);
            setStatus('Nie można zsynchronizować historii z serwerem.');
            throw error;
        }
    }

    async function deleteHistoryEntry(entryId, { showStatus = true } = {}) {
        if (!entryId) {
            return false;
        }
        try {
            const response = await fetch(`/processing/history/${encodeURIComponent(entryId)}`, {
                method: 'DELETE',
            });
            if (response.status === 404) {
                removeHistoryEntryLocally(entryId);
                if (showStatus) {
                    setStatus('Fragment został już wcześniej usunięty.');
                }
                return true;
            }
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            removeHistoryEntryLocally(entryId);
            if (showStatus) {
                setStatus('Fragment został usunięty z historii.');
            }
            return true;
        } catch (error) {
            console.error('Nie udało się usunąć fragmentu historii', error);
            setStatus('Nie można usunąć fragmentu z historii. Spróbuj ponownie.');
            return false;
        }
    }

    async function clearHistoryOnServer({ silent = false } = {}) {
        try {
            const response = await fetch('/processing/history?scope=image-processing', {
                method: 'DELETE',
            });
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            clearHistoryState({ silent });
            return true;
        } catch (error) {
            console.error('Nie udało się wyczyścić historii', error);
            setStatus('Nie można wyczyścić historii. Spróbuj ponownie później.');
            return false;
        }
    }

    function createHistoryEntry(payload) {
        const createdAt = new Date().toISOString();
        const humanTime = new Date(createdAt).toLocaleString();
        const page = payload.documentContext?.currentPage;
        const baseLabel = page ? `Fragment: strona ${page}` : 'Fragment schematu';
        const size = payload.sizeKb ? `, ${payload.sizeKb} KB` : '';
        const filename = payload.documentContext?.filename;
        return {
            id: `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
            url: payload.url,
            label: `${baseLabel}${size} (${humanTime})`,
            payload,
            type: 'crop',
            storage: {
                type: 'crop',
                filename: payload.filename || null,
            },
            meta: {
                createdAt,
                typeLabel: 'Fragment kadrowania',
                sourcePage: page,
                filename,
                sizeKb: payload.sizeKb || null,
            },
        };
    }

    async function handleCropSaved(payload) {
        console.log('[imageProcessing] handleCropSaved wywołane z payload:', payload);
        if (!payload || !payload.url) {
            console.warn('[imageProcessing] Brak payload lub payload.url');
            return;
        }
        const entry = createHistoryEntry(payload);
        console.log('[imageProcessing] Utworzono entry:', entry);
        if (typeof payload.objectUrl === 'string' && payload.objectUrl.startsWith('blob:')) {
            entry.objectUrl = payload.objectUrl;
        } else {
            try {
                const response = await fetch(payload.url, { cache: 'no-store' });
                if (response.ok) {
                    const blob = await response.blob();
                    entry.objectUrl = URL.createObjectURL(blob);
                }
            } catch (error) {
                console.warn('Nie udało się wczytać podglądu fragmentu z serwera', error);
            }
        }
        try {
            console.log('[imageProcessing] Rozpoczynam persistHistoryEntry...');
            const savedEntry = await persistHistoryEntry(entry, {
                setAsCurrent: true,
                statusMessage: 'Gotowy do obróbki: zapisany fragment został wczytany.',
            });
            console.log('[imageProcessing] persistHistoryEntry zwróciło:', savedEntry);
            if (entry.objectUrl) {
                savedEntry.objectUrl = entry.objectUrl;
            }
        } catch (error) {
            console.error('Nie udało się zsynchronizować nowego fragmentu', error);
            integrateHistoryEntry(entry, { setAsCurrent: true });
            setStatus('Fragment zapisano lokalnie, ale synchronizacja z serwerem nie powiodła się.');
        }
    }

    function loadImageResource(url) {
        return new Promise((resolve, reject) => {
            const img = new Image();
            if (/^https?:/i.test(url)) {
                img.crossOrigin = 'anonymous';
            }
            img.onload = () => resolve(img);
            img.onerror = (error) => reject(error);
            img.src = url;
        });
    }

    function computeIntegralImage(grayscale, width, height) {
        const integralWidth = width + 1;
        const integral = new Float64Array(integralWidth * (height + 1));
        for (let y = 1; y <= height; y += 1) {
            let rowSum = 0;
            for (let x = 1; x <= width; x += 1) {
                const gray = grayscale[(y - 1) * width + (x - 1)];
                rowSum += gray;
                const idx = y * integralWidth + x;
                integral[idx] = integral[(y - 1) * integralWidth + x] + rowSum;
            }
        }
        return { integral, stride: width + 1 };
    }

    function getIntegralRegionSum(integralImage, x0, y0, x1, y1) {
        const { integral, stride } = integralImage;
        const left = x0;
        const top = y0;
        const right = x1 + 1;
        const bottom = y1 + 1;
        return (
            integral[bottom * stride + right] -
            integral[top * stride + right] -
            integral[bottom * stride + left] +
            integral[top * stride + left]
        );
    }

    function computeOtsuThreshold(histogram, totalPixels) {
        let sumAll = 0;
        for (let i = 0; i < histogram.length; i += 1) {
            sumAll += i * histogram[i];
        }
        let sumBackground = 0;
        let weightBackground = 0;
        let maxVariance = 0;
        let bestThreshold = 0;

        for (let i = 0; i < histogram.length; i += 1) {
            weightBackground += histogram[i];
            if (weightBackground === 0) {
                continue;
            }
            const weightForeground = totalPixels - weightBackground;
            if (weightForeground === 0) {
                break;
            }
            sumBackground += i * histogram[i];
            const meanBackground = sumBackground / weightBackground;
            const meanForeground = (sumAll - sumBackground) / weightForeground;
            const variance = weightBackground * weightForeground * (meanBackground - meanForeground) ** 2;
            if (variance > maxVariance) {
                maxVariance = variance;
                bestThreshold = i;
            }
        }
        return bestThreshold;
    }

    function applyFilterToImageData(imageData, options) {
        const { width, height, data } = imageData;
        const pixelCount = width * height;
        const grayscale = new Float32Array(pixelCount);
        const histogram = new Uint32Array(256);
        let grayscaleSum = 0;

        for (let i = 0, idx = 0; i < data.length; i += 4, idx += 1) {
            const gray = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
            grayscale[idx] = gray;
            grayscaleSum += gray;
            histogram[Math.max(0, Math.min(255, Math.round(gray)))] += 1;
        }

        let darkPixels = 0;
        const stats = {
            width,
            height,
            pixelCount,
            meanGray: grayscaleSum / pixelCount,
            filterType: options.type,
        };

        if (options.type === 'manual') {
            const threshold = clamp(Number(options.threshold) || 0, 0, 255);
            for (let i = 0, idx = 0; i < data.length; i += 4, idx += 1) {
                const value = grayscale[idx] >= threshold ? 255 : 0;
                if (value === 0) {
                    darkPixels += 1;
                }
                data[i] = value;
                data[i + 1] = value;
                data[i + 2] = value;
                data[i + 3] = 255;
            }
            stats.threshold = threshold;
        } else if (options.type === 'otsu') {
            const threshold = computeOtsuThreshold(histogram, pixelCount);
            for (let i = 0, idx = 0; i < data.length; i += 4, idx += 1) {
                const value = grayscale[idx] >= threshold ? 255 : 0;
                if (value === 0) {
                    darkPixels += 1;
                }
                data[i] = value;
                data[i + 1] = value;
                data[i + 2] = value;
                data[i + 3] = 255;
            }
            stats.threshold = threshold;
        } else if (options.type === 'adaptive-mean') {
            const rawWindow = options.windowSize || 15;
            const offset = Number(options.offset) || 0;
            const windowSize = Math.max(3, rawWindow | 0);
            const window = windowSize % 2 === 0 ? windowSize + 1 : windowSize;
            const halfWindow = Math.floor(window / 2);
            const integralData = computeIntegralImage(grayscale, width, height);
            let thresholdAccumulator = 0;

            for (let y = 0; y < height; y += 1) {
                const top = Math.max(0, y - halfWindow);
                const bottom = Math.min(height - 1, y + halfWindow);
                for (let x = 0; x < width; x += 1) {
                    const left = Math.max(0, x - halfWindow);
                    const right = Math.min(width - 1, x + halfWindow);
                    const area = (right - left + 1) * (bottom - top + 1);
                    const sum = getIntegralRegionSum(integralData, left, top, right, bottom);
                    const localMean = sum / area;
                    const threshold = clamp(localMean - offset, 0, 255);
                    thresholdAccumulator += threshold;
                    const idx = y * width + x;
                    const value = grayscale[idx] >= threshold ? 255 : 0;
                    if (value === 0) {
                        darkPixels += 1;
                    }
                    const dataIndex = idx * 4;
                    data[dataIndex] = value;
                    data[dataIndex + 1] = value;
                    data[dataIndex + 2] = value;
                    data[dataIndex + 3] = 255;
                }
            }
            stats.thresholdAverage = thresholdAccumulator / pixelCount;
            stats.adaptiveWindow = window;
            stats.adaptiveOffset = offset;
        } else {
            throw new Error(`Nieznany filtr: ${options.type}`);
        }

        stats.darkPixels = darkPixels;
        stats.darkRatio = pixelCount ? darkPixels / pixelCount : 0;
        return stats;
    }

    function generateProcessedPreview(image, options) {
        const width = image.naturalWidth || image.width;
        const height = image.naturalHeight || image.height;
        if (!width || !height) {
            throw new Error('Nie można odczytać rozmiaru obrazu.');
        }
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(image, 0, 0, width, height);

        let imageData;
        try {
            imageData = ctx.getImageData(0, 0, width, height);
        } catch (error) {
            throw new Error('Nie można odczytać pikseli (problem z CORS).');
        }

        const stats = applyFilterToImageData(imageData, options);
        ctx.putImageData(imageData, 0, 0);

        return new Promise((resolve, reject) => {
            canvas.toBlob((blob) => {
                if (!blob) {
                    reject(new Error('Nie udało się wygenerować obrazu.'));
                    return;
                }
                const objectUrl = URL.createObjectURL(blob);
                resolve({
                    url: objectUrl,
                    objectUrl,
                    blob,
                    stats,
                });
            }, 'image/png');
        });
    }

    function getCurrentFilterOptions() {
        const { filter } = state;
        if (filter.type === 'manual') {
            return {
                type: 'manual',
                threshold: Math.round(clamp(filter.threshold, 0, 255)),
            };
        }
        if (filter.type === 'adaptive-mean') {
            const rawWindow = clamp(filter.adaptiveWindow, 3, 101);
            const windowSize = rawWindow % 2 === 0 ? rawWindow + 1 : rawWindow;
            return {
                type: 'adaptive-mean',
                windowSize,
                offset: Math.round(clamp(filter.adaptiveOffset, -255, 255)),
            };
        }
        return { type: 'otsu' };
    }

    function getFilterLabel(options) {
        if (options.type === 'manual') {
            return `Próg ręczny (${options.threshold})`;
        }
        if (options.type === 'adaptive-mean') {
            return `Adaptacyjny (okno ${options.windowSize}, korekta ${options.offset})`;
        }
        return 'Otsu';
    }

    function getThresholdLabel(options, stats) {
        if (options.type === 'manual') {
            return `Próg: ${Math.round(options.threshold)}`;
        }
        if (options.type === 'otsu') {
            return `Próg Otsu: ${Math.round(stats.threshold ?? 0)}`;
        }
        if (options.type === 'adaptive-mean') {
            const avg = stats.thresholdAverage ?? stats.threshold ?? 0;
            return `Średni próg lokalny: ${Math.round(avg)}`;
        }
        return null;
    }

    function createProcessedMeta(options, stats) {
        const createdAt = new Date().toISOString();
        const meta = {
            createdAt,
            filter: getFilterLabel(options),
            filterKey: options.type,
            width: stats.width,
            height: stats.height,
            darkRatio: stats.darkRatio,
            typeLabel: 'Wynik obróbki',
        };
        const thresholdLabel = getThresholdLabel(options, stats);
        if (thresholdLabel) {
            meta.thresholdLabel = thresholdLabel;
        }
        if (typeof stats.threshold === 'number') {
            meta.threshold = stats.threshold;
        }
        if (options.type === 'adaptive-mean') {
            meta.adaptiveWindow = stats.adaptiveWindow || options.windowSize;
            meta.adaptiveOffset = stats.adaptiveOffset ?? options.offset;
            if (typeof stats.thresholdAverage === 'number') {
                meta.threshold = stats.thresholdAverage;
            }
        }
        meta.meanGray = stats.meanGray;
        return meta;
    }

    async function applyPreprocessing() {
        if (!state.current || !state.current.url) {
            setStatus('Brak fragmentu do obróbki. Zapisz kadrowanie lub wczytaj stronę.');
            return;
        }
        if (applyBtn) {
            applyBtn.disabled = true;
        }
        const filterOptions = getCurrentFilterOptions();
        if (filterOptions.type === 'manual') {
            setStatus('Trwa obróbka: progowanie ręczne.');
        } else if (filterOptions.type === 'adaptive-mean') {
            setStatus('Trwa obróbka: progowanie adaptacyjne.');
        } else {
            setStatus('Trwa obróbka: wyszukiwanie progu metodą Otsu.');
        }
        try {
            const image = await loadImageResource(state.current.url);
            const preview = await generateProcessedPreview(image, filterOptions);

            if (
                state.processed &&
                !state.processed.persistent &&
                state.processed.objectUrl &&
                state.processed.objectUrl !== preview.objectUrl
            ) {
                URL.revokeObjectURL(state.processed.objectUrl);
            }

            state.processed = {
                basedOn: state.current,
                url: preview.url,
                objectUrl: preview.objectUrl,
                pipeline: 'image-preprocessing',
                stats: preview.stats,
                persistent: false,
                filterOptions,
                blob: preview.blob,
                meta: {
                    ...createProcessedMeta(filterOptions, preview.stats),
                    sourceId: state.current?.id || null,
                },
            };

            if (resultImage) {
                resultImage.src = preview.url;
                applyTransform(resultImage);
            }
            toggleVisibility(resultImage, resultPlaceholder, true);
            if (resetBtn) {
                resetBtn.disabled = false;
            }
            if (saveResultBtn) {
                saveResultBtn.disabled = false;
            }
            const filterLabel = state.processed.meta?.filter || 'Filtr zastosowany';
            setStatus(`Zastosowano filtr: ${filterLabel}.`);
        } catch (error) {
            console.error('Błąd podczas obróbki obrazu', error);
            setStatus('Nie udało się zastosować filtrów. Sprawdź źródło obrazu (CORS) lub spróbuj ponownie.');
        } finally {
            if (applyBtn && state.current && state.current.url) {
                applyBtn.disabled = false;
            }
            updateProcessedButtons();
        }
    }

    function resetOriginal() {
        state.current = null;
        if (originalImage) {
            originalImage.src = '';
            originalImage.style.transform = '';
        }
        toggleVisibility(originalImage, originalPlaceholder, false);
        clearResultStage();
        enableProcessingControls(false);
        setStatus('Wybierz fragment, aby rozpocząć obróbkę.');
        if (historySelect) {
            historySelect.value = '';
        }
        if (savePageBtn) {
            savePageBtn.disabled = true;
        }
    }

    async function handleCleanup() {
        await clearHistoryOnServer({ silent: true });
        resetOriginal();
    }

    function loadCurrentPagePreview(context = null, options = {}) {
        const { force = false } = options;
        const doc = context || getDocumentContext() || {};
        if (!doc || !doc.lastImageUrl) {
            return;
        }
        const entry = {
            id: 'current-page',
            url: doc.lastImageUrl,
            label: doc.currentPage ? `Podgląd strony ${doc.currentPage}` : 'Bieżąca strona PDF',
            type: 'page',
            payload: { documentContext: doc },
        };
        if (savePageBtn) {
            savePageBtn.disabled = false;
        }
        if (force || !state.current || state.current.type === 'page') {
            setOriginal(entry);
        }
    }

    if (historySelect) {
        historySelect.addEventListener('change', () => {
            if (!historySelect.value) {
                return;
            }
            const entry = findHistoryEntry(historySelect.value);
            if (entry) {
                setOriginal(entry);
                setStatus(`Wybrano zapisany fragment: ${entry.label}`);
            }
        });
    }

    if (loadPageBtn) {
        loadPageBtn.addEventListener('click', () => {
            const context = getDocumentContext();
            if (!context || !context.lastImageUrl) {
                setStatus('Brak wczytanego PDF. Prześlij dokument, aby zobaczyć stronę.');
                return;
            }
            loadCurrentPagePreview(context, { force: true });
            setStatus('Załadowano bieżącą stronę PDF do obróbki.');
        });
    }

    if (savePageBtn) {
        savePageBtn.addEventListener('click', async () => {
            const context = getDocumentContext();
            if (!context || !context.lastImageUrl) {
                setStatus('Brak strony PDF do zapisania.');
                return;
            }
            const entry = buildPageHistoryEntry(context);
            if (!entry) {
                setStatus('Nie udało się przygotować strony do historii.');
                return;
            }
            try {
                savePageBtn.disabled = true;
                setStatus('Zapisywanie strony PDF w historii...');
                await persistHistoryEntry(entry, {
                    setAsCurrent: true,
                    statusMessage: 'Strona PDF została dodana do historii.',
                });
            } catch (error) {
                console.error('Nie udało się zapisać strony PDF w historii', error);
                setStatus('Nie można zapisać strony PDF w historii. Spróbuj ponownie.');
            } finally {
                savePageBtn.disabled = false;
            }
        });
    }

    async function handleFileSelection(event) {
        const file = event?.target?.files?.[0];
        if (!file) {
            return;
        }
        const formData = new FormData();
        formData.append('file', file);
        if (loadFileInput) {
            loadFileInput.value = '';
        }
        try {
            setStatus('Wysyłanie fragmentu na serwer...');
            const response = await fetch('/processing/import', {
                method: 'POST',
                body: formData,
            });
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json();
            const entry = data?.entry || data;
            integrateHistoryEntry(entry, { setAsCurrent: true });
            setStatus('Wczytano fragment z dysku. Możesz zastosować obróbkę.');
        } catch (error) {
            console.error('Nie udało się wczytać fragmentu z dysku', error);
            setStatus('Nie można wczytać fragmentu z dysku. Spróbuj ponownie.');
        }
    }

    if (loadFileBtn && loadFileInput) {
        loadFileBtn.addEventListener('click', () => {
            loadFileInput.click();
        });
        loadFileInput.addEventListener('change', handleFileSelection);
    }

    if (filterSelect) {
        filterSelect.addEventListener('change', (event) => {
            setFilterType(event.target.value);
        });
    }

    if (thresholdSlider) {
        thresholdSlider.addEventListener('input', (event) => {
            const value = Number(event.target.value);
            state.filter.threshold = clamp(value, 0, 255);
            updateFilterUi();
        });
    }

    if (adaptiveWindow) {
        adaptiveWindow.addEventListener('input', (event) => {
            const value = Number(event.target.value);
            state.filter.adaptiveWindow = clamp(value, 3, 101);
            updateFilterUi();
        });
    }

    if (adaptiveOffset) {
        adaptiveOffset.addEventListener('input', (event) => {
            const value = Number(event.target.value);
            state.filter.adaptiveOffset = clamp(value, -255, 255);
            updateFilterUi();
        });
    }

    if (applyBtn) {
        applyBtn.addEventListener('click', () => {
            applyPreprocessing();
        });
        applyBtn.disabled = true;
    }

    if (saveResultBtn) {
        saveResultBtn.addEventListener('click', async () => {
            if (!state.processed || !state.processed.url) {
                setStatus('Brak wyniku do zapisania. Najpierw zastosuj filtr.');
                return;
            }
            try {
                saveResultBtn.disabled = true;
                setStatus('Zapisywanie wyniku na serwerze...');
                const blob = await ensureEntryBlob(state.processed);
                const formData = new FormData();
                formData.append('file', blob, `processed_${Date.now()}.png`);
                const metadata = buildUploadMetadata(state.processed);
                formData.append('metadata', JSON.stringify(metadata));
                const response = await fetch('/processing/save-result', {
                    method: 'POST',
                    body: formData,
                });
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }
                const data = await response.json();
                const entry = data?.entry || data;
                integrateHistoryEntry(entry);
                state.processed.persistent = true;
                state.processed.savedEntryId = entry.id;
                state.processed.meta = entry.meta || state.processed.meta;
                if (entry.stats) {
                    state.processed.stats = entry.stats;
                }
                if (state.processed.objectUrl) {
                    URL.revokeObjectURL(state.processed.objectUrl);
                }
                state.processed.objectUrl = null;
                state.processed.blob = null;
                state.processed.url = entry.url;
                if (resultImage) {
                    resultImage.src = cacheBust(entry.url);
                    applyTransform(resultImage);
                }
                setStatus('Zapisano wynik obróbki w historii.');
            } catch (error) {
                console.error('Nie udało się zapisać wyniku obróbki', error);
                setStatus('Nie można zapisać wyniku obróbki. Spróbuj ponownie.');
                saveResultBtn.disabled = false;
            } finally {
                updateProcessedButtons();
            }
        });
        saveResultBtn.disabled = true;
    }

    if (downloadBtn) {
        downloadBtn.addEventListener('click', async () => {
            if (!state.processed || !state.processed.url) {
                setStatus('Brak wyniku do pobrania. Najpierw zastosuj filtr.');
                return;
            }
            try {
                downloadBtn.disabled = true;
                const blob = await ensureEntryBlob(state.processed);
                const objectUrl = URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.href = objectUrl;
                const label = state.processed.meta?.filter || 'wynik_obrobki';
                link.download = `${label.replace(/[^a-z0-9_-]+/gi, '_')}_${Date.now()}.png`;
                document.body.append(link);
                link.click();
                link.remove();
                URL.revokeObjectURL(objectUrl);
                setStatus('Pobrano wynik obróbki.');
            } catch (error) {
                console.error('Nie udało się pobrać wyniku obróbki', error);
                setStatus('Nie można pobrać wyniku obróbki. Spróbuj ponownie.');
            } finally {
                updateProcessedButtons();
            }
        });
        downloadBtn.disabled = true;
    }

    if (sendToRetouchBtn) {
        sendToRetouchBtn.addEventListener('click', async () => {
            try {
                await transferProcessedToRetouch({ silent: false });
            } catch (error) {
                console.error('Nie udało się przekazać wyniku do retuszu', error);
                const message =
                    error?.code === 'NO_PROCESSED_RESULT'
                        ? 'Brak wyniku do przekazania. Najpierw zastosuj filtr.'
                        : error?.message || 'Nie można przekazać wyniku do retuszu. Spróbuj ponownie.';
                setStatus(message);
            }
        });
        sendToRetouchBtn.disabled = true;
    }

    if (historyList) {
        historyList.addEventListener('click', async (event) => {
            const actionTarget = event.target.closest('button[data-action]');
            if (!actionTarget) {
                return;
            }
            const { action, entryId } = actionTarget.dataset;
            if (!entryId) {
                return;
            }
            if (action === 'use') {
                const entry = findHistoryEntry(entryId);
                if (entry) {
                    setOriginal(entry);
                    setStatus(`Wybrano fragment z historii: ${entry.label}`);
                }
            } else if (action === 'remove') {
                await deleteHistoryEntry(entryId);
            }
        });
    }

    if (historyClearBtn) {
        historyClearBtn.addEventListener('click', async () => {
            await clearHistoryOnServer();
        });
    }

    if (resetBtn) {
        resetBtn.addEventListener('click', () => {
            clearResultStage();
            if (state.current) {
                setStatus('Wyczyszczono podgląd obróbki. Fragment pozostaje dostępny.');
            } else {
                setStatus('Wybierz fragment, aby rozpocząć obróbkę.');
            }
        });
        resetBtn.disabled = true;
    }

    if (zoomInBtn) {
        zoomInBtn.addEventListener('click', () => updateZoom(0.25));
    }
    if (zoomOutBtn) {
        zoomOutBtn.addEventListener('click', () => updateZoom(-0.25));
    }
    if (zoomResetBtn) {
        zoomResetBtn.addEventListener('click', () => {
            resetTransform(originalImage);
            resetTransform(resultImage);
            setStatus('Zresetowano powiększenie i przesunięcie.');
        });
    }

    const originalStage = originalImage ? originalImage.closest('.processing-stage') : null;
    const resultStage = resultImage ? resultImage.closest('.processing-stage') : null;
    wireZoomControls(originalStage);
    wireZoomControls(resultStage);
    updateZoomLabel();
    renderHistoryList();
    updateFilterUi();
    void fetchHistoryFromServer();

    return {
        handleCropSaved,
        onTabVisible() {
            if (!state.current) {
                setStatus('Wybierz fragment, aby rozpocząć obróbkę.');
            }
        },
        handleCleanup,
        resetOriginal,
        loadCurrentPagePreview,
        registerRetouchNotifier,
        transferResultToRetouch(options = {}) {
            const silent = options?.silent ?? true;
            return transferProcessedToRetouch({ silent });
        },
        getCurrentOriginal() {
            // Zwraca oryginalny obraz (bez przetwarzania) dla canvasRetouch
            if (!state.current) {
                return null;
            }
            const previewUrl = getEntryImageUrl(state.current);
            const downloadUrl = getEntryDownloadUrl(state.current);
            const effectiveUrl = previewUrl || downloadUrl || state.current.url || null;
            if (!effectiveUrl) {
                return null;
            }
            const historyId = state.current.id || null;
            return {
                id: state.current.id,
                historyId,
                url: effectiveUrl,
                objectUrl: state.current.objectUrl && state.current.objectUrl.startsWith('blob:')
                    ? state.current.objectUrl
                    : previewUrl && previewUrl.startsWith('blob:')
                        ? previewUrl
                        : state.current.objectUrl || null,
                label: state.current.label || 'Oryginalny wycinek',
                previewUrl,
                downloadUrl,
                originalUrl: state.current.url || null,
                meta: state.current.meta ? { ...state.current.meta } : undefined,
                type: state.current.type || null,
            };
        },
        ingestHistoryEntry(entry) {
            if (!entry) {
                return;
            }
            integrateHistoryEntry(entry, { setAsCurrent: false });
        },
    };
}
