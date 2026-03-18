const DEFAULT_BUFFER_ENDPOINT = '/processing/retouch-buffer';

function cacheBust(url) {
    if (!url) {
        return url;
    }
    if (!/^https?:/i.test(url)) {
        return url;
    }
    const separator = url.includes('?') ? '&' : '?';
    return `${url}${separator}t=${Date.now()}`;
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

function releaseObjectUrl(url) {
    if (typeof url === 'string' && url.startsWith('blob:')) {
        try {
            URL.revokeObjectURL(url);
        } catch (error) {
            console.warn('Nie udało się zwolnić adresu blob', error);
        }
    }
}

export function initManualRetouch(dom = {}, dependencies = {}) {
    const {
        loadBufferBtn,
        loadDiskBtn,
        loadFileInput,
        clearBtn,
        storeHistoryCheckbox,
        saveHistoryBtn,
        sourceImage,
        sourcePlaceholder,
        resultImage,
        resultPlaceholder,
        statusLabel,
        autoFilterSelect,
        applyAutoFilterBtn,
        undoBtn,
        downloadBtn,
        removeSmallControls,
        removeSmallSlider,
        removeSmallValue,
        morphOpenControls,
        morphOpenSlider,
        morphOpenValue,
        morphCloseControls,
        morphCloseSlider,
        morphCloseValue,
        medianControls,
        medianSlider,
        medianValue,
        denoiseControls,
        denoiseSlider,
        denoiseValue,
        sourceZoomInBtn,
        sourceZoomOutBtn,
        sourceZoomResetBtn,
        sourceZoomLabel,
        resultZoomInBtn,
        resultZoomOutBtn,
        resultZoomResetBtn,
        resultZoomLabel,
        sourceStage,
        resultStage,
    } = dom;

    const {
        bufferEndpoint = DEFAULT_BUFFER_ENDPOINT,
        autoCleanEndpoint = '/processing/auto-clean',
        onEntryLoaded = () => {},
        onHistorySaved = () => {},
        requestProcessingTransfer = null,
    } = dependencies;

    const state = {
        bufferEntry: null,
        pendingBufferUpdate: false,
        bufferRequestId: 0,
        isFetchingBuffer: false,
        activeSource: null,
        tabVisible: false,
        processedResult: null,
        savingHistory: false,
        zoomLevel: 1,
        pan: { x: 0, y: 0 },
        isPanning: false,
        panStart: { x: 0, y: 0 },
        pointerId: null,
    };

    function setBufferEntry(entry) {
        if (state.bufferEntry?.objectUrl && state.bufferEntry.objectUrl !== entry?.objectUrl) {
            releaseObjectUrl(state.bufferEntry.objectUrl);
        }
        state.bufferEntry = entry || null;
    }

    async function prepareBufferEntry(entry) {
        if (!entry || typeof entry !== 'object') {
            return null;
        }
        const prepared = { ...entry };
        if (typeof prepared.objectUrl === 'string' && prepared.objectUrl.startsWith('blob:')) {
            return prepared;
        }
        // Preferuj dataUrl (bezpośrednio zakodowany base64) - zawsze będzie dostępny
        const sourceUrl = prepared.dataUrl || prepared.url || prepared.serverUrl || prepared.resultUrl;
        if (!sourceUrl) {
            return prepared;
        }
        if (/^(data|blob):/i.test(sourceUrl)) {
            // jeśli dostajemy dataUrl -> będzie zawsze dostępne; logujmy rozmiar do debugu
            if (sourceUrl.startsWith('data:')) {
                try {
                    const payload = sourceUrl.split(',')[1] || '';
                    // dataUrl found in buffer (payload length available for debug)
                } catch (e) {
                    console.warn('[FETCH] Nie udało się policzyć długości dataUrl', e);
                }
            }
            prepared.objectUrl = sourceUrl;
            return prepared;
        }
        try {
            const response = await fetch(sourceUrl, { cache: 'no-store' });
            if (!response.ok) {
                const error = new Error(`HTTP ${response.status}`);
                error.code = 'BUFFER_IMAGE_FETCH_FAILED';
                error.status = response.status;
                error.url = sourceUrl;
                throw error;
            }
            const blob = await response.blob();
            prepared.objectUrl = URL.createObjectURL(blob);
        } catch (error) {
            console.error('Nie udało się pobrać materiału do retuszu', error);
            throw error;
        }
        return prepared;
    }

    function setStatus(message) {
        if (statusLabel) {
            statusLabel.textContent = message;
        }
    }

    function clearActiveSource() {
        if (state.activeSource && state.activeSource.objectUrl) {
            const sharedWithBuffer = Boolean(
                state.bufferEntry?.objectUrl && state.bufferEntry.objectUrl === state.activeSource.objectUrl,
            );
            if (!sharedWithBuffer) {
                URL.revokeObjectURL(state.activeSource.objectUrl);
            }
        }
        state.activeSource = null;
        if (sourceImage) {
            sourceImage.src = '';
        }
        toggleVisibility(sourceImage, sourcePlaceholder, false);
    }

    function clearResultPreview() {
        if (state.processedResult && state.processedResult.objectUrl) {
            URL.revokeObjectURL(state.processedResult.objectUrl);
        }
        state.processedResult = null;
        if (resultImage) {
            resultImage.src = '';
        }
        toggleVisibility(resultImage, resultPlaceholder, false);
        if (downloadBtn) {
            downloadBtn.disabled = true;
        }
        if (undoBtn) {
            undoBtn.disabled = true;
        }
        updateSaveHistoryState();
    }

    function showBufferEntry(entry) {
        setBufferEntry(entry);
        state.pendingBufferUpdate = false;
        clearActiveSource();
        if (!entry) {
            setStatus('Brak materiału do retuszu.');
            return;
        }
        const rawUrl = entry.objectUrl || entry.url || entry.serverUrl || entry.resultUrl;
        if (!rawUrl) {
            setStatus('Brak materiału do retuszu.');
            return;
        }
        const displayUrl = entry.objectUrl ? rawUrl : cacheBust(rawUrl);
        // showBufferEntry invoked (silent)
            if (sourceImage) {
            sourceImage.onload = () => {
                // sourceImage loaded successfully
                toggleVisibility(sourceImage, sourcePlaceholder, true);
                sourceImage.onload = null;
                sourceImage.onerror = null;
            };
            sourceImage.onerror = async (ev) => {
                console.error('[RETOUCH] sourceImage onerror — nie udało się wczytać obrazka. src=', sourceImage.src, ' event=', ev);
                // Jeśli to był data: URL, spróbuj fallbacku: skonwertuj base64 -> blob -> objectURL i podmień src
                try {
                    const currentSrc = sourceImage.src || '';
                    if (currentSrc.startsWith('data:') && !sourceImage._triedDataFallback) {
                        sourceImage._triedDataFallback = true;
                        // Attempting fallback: decode dataURL -> blob and set object URL
                        const comma = currentSrc.indexOf(',');
                        const base64 = comma >= 0 ? currentSrc.slice(comma + 1) : currentSrc;
                        const bytes = atob(base64);
                        const len = bytes.length;
                        const arr = new Uint8Array(len);
                        for (let i = 0; i < len; i++) {
                            arr[i] = bytes.charCodeAt(i);
                        }
                        const blob = new Blob([arr], { type: 'image/png' });
                        const objUrl = URL.createObjectURL(blob);
                        // Created fallback object URL from dataURL
                        sourceImage.src = objUrl;
                        // Nie usuwamy revoke; on success we'll clear handlers
                        return;
                    }
                } catch (x) {
                    console.warn('[RETOUCH] Fallback dataURL -> blob nie powiódł się', x);
                }

                toggleVisibility(sourceImage, sourcePlaceholder, false);
                setStatus('Nie udało się wczytać materiału do retuszu.');
                sourceImage.onload = null;
                sourceImage.onerror = null;
            };
            sourceImage.src = displayUrl;
        }
        state.activeSource = { mode: 'buffer' };
        if (displayUrl.startsWith('blob:')) {
            state.activeSource.objectUrl = displayUrl;
        } else {
            state.activeSource.url = displayUrl;
        }
        setStatus('Wczytano materiał do retuszu.');
        onEntryLoaded(entry);
    }

    async function fetchBufferEntry() {
        const requestId = ++state.bufferRequestId;
        try {
            console.log('[FETCH] Wysyłam GET na', bufferEndpoint);
            setStatus('Sprawdzanie bufora retuszu...');
            const response = await fetch(bufferEndpoint, {
                method: 'GET',
                headers: {
                    Accept: 'application/json',
                    'Cache-Control': 'no-cache',
                },
                cache: 'no-store',
            });
            console.log('[FETCH] Odpowiedź statusu:', response.status, response.statusText);
            if (requestId !== state.bufferRequestId) {
                console.log('[FETCH] Prośba anulowana (inny requestId)');
                return null;
            }
            if (response.status === 404) {
                console.log('[FETCH] 404 - brak bufora');
                state.bufferEntry = null;
                state.pendingBufferUpdate = false;
                clearActiveSource();
                setStatus('Brak materiału do retuszu. Zastosuj obróbkę i wyślij ponownie.');
                return null;
            }
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const payload = await response.json();
            console.log('[FETCH] JSON payload:', payload);
            if (requestId !== state.bufferRequestId) {
                console.log('[FETCH] Prośba anulowana po pobraniu JSON');
                return null;
            }
            const entry = payload?.entry || payload;
            console.log('[FETCH] Przygotowuję entry:', entry);
            try {
                const prepared = (await prepareBufferEntry(entry)) || entry;
                console.log('[FETCH] Przygotowywanie powiodło się:', prepared);
                showBufferEntry(prepared);
                return prepared;
            } catch (prepareError) {
                console.error('[FETCH] Błąd przygotowania:', prepareError);
                if (prepareError?.code === 'BUFFER_IMAGE_FETCH_FAILED' && prepareError?.status === 404) {
                    console.warn('[FETCH] Plik z bufora nie istnieje (404), czyszczę bufor.');
                    // Wymuś usunięcie błędnego wpisu z serwera
                    await fetch(bufferEndpoint, { method: 'DELETE' }).catch(() => {});
                    state.bufferEntry = null;
                    state.pendingBufferUpdate = false;
                    clearActiveSource();
                    return null; // Zwróć null, aby loadBufferWithFallback przeszedł do transferu
                }
                throw prepareError;
            }
        } catch (error) {
            console.error('[FETCH] Błąd:', error);
            if (requestId !== state.bufferRequestId) {
                return null;
            }
            if (error?.code === 'BUFFER_IMAGE_FETCH_FAILED') {
                setBufferEntry(null);
                state.pendingBufferUpdate = false;
                if (error?.status === 404) {
                    setStatus('Plik w buforze nie istnieje. Pobieram najnowszy wynik z binaryzacji...');
                } else {
                    setStatus('Nie udało się pobrać materiału z bufora. Spróbuj ponownie.');
                }
            } else {
                setStatus('Nie można pobrać materiału do retuszu. Spróbuj ponownie.');
            }
            return null;
        }
    }

    async function loadBufferWithFallback() {
        const entry = await fetchBufferEntry();
        if (entry) {
            return entry;
        }
        if (typeof requestProcessingTransfer !== 'function') {
            return null;
        }
        try {
            setStatus('Brak materiału w buforze. Pobieram wynik z zakładki „Binaryzacja”...');
            const transferred = await requestProcessingTransfer();
            if (transferred) {
                await handleBufferUpdate(transferred);
                setStatus('Załadowano najnowszy wynik z binaryzacji.');
                return transferred;
            }
            setStatus('Brak świeżego wyniku z binaryzacji. Użyj przycisku „Prześlij do retuszu”.');
        } catch (error) {
            console.error('Nie udało się zsynchronizować wyniku z binaryzacji', error);
            const message =
                error?.code === 'NO_PROCESSED_RESULT'
                    ? 'Brak aktywnego wyniku z binaryzacji. Zastosuj filtr i prześlij do retuszu.'
                    : error?.message || 'Nie udało się pobrać wyniku z binaryzacji.';
            setStatus(message);
        }
        return null;
    }

    async function handleBufferUpdate(entry) {
        const requestId = ++state.bufferRequestId;
        try {
            const prepared = entry ? (await prepareBufferEntry(entry)) || entry : null;
            if (requestId !== state.bufferRequestId) {
                if (prepared?.objectUrl && prepared.objectUrl !== entry?.objectUrl) {
                    releaseObjectUrl(prepared.objectUrl);
                }
                return;
            }
            if (!prepared) {
                state.pendingBufferUpdate = false;
                setBufferEntry(null);
                if (state.tabVisible) {
                    clearActiveSource();
                    clearResultPreview();
                }
                setStatus('Bufor retuszu został wyczyszczony.');
                return;
            }
            if (state.tabVisible) {
                showBufferEntry(prepared);
            } else {
                setBufferEntry(prepared);
                state.pendingBufferUpdate = true;
                setStatus('Nowy materiał do retuszu jest gotowy. Przejdź na zakładkę retuszu.');
            }
        } catch (error) {
            console.error('Nie udało się zaktualizować bufora retuszu', error);
            if (requestId !== state.bufferRequestId) {
                return;
            }
            setStatus('Nie udało się pobrać materiału do retuszu. Spróbuj ponownie.');
        }
    }

    async function handleLocalFile(file) {
        if (!file) {
            return;
        }
        clearActiveSource();
        const objectUrl = URL.createObjectURL(file);
        state.activeSource = { mode: 'local', objectUrl };
        if (sourceImage) {
            sourceImage.src = objectUrl;
        }
        toggleVisibility(sourceImage, sourcePlaceholder, true);
        setStatus(`Wczytano plik z dysku: ${file.name}.`);
        onEntryLoaded({
            id: null,
            url: objectUrl,
            label: file.name,
            type: 'local-upload',
        });

        // Sprawdź, czy użytkownik chce zapisywać kopię na serwerze
        const autoSave = (() => {
            try {
                const v = localStorage.getItem('autoSaveOnLoad');
                return v === null ? true : v === 'true';
            } catch (err) {
                return true;
            }
        })();

        if (!autoSave) {
            setStatus('ℹ️ Wczytano lokalnie (kopia na serwerze wyłączona w ustawieniach).');
            return;
        }

        // Spróbuj zachować kopię na serwerze (folder uploads) tak aby dalsze operacje nadpisania
        // były wykonywane na tej samej wersji. Działamy w tle i informujemy o sukcesie/porażce.
        try {
            const form = new FormData();
            form.append('file', file);
            setStatus('💾 Zapisuję kopię pliku na serwerze...');
            const resp = await fetch('/processing/import', { method: 'POST', body: form });
            if (!resp.ok) {
                throw new Error(`HTTP ${resp.status}`);
            }
            const payload = await resp.json();
            const entry = payload?.entry || payload;
            if (entry && entry.url) {
                // Zachowaj URL serwerowy dla aktywnego źródła
                state.activeSource.serverUrl = entry.url;
                state.activeSource.serverFilename = entry.payload?.filename || entry.storage?.filename || null;
                setStatus(`✅ Zapisano kopię na serwerze: ${state.activeSource.serverFilename || entry.url}`);
            } else {
                setStatus('⚠ Plik wczytany lokalnie, ale nie udało się zapisać kopii na serwerze.');
            }
        } catch (err) {
            console.warn('Nie udało się zapisać lokalnego pliku na serwerze', err);
            setStatus('⚠ Wczytano lokalnie, ale nie zapisano kopii na serwerze.');
        }
    }

    function resetRetouchView() {
        clearActiveSource();
        clearResultPreview();
        setBufferEntry(null);
        state.pendingBufferUpdate = false;
        setStatus('Wczytaj materiał do retuszu.');
        hideAllFilterControls();
        if (autoFilterSelect) {
            autoFilterSelect.value = '';
        }
        // Reset zoom i pan
        resetTransform(sourceImage);
        resetTransform(resultImage);
        updateSaveHistoryState();
    }

    function hideAllFilterControls() {
        const controls = [
            removeSmallControls,
            morphOpenControls,
            morphCloseControls,
            medianControls,
            denoiseControls,
        ];
        controls.forEach(ctrl => {
            if (ctrl) {
                ctrl.classList.add('hidden');
            }
        });
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

    function sanitizeHistoryEntry(entry) {
        return JSON.parse(
            JSON.stringify(entry, (key, value) => {
                if (key === 'objectUrl') {
                    return undefined;
                }
                return value;
            }),
        );
    }

    function updateSaveHistoryState() {
        if (!saveHistoryBtn) {
            return;
        }
        const hasResult = Boolean(state.processedResult && state.processedResult.objectUrl);
        const alreadySaved = Boolean(state.processedResult && state.processedResult.savedEntryId);
        const checkboxChecked = Boolean(storeHistoryCheckbox && storeHistoryCheckbox.checked);
        const canSave = hasResult && checkboxChecked && !state.savingHistory && !alreadySaved;
        saveHistoryBtn.disabled = !canSave;
        if (alreadySaved) {
            saveHistoryBtn.textContent = 'Zapisano';
            saveHistoryBtn.classList.add('btn-success');
            saveHistoryBtn.classList.remove('btn-outline-success');
        } else {
            saveHistoryBtn.textContent = 'Zapisz wynik';
            saveHistoryBtn.classList.add('btn-outline-success');
            saveHistoryBtn.classList.remove('btn-success');
        }
    }

    function buildHistoryEntry(createdAtIso) {
        if (!state.processedResult || !state.processedResult.serverUrl) {
            return null;
        }
        const createdAt = createdAtIso || new Date().toISOString();
        const createdDate = new Date(createdAt);
        const humanTime = Number.isNaN(createdDate.getTime()) ? createdAt : createdDate.toLocaleString();
        const filterLabel = state.processedResult.filterLabel || 'Wynik retuszu';
        const filterType = state.processedResult.filterType || null;
        const params = state.processedResult.params || null;
        const entryId = `retouch-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
        const relative = extractUploadFilename(state.processedResult.serverUrl);

        const meta = {
            createdAt,
            typeLabel: 'Wynik retuszu',
        };
        if (filterLabel) {
            meta.filterLabel = filterLabel;
        }
        if (filterType) {
            meta.filter = filterType;
        }
        if (params) {
            meta.params = params;
        }
        if (state.activeSource?.mode) {
            meta.sourceMode = state.activeSource.mode;
        }
        if (state.bufferEntry?.meta?.sourcePage) {
            meta.sourcePage = state.bufferEntry.meta.sourcePage;
        }

        const payload = {};
        if (filterType) {
            payload.filter = filterType;
        }
        if (params) {
            payload.params = params;
        }
        if (state.processedResult.serverUrl) {
            payload.serverUrl = state.processedResult.serverUrl;
        }
        const sourceSummary = {};
        if (state.activeSource?.mode) {
            sourceSummary.mode = state.activeSource.mode;
        }
        if (state.bufferEntry?.label) {
            sourceSummary.label = state.bufferEntry.label;
        } else if (state.activeSource?.label) {
            sourceSummary.label = state.activeSource.label;
        }
        if (state.bufferEntry?.id) {
            sourceSummary.bufferEntryId = state.bufferEntry.id;
        }
        if (state.bufferEntry?.meta?.sourcePage) {
            sourceSummary.sourcePage = state.bufferEntry.meta.sourcePage;
        }
        if (Object.keys(sourceSummary).length > 0) {
            payload.source = sourceSummary;
        }

        const entry = {
            id: entryId,
            url: state.processedResult.serverUrl,
            label: `${filterLabel} (${humanTime})`,
            type: 'retouch',
            meta,
            payload,
        };

        if (relative) {
            entry.storage = {
                type: 'retouch',
                filename: relative,
            };
        }

        return entry;
    }

    function showFilterControls(filterType) {
        hideAllFilterControls();
        if (filterType === 'remove-small' && removeSmallControls) {
            removeSmallControls.classList.remove('hidden');
        } else if (filterType === 'morphology-open' && morphOpenControls) {
            morphOpenControls.classList.remove('hidden');
        } else if (filterType === 'morphology-close' && morphCloseControls) {
            morphCloseControls.classList.remove('hidden');
        } else if (filterType === 'median' && medianControls) {
            medianControls.classList.remove('hidden');
        } else if (filterType === 'denoise' && denoiseControls) {
            denoiseControls.classList.remove('hidden');
        }
    }

    function getFilterParams(filterType) {
        const params = {};
        if (filterType === 'remove-small' && removeSmallSlider) {
            params.minSize = parseInt(removeSmallSlider.value);
        } else if (filterType === 'morphology-open' && morphOpenSlider) {
            params.kernelSize = parseInt(morphOpenSlider.value);
        } else if (filterType === 'morphology-close' && morphCloseSlider) {
            params.kernelSize = parseInt(morphCloseSlider.value);
        } else if (filterType === 'median' && medianSlider) {
            params.kernelSize = parseInt(medianSlider.value);
        } else if (filterType === 'denoise' && denoiseSlider) {
            params.h = parseInt(denoiseSlider.value);
        }
        return params;
    }

    // Funkcje zoom i pan (przesuwania)
    function updateZoomLabel() {
        if (sourceZoomLabel) {
            sourceZoomLabel.textContent = `${Math.round(state.zoomLevel * 100)}%`;
        }
        if (resultZoomLabel) {
            resultZoomLabel.textContent = `${Math.round(state.zoomLevel * 100)}%`;
        }
        if (sourceZoomOutBtn) {
            sourceZoomOutBtn.disabled = state.zoomLevel <= 0.25;
        }
        if (resultZoomOutBtn) {
            resultZoomOutBtn.disabled = state.zoomLevel <= 0.25;
        }
        if (sourceZoomInBtn) {
            sourceZoomInBtn.disabled = state.zoomLevel >= 4;
        }
        if (resultZoomInBtn) {
            resultZoomInBtn.disabled = state.zoomLevel >= 4;
        }
        if (sourceZoomResetBtn) {
            sourceZoomResetBtn.disabled = state.zoomLevel === 1 && state.pan.x === 0 && state.pan.y === 0;
        }
        if (resultZoomResetBtn) {
            resultZoomResetBtn.disabled = state.zoomLevel === 1 && state.pan.x === 0 && state.pan.y === 0;
        }
    }

    function applyTransform(target) {
        if (!target) return;
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

        applyTransform(sourceImage);
        applyTransform(resultImage);
        updateZoomLabel();
    }

    function handlePointerDown(event, target) {
        if (!target) return;
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
        applyTransform(sourceImage);
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

    function wireZoomControls(stageEl) {
        if (!stageEl) return;
        stageEl.classList.add('zoomable');
        stageEl.addEventListener('pointerdown', (event) => handlePointerDown(event, stageEl));
        stageEl.addEventListener('pointermove', (event) => handlePointerMove(event, stageEl));
        stageEl.addEventListener('pointerup', (event) => handlePointerUp(event, stageEl));
        stageEl.addEventListener('pointercancel', (event) => handlePointerUp(event, stageEl));
        // Scroll wheel intentionally left to default page scrolling; zoom obsługiwany klawiszami/UI.
        stageEl.addEventListener('contextmenu', (event) => event.preventDefault());
    }

    async function applyAutoFilter() {
        if (!state.activeSource) {
            alert('Najpierw wczytaj fragment do retuszu!');
            return;
        }
        const filterType = autoFilterSelect?.value;
        if (!filterType) {
            alert('Wybierz filtr z listy!');
            return;
        }

        try {
            setStatus('Wykonywanie automatycznego czyszczenia...');
            if (applyAutoFilterBtn) {
                applyAutoFilterBtn.disabled = true;
            }

            // Konwersja obrazu na base64
            const canvas = document.createElement('canvas');
            const ctx = canvas.getContext('2d');
            const img = sourceImage;
            canvas.width = img.naturalWidth;
            canvas.height = img.naturalHeight;
            ctx.drawImage(img, 0, 0);
            const imageData = canvas.toDataURL('image/png');

            // Pobierz parametry z suwaków
            const params = getFilterParams(filterType);

            const response = await fetch(autoCleanEndpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filterType, imageData, params }),
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const result = await response.json();
            if (!result.resultUrl) {
                throw new Error('Brak URL wyniku w odpowiedzi');
            }
            const filterLabel = autoFilterSelect?.options?.[autoFilterSelect.selectedIndex]?.text?.trim() || filterType;

            // Pobierz wynik i utwórz lokalny blob URL
            const imgResponse = await fetch(cacheBust(result.resultUrl));
            if (!imgResponse.ok) {
                throw new Error('Nie można pobrać wyniku');
            }
            const blob = await imgResponse.blob();
            const objectUrl = URL.createObjectURL(blob);

            clearResultPreview();
            state.processedResult = {
                objectUrl,
                serverUrl: result.resultUrl,
                filterType,
                filterLabel,
                params,
                createdAt: new Date().toISOString(),
                savedEntryId: null,
            };
            if (resultImage) {
                resultImage.src = objectUrl;
            }
            toggleVisibility(resultImage, resultPlaceholder, true);
            if (downloadBtn) {
                downloadBtn.disabled = false;
            }
            if (undoBtn) {
                undoBtn.disabled = false;
            }
            setStatus(`Filtr "${filterLabel}" zastosowany pomyślnie.`);
            updateSaveHistoryState();
        } catch (error) {
            console.error('Błąd podczas automatycznego czyszczenia:', error);
            setStatus('Nie udało się zastosować automatycznego czyszczenia.');
            alert('Nie udało się zastosować filtra. Sprawdź konsolę deweloperską.');
        } finally {
            if (applyAutoFilterBtn) {
                applyAutoFilterBtn.disabled = false;
            }
        }
    }

    function handleDownload() {
        if (!state.processedResult || !state.processedResult.objectUrl) {
            alert('Brak wyniku do pobrania!');
            return;
        }
        const a = document.createElement('a');
        a.href = state.processedResult.objectUrl;
        a.download = `retusz-${Date.now()}.png`;
        a.click();
    }

    function handleUndo() {
        if (!state.activeSource) {
            alert('Brak oryginału do przywrócenia!');
            return;
        }
        // Wyczyść wynik, ale zachowaj oryginalny fragment
        clearResultPreview();
        setStatus('Przywrócono oryginalny fragment. Wybierz inny filtr lub zastosuj ponownie.');
        updateSaveHistoryState();
    }

    if (loadBufferBtn) {
        loadBufferBtn.addEventListener('click', async () => {
            // Najpierw spróbuj bezpośredniego transferu z zakładki Binaryzacja (jeśli dostępny)
            if (typeof requestProcessingTransfer === 'function') {
                try {
                    setStatus('Pobieram najnowszy wynik z zakładki „Binaryzacja"...');
                    const transferred = await requestProcessingTransfer();
                    if (transferred) {
                        await handleBufferUpdate(transferred);
                        setStatus('Załadowano najnowszy wynik z binaryzacji.');
                        return;
                    }
                } catch (err) {
                    console.warn('[RETOUCH] Bezpośredni transfer nie powiódł się, spróbuję bufora:', err);
                    // kontynuuj do fallbacku
                }
            }

            // Fallback: spróbuj załadować istniejący wpis w buforze, lub wymusić transfer
            await loadBufferWithFallback();
        });
    }

    if (loadDiskBtn && loadFileInput) {
        loadDiskBtn.addEventListener('click', () => {
            loadFileInput.click();
        });
        loadFileInput.addEventListener('change', (event) => {
            const file = event?.target?.files?.[0];
            if (loadFileInput) {
                loadFileInput.value = '';
            }
            if (!file) {
                return;
            }
            handleLocalFile(file);
        });
    }

    if (clearBtn) {
        clearBtn.addEventListener('click', async () => {
            resetRetouchView();
            try {
                await fetch(bufferEndpoint, { method: 'DELETE' });
            } catch (error) {
                console.warn('Nie udało się wyczyścić bufora retuszu', error);
            }
        });
    }

    if (applyAutoFilterBtn) {
        applyAutoFilterBtn.addEventListener('click', () => {
            void applyAutoFilter();
        });
    }

    if (undoBtn) {
        undoBtn.addEventListener('click', handleUndo);
    }

    if (downloadBtn) {
        downloadBtn.addEventListener('click', handleDownload);
    }

    async function saveResultToHistory() {
        if (!state.processedResult || !state.processedResult.serverUrl) {
            alert('Brak wyniku do zapisania w historii.');
            return;
        }
        const entry = buildHistoryEntry(state.processedResult.createdAt || new Date().toISOString());
        if (!entry) {
            alert('Nie udało się przygotować wpisu historii.');
            return;
        }
        try {
            state.savingHistory = true;
            updateSaveHistoryState();
            const response = await fetch('/processing/history', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(sanitizeHistoryEntry(entry)),
            });
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const payload = await response.json();
            const savedEntry = payload?.entry || payload;
            state.processedResult.savedEntryId = savedEntry?.id || entry.id;
            setStatus('Wynik retuszu zapisany w historii.');
            if (typeof onHistorySaved === 'function') {
                try {
                    onHistorySaved(savedEntry || entry);
                } catch (notifyError) {
                    console.warn('Nie udało się powiadomić o nowym wpisie historii retuszu', notifyError);
                }
            }
        } catch (error) {
            console.error('Nie udało się zapisać retuszu w historii', error);
            setStatus('Nie można zapisać wyniku retuszu w historii.');
            alert('Zapis do historii nie powiódł się. Sprawdź logi serwera.');
        } finally {
            state.savingHistory = false;
            updateSaveHistoryState();
        }
    }

    if (saveHistoryBtn) {
        saveHistoryBtn.addEventListener('click', () => {
            void saveResultToHistory();
        });
    }

    if (storeHistoryCheckbox) {
        storeHistoryCheckbox.addEventListener('change', () => {
            updateSaveHistoryState();
        });
    }

    // Dynamiczne pokazywanie kontrolek przy zmianie filtra
    if (autoFilterSelect) {
        autoFilterSelect.addEventListener('change', (e) => {
            showFilterControls(e.target.value);
        });
    }

    // Aktualizacja wartości przy przesuwaniu suwaków
    if (removeSmallSlider && removeSmallValue) {
        removeSmallSlider.addEventListener('input', (e) => {
            removeSmallValue.textContent = `${e.target.value} px`;
        });
    }
    if (morphOpenSlider && morphOpenValue) {
        morphOpenSlider.addEventListener('input', (e) => {
            morphOpenValue.textContent = `${e.target.value} px`;
        });
    }
    if (morphCloseSlider && morphCloseValue) {
        morphCloseSlider.addEventListener('input', (e) => {
            morphCloseValue.textContent = `${e.target.value} px`;
        });
    }
    if (medianSlider && medianValue) {
        medianSlider.addEventListener('input', (e) => {
            medianValue.textContent = `${e.target.value} px`;
        });
    }
    if (denoiseSlider && denoiseValue) {
        denoiseSlider.addEventListener('input', (e) => {
            denoiseValue.textContent = e.target.value;
        });
    }

    // Event listenery dla przycisków zoom
    if (sourceZoomInBtn) {
        sourceZoomInBtn.addEventListener('click', () => updateZoom(0.1));
    }
    if (sourceZoomOutBtn) {
        sourceZoomOutBtn.addEventListener('click', () => updateZoom(-0.1));
    }
    if (sourceZoomResetBtn) {
        sourceZoomResetBtn.addEventListener('click', () => {
            resetTransform(sourceImage);
            resetTransform(resultImage);
        });
    }
    if (resultZoomInBtn) {
        resultZoomInBtn.addEventListener('click', () => updateZoom(0.1));
    }
    if (resultZoomOutBtn) {
        resultZoomOutBtn.addEventListener('click', () => updateZoom(-0.1));
    }
    if (resultZoomResetBtn) {
        resultZoomResetBtn.addEventListener('click', () => {
            resetTransform(sourceImage);
            resetTransform(resultImage);
        });
    }

    // Podłącz funkcje zoom i pan do stage'ów
    wireZoomControls(sourceStage);
    wireZoomControls(resultStage);

    resetRetouchView();
    updateSaveHistoryState();

    return {
        handleBufferUpdate,
        getProcessedResult() {
            return state.processedResult;
        },
        onTabVisible() {
            state.tabVisible = true;
            if (state.pendingBufferUpdate) {
                if (state.bufferEntry) {
                    showBufferEntry(state.bufferEntry);
                    return;
                }
            }
            if (!state.activeSource) {
                void loadBufferWithFallback();
            }
        },
        onTabHidden() {
            state.tabVisible = false;
        },
    };
}
