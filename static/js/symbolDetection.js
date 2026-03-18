const DETECTORS_ENDPOINT = '/api/symbols/detectors';
const DETECT_ENDPOINT = '/api/symbols/detect';
const MAX_PREVIEW_WIDTH = 1280;
const MAX_PREVIEW_HEIGHT = 820;
const PREVIEW_MIN_SCALE = 0.1;
const PREVIEW_MAX_SCALE = 6;
const PREVIEW_ZOOM_STEP = 0.12;

import { formatTimestamp, parseTimestamp } from './utils/timestamp.js';

function createElement(tag, text) {
    const element = document.createElement(tag);
    if (typeof text === 'string') {
        element.textContent = text;
    }
    return element;
}

function cacheBust(url) {
    if (typeof url !== 'string' || !url) {
        return url;
    }
    if (/^(data|blob):/i.test(url)) {
        return url;
    }
    const token = `_=${Date.now()}`;
    if (url.includes('?')) {
        return `${url}&${token}`;
    }
    return `${url}?${token}`;
}

function formatFloat(value, digits = 2) {
    if (Number.isNaN(value) || !Number.isFinite(value)) {
        return '--';
    }
    const factor = Math.pow(10, digits);
    return String(Math.round(value * factor) / factor);
}

function normalizeBox(detection) {
    if (!detection) {
        return [0, 0, 0, 0];
    }
    if (Array.isArray(detection.bbox)) {
        return detection.bbox.map((entry) => Number(entry) || 0);
    }
    if (detection.box && typeof detection.box === 'object') {
        const { x = 0, y = 0, width = 0, height = 0 } = detection.box;
        return [Number(x) || 0, Number(y) || 0, Number(width) || 0, Number(height) || 0];
    }
    return [0, 0, 0, 0];
}

export function initSymbolDetection(dom = {}, dependencies = {}) {
    const {
        statusLabel,
        detectorSelect,
        refreshBtn,
        storeHistoryCheckbox,
        usePdfBtn,
        pdfInfo,
        pdfThumbnail,
        pdfThumbPlaceholder,
        segmentationInfo,
        segmentationDetectBtn,
        segThumbnail,
        segThumbPlaceholder,
        fileInput,
        fileDetectBtn,
        fileNameLabel,
        fileThumbnail,
        fileThumbPlaceholder,
        previewCanvas,
        previewFrame,
        previewSourceLabel,
        previewOverlayToggle,
        confidenceSlider,
        confidenceValue,
        resultCount,
        resultDetector,
        resultLatency,
        resultSummary,
        resultTableBody,
        rawOutputPre,
        historyLink,
        historyList,
        historyEmpty,
        historyRefreshBtn,
    } = dom;

    const {
        getPdfContext = null,
        getSegmentationContext = null,
        ensureSegmentationSource = null,
    } = dependencies;

    const historyObservers = new Set();

    const state = {
        detectors: [],
        selectedDetector: null,
        loading: false,
        pdfContext: null,
        segmentationContext: null,
        pendingFile: null,
        pendingFileName: '',
        lastSource: null,
        allDetections: [],
        visibleDetections: [],
        previewImage: null,
        previewDetections: [],
        previewSourceDescriptor: null,
        previewScale: 1,
        previewFitScale: 1,
        showDetections: true,
        isPanning: false,
        panStartX: 0,
        panStartY: 0,
        scrollStartX: 0,
        scrollStartY: 0,
        activeDetectionIndex: null,
        confidenceThreshold: 0,
        historyEntries: [],
        historyLoading: false,
    };

    function setStatus(message, tone = 'muted') {
        if (!statusLabel) {
            return;
        }
        statusLabel.textContent = message || '';
        const base = 'form-text';
        let toneClass = 'text-muted';
        if (tone === 'error') {
            toneClass = 'text-danger';
        } else if (tone === 'success') {
            toneClass = 'text-success';
        } else if (tone === 'info') {
            toneClass = 'text-primary';
        }
        statusLabel.className = `${base} ${toneClass}`;
    }

    function setSegmentationInfo(message, tone = 'muted') {
        if (!segmentationInfo) {
            return;
        }
        const base = 'small mb-3';
        let toneClass = 'text-muted';
        if (tone === 'success') {
            toneClass = 'text-success';
        } else if (tone === 'warning') {
            toneClass = 'text-warning';
        } else if (tone === 'error' || tone === 'danger') {
            toneClass = 'text-danger';
        } else if (tone === 'info') {
            toneClass = 'text-primary';
        }
        segmentationInfo.className = `${base} ${toneClass}`;
        segmentationInfo.textContent = message || '';
    }

    // Use shared formatTimestamp util (imported at top of module)

    function resolveHistoryPreviewUrl(entry) {
        if (!entry || typeof entry !== 'object') {
            return null;
        }
        const candidates = [
            entry.previewUrl,
            entry.preview_url,
            entry.meta && (entry.meta.previewUrl || entry.meta.preview_url),
            entry.payload && (entry.payload.previewUrl || entry.payload.preview_url),
        ];
        for (const candidate of candidates) {
            if (typeof candidate === 'string' && candidate) {
                return candidate;
            }
        }
        if (entry.payload && entry.payload.source && typeof entry.payload.source === 'object') {
            const sourcePreview = entry.payload.source.imageUrl
                || entry.payload.source.image_url
                || entry.payload.source.url;
            if (typeof sourcePreview === 'string' && sourcePreview) {
                return sourcePreview;
            }
        }
        return null;
    }

    function getHistoryPreviewUrl(entry) {
        const preview = resolveHistoryPreviewUrl(entry);
        if (typeof preview === 'string' && preview && !preview.startsWith('data:')) {
            return cacheBust(preview);
        }
        return preview;
    }

    function getHistoryDetectorLabel(entry) {
        const metaDetector = entry?.meta?.detector;
        if (typeof metaDetector === 'string' && metaDetector) {
            return metaDetector;
        }
        const payloadDetector = entry?.payload?.detector;
        if (payloadDetector && typeof payloadDetector === 'object') {
            const { name, version } = payloadDetector;
            if (name) {
                return version ? `${name} v${version}` : name;
            }
        }
        return null;
    }

    function getHistoryDetectionCount(entry) {
        const metaCount = entry?.meta?.detections;
        if (Number.isFinite(metaCount)) {
            return metaCount;
        }
        const payloadCount = entry?.payload?.count;
        if (Number.isFinite(payloadCount)) {
            return payloadCount;
        }
        const detections = entry?.payload?.detections;
        if (Array.isArray(detections)) {
            return detections.length;
        }
        return null;
    }

    function describeHistorySource(entry) {
        if (entry?.meta?.sourceLabel) {
            return entry.meta.sourceLabel;
        }
        if (entry?.payload?.source && typeof entry.payload.source === 'object') {
            const src = entry.payload.source;
            if (typeof src.label === 'string' && src.label) {
                return src.label;
            }
            if (typeof src.filename === 'string' && src.filename) {
                return src.filename;
            }
            if (typeof src.source === 'string' && src.source) {
                return src.source;
            }
        }
        if (typeof entry?.label === 'string' && entry.label) {
            return entry.label;
        }
        return 'Źródło nieznane';
    }

    function setHistoryLoading(flag) {
        state.historyLoading = flag;
        if (historyRefreshBtn) {
            historyRefreshBtn.disabled = flag;
        }
    }

    function renderHistoryEntries() {
        if (!historyList || !historyEmpty) {
            return;
        }
        historyList.innerHTML = '';
        const entries = [...state.historyEntries].sort((a, b) => {
            const timeA = new Date(a?.meta?.createdAt || 0).getTime();
            const timeB = new Date(b?.meta?.createdAt || 0).getTime();
            return timeB - timeA;
        });
        if (!entries.length) {
            historyEmpty.classList.remove('hidden');
            historyList.classList.add('hidden');
            return;
        }
        historyEmpty.classList.add('hidden');
        historyList.classList.remove('hidden');
        const fragment = document.createDocumentFragment();
        entries.forEach((entry) => {
            const item = document.createElement('li');
            item.className = 'symbol-history-card';

            const title = document.createElement('h4');
            title.textContent = describeHistorySource(entry);
            item.appendChild(title);

            const thumb = document.createElement('div');
            thumb.className = 'symbol-history-thumb';
            const previewUrl = getHistoryPreviewUrl(entry);
            if (previewUrl) {
                const img = document.createElement('img');
                img.src = previewUrl;
                img.alt = entry.label || 'Podgląd detekcji';
                img.loading = 'lazy';
                thumb.appendChild(img);
            } else {
                const placeholder = document.createElement('p');
                placeholder.className = 'symbol-thumb-placeholder mb-0';
                placeholder.textContent = 'Podgląd niedostępny.';
                thumb.appendChild(placeholder);
            }
            item.appendChild(thumb);

            const metaWrap = document.createElement('div');
            metaWrap.className = 'symbol-history-meta';

            const detectorLabel = getHistoryDetectorLabel(entry);
            const count = getHistoryDetectionCount(entry);
            const createdAt = formatTimestamp(entry?.meta?.createdAt);

            const detectorLine = document.createElement('p');
            detectorLine.textContent = `Detektor: ${detectorLabel || '—'}`;
            metaWrap.appendChild(detectorLine);

            const countLine = document.createElement('p');
            countLine.textContent = Number.isFinite(count) ? `Wykryto: ${count} symboli` : 'Liczba detekcji: —';
            metaWrap.appendChild(countLine);

            const timeLine = document.createElement('p');
            timeLine.textContent = `Dodano: ${createdAt}`;
            metaWrap.appendChild(timeLine);

            item.appendChild(metaWrap);

            const actions = document.createElement('div');
            actions.className = 'symbol-history-actions';

            const sourceLabel = document.createElement('span');
            sourceLabel.className = 'symbol-history-source';
            sourceLabel.textContent = entry?.meta?.sourceLabel || 'Fragment: nieznany';
            actions.appendChild(sourceLabel);

            const buttonsWrap = document.createElement('div');
            buttonsWrap.className = 'd-flex gap-2';

            if (previewUrl) {
                const previewBtn = document.createElement('a');
                previewBtn.className = 'btn btn-outline-primary btn-sm';
                previewBtn.href = previewUrl;
                previewBtn.target = '_blank';
                previewBtn.rel = 'noopener noreferrer';
                previewBtn.textContent = 'Podgląd';
                buttonsWrap.appendChild(previewBtn);
            }

            if (entry?.url) {
                const detailsBtn = document.createElement('a');
                detailsBtn.className = 'btn btn-outline-secondary btn-sm';
                detailsBtn.href = entry.url;
                detailsBtn.target = '_blank';
                detailsBtn.rel = 'noopener noreferrer';
                detailsBtn.textContent = 'Szczegóły';
                buttonsWrap.appendChild(detailsBtn);
            }

            if (buttonsWrap.childElementCount > 0) {
                actions.appendChild(buttonsWrap);
            }

            item.appendChild(actions);

            fragment.appendChild(item);
        });
        historyList.appendChild(fragment);
    }

    function setHistoryEntries(entries) {
        state.historyEntries = Array.isArray(entries) ? entries.slice() : [];
        renderHistoryEntries();
    }

    function upsertHistoryEntry(entry) {
        if (!entry || !entry.id) {
            return;
        }
        const index = state.historyEntries.findIndex((item) => item.id === entry.id);
        if (index === -1) {
            state.historyEntries.push(entry);
        } else {
            state.historyEntries[index] = entry;
        }
        renderHistoryEntries();
    }

    async function fetchDetectionHistory({ silent = false } = {}) {
        if (state.historyLoading) {
            return;
        }
        setHistoryLoading(true);
        try {
            const response = await fetch('/processing/history?scope=symbol-detection', {
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
            setHistoryEntries(entries);
        } catch (error) {
            console.error('Nie udało się pobrać historii detekcji symboli', error);
            if (!silent) {
                setStatus('Nie udało się pobrać historii detekcji.', 'error');
            }
        } finally {
            setHistoryLoading(false);
        }
    }

    function cloneSegmentationContext(context) {
        if (!context) {
            return null;
        }
        const { entry, ...rest } = context;
        return {
            ...rest,
            entry: entry ? { ...entry } : null,
        };
    }

    function describeSegmentationContext(context) {
        if (!context) {
            return {
                message: 'Brak aktywnego fragmentu.',
                tone: 'muted',
            };
        }
        const entry = context.entry || {};
        if (context.requiresUpload) {
            const label = entry.label || 'Obraz z dysku';
            return {
                message: `${label} — prześlij, aby użyć w detekcji symboli.`,
                tone: 'warning',
            };
        }
        const parts = [];
        if (entry.label) {
            parts.push(entry.label);
        }
        if (context.origin) {
            parts.push(`źródło: ${context.origin}`);
        }
        if (entry.historyId) {
            parts.push(`historia: ${entry.historyId}`);
        }
        if (!entry.url) {
            parts.push('brak adresu URL');
            return {
                message: parts.join(' • '),
                tone: 'warning',
            };
        }
        if (parts.length === 0) {
            parts.push('Fragment segmentacji gotowy do detekcji.');
        }
        return {
            message: parts.join(' • '),
            tone: 'success',
        };
    }

    function refreshSegmentationInfo(contextOverride) {
        if (!segmentationInfo) {
            return;
        }
        const description = describeSegmentationContext(
            contextOverride === undefined ? state.segmentationContext : contextOverride
        );
        setSegmentationInfo(description.message, description.tone);
        refreshSegmentationThumbnail(contextOverride === undefined ? state.segmentationContext : contextOverride);
    }

    function isSegmentationAvailable(contextOverride) {
        const context = contextOverride === undefined ? state.segmentationContext : contextOverride;
        return Boolean(context && context.entry && context.entry.url);
    }

    function showThumbnail(imageEl, placeholderEl, url, altText) {
        if (!imageEl || !placeholderEl || !url) {
            return;
        }
        const original = url;
        const effective = url.startsWith('data:') ? url : cacheBust(url);
        if (imageEl.dataset.source !== original) {
            imageEl.dataset.source = original;
            imageEl.src = effective;
        } else if (!url.startsWith('data:')) {
            imageEl.src = cacheBust(original);
        }
        if (altText) {
            imageEl.alt = altText;
        }
        imageEl.classList.remove('hidden');
        placeholderEl.classList.add('hidden');
    }

    function clearThumbnail(imageEl, placeholderEl, message) {
        if (!imageEl || !placeholderEl) {
            return;
        }
        imageEl.dataset.source = '';
        imageEl.src = '';
        imageEl.classList.add('hidden');
        imageEl.removeAttribute('alt');
        placeholderEl.classList.remove('hidden');
        if (typeof message === 'string') {
            placeholderEl.textContent = message;
        }
    }

    function refreshPdfThumbnail() {
        if (!pdfThumbnail || !pdfThumbPlaceholder) {
            return;
        }
        if (!state.pdfContext || !state.pdfContext.lastImageUrl) {
            clearThumbnail(pdfThumbnail, pdfThumbPlaceholder, 'Brak podglądu.');
            return;
        }
        const { filename, currentPage, totalPages } = state.pdfContext;
        const meta = [];
        if (filename) {
            meta.push(filename);
        }
        if (Number.isFinite(currentPage) && Number.isFinite(totalPages)) {
            meta.push(`strona ${currentPage}/${totalPages}`);
        }
        const altText = meta.length ? meta.join(' • ') : 'Bieżąca strona PDF';
        showThumbnail(pdfThumbnail, pdfThumbPlaceholder, state.pdfContext.lastImageUrl, altText);
    }

    function selectSegmentationPreview(context) {
        if (!context || !context.entry) {
            return null;
        }
        const entry = context.entry;
        if (entry.objectUrl) {
            return entry.objectUrl;
        }
        if (entry.previewUrl) {
            return entry.previewUrl;
        }
        if (entry.url) {
            return entry.url;
        }
        return null;
    }

    function refreshSegmentationThumbnail(contextOverride) {
        if (!segThumbnail || !segThumbPlaceholder) {
            return;
        }
        const context = contextOverride === undefined ? state.segmentationContext : contextOverride;
        if (!context || !context.entry) {
            clearThumbnail(segThumbnail, segThumbPlaceholder, 'Brak podglądu fragmentu segmentacji.');
            return;
        }
        if (context.requiresUpload && !context.entry.url && !context.entry.objectUrl) {
            clearThumbnail(segThumbnail, segThumbPlaceholder, 'Podgląd pojawi się po przesłaniu fragmentu na serwer.');
            return;
        }
        const src = selectSegmentationPreview(context);
        if (!src) {
            clearThumbnail(segThumbnail, segThumbPlaceholder, 'Brak podglądu fragmentu segmentacji.');
            return;
        }
        const altText = context.entry.label || 'Fragment segmentacji';
        showThumbnail(segThumbnail, segThumbPlaceholder, src, altText);
    }

    function refreshFileThumbnail() {
        if (!fileThumbnail || !fileThumbPlaceholder) {
            return;
        }
        if (!state.pendingFile) {
            clearThumbnail(fileThumbnail, fileThumbPlaceholder, 'Brak podglądu pliku.');
            return;
        }
        const label = state.pendingFileName || 'Załadowany plik';
        showThumbnail(fileThumbnail, fileThumbPlaceholder, state.pendingFile, label);
    }

    function setLoading(flag) {
        state.loading = flag;
        if (refreshBtn) {
            refreshBtn.disabled = flag;
        }
        if (usePdfBtn) {
            usePdfBtn.disabled = flag || !state.pdfContext || !state.pdfContext.lastImageUrl;
        }
        if (fileDetectBtn) {
            fileDetectBtn.disabled = flag || !state.pendingFile;
        }
        if (detectorSelect) {
            detectorSelect.disabled = flag || state.detectors.length === 0;
        }
        if (segmentationDetectBtn) {
            segmentationDetectBtn.disabled = flag || !isSegmentationAvailable();
        }
    }

    function populateDetectors(detectors) {
        state.detectors = detectors.slice();
        if (!detectorSelect) {
            return;
        }
        detectorSelect.innerHTML = '';
        if (!state.detectors.length) {
            const option = createElement('option', 'Brak detektorów');
            option.value = '';
            detectorSelect.appendChild(option);
            detectorSelect.disabled = true;
            setStatus('Brak zarejestrowanych detektorów.', 'error');
            return;
        }
        state.detectors.forEach((entry) => {
            const option = createElement('option', entry.name);
            option.value = entry.name;
            detectorSelect.appendChild(option);
        });
        detectorSelect.disabled = false;
        const defaultName = state.detectors[0].name;
        detectorSelect.value = defaultName;
        state.selectedDetector = defaultName;
    }

    async function fetchDetectors() {
        setLoading(true);
        try {
            const response = await fetch(DETECTORS_ENDPOINT, { headers: { 'Accept': 'application/json' } });
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const payload = await response.json();
            const detectors = Array.isArray(payload.detectors) ? payload.detectors : [];
            populateDetectors(detectors.map((entry) => ({ name: entry.name })));
            if (!detectors.length) {
                setStatus('Brak zarejestrowanych detektorów.', 'error');
            } else {
                setStatus(`Załadowano ${detectors.length} detektor(y).`, 'success');
            }
        } catch (error) {
            populateDetectors([]);
            setStatus(`Nie udało się pobrać listy detektorów: ${error}`, 'error');
        } finally {
            setLoading(false);
            updateButtons();
        }
    }

    function updateButtons() {
        if (usePdfBtn) {
            usePdfBtn.disabled = state.loading || !state.pdfContext || !state.pdfContext.lastImageUrl;
        }
        if (fileDetectBtn) {
            fileDetectBtn.disabled = state.loading || !state.pendingFile;
        }
        if (segmentationDetectBtn) {
            segmentationDetectBtn.disabled = state.loading || !isSegmentationAvailable();
        }
    }

    function updateConfidenceLabel() {
        if (!confidenceValue) {
            return;
        }
        confidenceValue.textContent = formatFloat(state.confidenceThreshold, 2);
    }

    function updateResultCounters() {
        if (!resultCount) {
            return;
        }
        const total = state.allDetections.length;
        const visible = state.visibleDetections.length;
        if (total > 0 && visible !== total) {
            resultCount.textContent = `${visible}/${total}`;
        } else {
            resultCount.textContent = String(visible);
        }
    }

    function applyDetectionFilter() {
        const baseDetections = Array.isArray(state.allDetections) ? state.allDetections : [];
        const filtered = baseDetections
            .map((detection, index) => ({ ...detection, __index: index }))
            .filter((entry) => {
                if (typeof entry.score !== 'number') {
                    return true;
                }
                return entry.score >= state.confidenceThreshold;
            });
        state.visibleDetections = filtered;
        state.previewDetections = filtered;
        if (
            state.activeDetectionIndex !== null
            && !filtered.some((entry) => entry.__index === state.activeDetectionIndex)
        ) {
            state.activeDetectionIndex = null;
        }
        renderDetections();
        updateResultCounters();
        drawPreview();
    }

    function setConfidenceThreshold(rawValue) {
        const numericValue = Number(rawValue);
        if (!Number.isFinite(numericValue)) {
            return;
        }
        const clamped = Math.max(0, Math.min(1, numericValue));
        if (Math.abs(clamped - state.confidenceThreshold) < 0.0001) {
            return;
        }
        state.confidenceThreshold = clamped;
        if (confidenceSlider && confidenceSlider.value !== String(clamped)) {
            confidenceSlider.value = String(clamped);
        }
        updateConfidenceLabel();
        applyDetectionFilter();
    }

    function setDetections(detections) {
        state.allDetections = Array.isArray(detections) ? detections.slice() : [];
        state.activeDetectionIndex = null;
        applyDetectionFilter();
    }

    function focusDetectionRow(index) {
        if (!resultTableBody || index === null || index === undefined) {
            return;
        }
        const target = resultTableBody.querySelector(`tr[data-index="${index}"]`);
        if (target) {
            target.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }

    function setActiveDetection(index, options = {}) {
        const { scroll = false } = options;
        if (index === state.activeDetectionIndex) {
            state.activeDetectionIndex = null;
        } else {
            state.activeDetectionIndex = index;
        }
        renderDetections();
        drawPreview();
        if (scroll) {
            focusDetectionRow(index);
        }
    }

    function hitTestDetection(canvasX, canvasY) {
        if (!Array.isArray(state.previewDetections) || !state.previewDetections.length || !state.previewImage) {
            return null;
        }
        const scale = state.previewScale || 1;
        for (let i = state.previewDetections.length - 1; i >= 0; i -= 1) {
            const detection = state.previewDetections[i];
            const [x, y, w, h] = normalizeBox(detection);
            const scaledX = x * scale;
            const scaledY = y * scale;
            const scaledW = w * scale;
            const scaledH = h * scale;
            const inside = canvasX >= scaledX && canvasX <= scaledX + scaledW && canvasY >= scaledY && canvasY <= scaledY + scaledH;
            if (inside) {
                return typeof detection.__index === 'number' ? detection.__index : i;
            }
        }
        return null;
    }

    function updatePdfInfo() {
        if (pdfInfo) {
            if (!state.pdfContext || !state.pdfContext.lastImageUrl) {
                pdfInfo.textContent = 'Brak załadowanej strony PDF.';
            } else {
                const { filename, currentPage, totalPages } = state.pdfContext;
                const label = filename ? `${filename}` : 'Bieżąca strona PDF';
                const pageInfo = Number.isFinite(currentPage) && Number.isFinite(totalPages)
                    ? ` (strona ${currentPage}/${totalPages})`
                    : '';
                pdfInfo.textContent = `${label}${pageInfo}`;
            }
        }
        refreshPdfThumbnail();
    }

    function updateSegmentationContext(context) {
        state.segmentationContext = cloneSegmentationContext(context);
        refreshSegmentationInfo(state.segmentationContext);
        updateButtons();
    }

    function resetPreviewState() {
        state.previewImage = null;
        state.previewDetections = [];
        state.previewSourceDescriptor = null;
    state.previewScale = 1;
    state.previewFitScale = 1;
        if (previewCanvas) {
            const ctx = previewCanvas.getContext('2d');
            ctx.clearRect(0, 0, previewCanvas.width, previewCanvas.height);
            previewCanvas.width = 0;
            previewCanvas.height = 0;
            previewCanvas.style.width = '';
            previewCanvas.style.height = '';
        }
        if (previewOverlayToggle) {
            previewOverlayToggle.checked = state.showDetections;
        }
    }

    function clearPreview() {
        resetPreviewState();
        if (previewSourceLabel) {
            previewSourceLabel.textContent = 'Podgląd niedostępny.';
        }
    }

    function updatePreviewScaleLabel() {
        if (!previewSourceLabel) {
            return;
        }
        if (!state.previewImage) {
            const description = state.previewSourceDescriptor?.description || 'Podgląd niedostępny.';
            previewSourceLabel.textContent = description;
            return;
        }
        const description = state.previewSourceDescriptor?.description || 'Źródło nieznane';
        const percentage = Math.round(state.previewScale * 100);
        const parts = [`${description} — ${percentage}%`];
        const epsilon = 0.001;
        if (Math.abs(state.previewScale - state.previewFitScale) < epsilon && Math.abs(state.previewFitScale - 1) > epsilon) {
            parts.push('(dopasowanie)');
        }
        parts.push('• Dwuklik = 100% ↔ dopasowanie');
        parts.push('• Przesuwanie = lewy przycisk myszy');
        previewSourceLabel.textContent = parts.join(' ');
    }

    function calculateFitScale(image) {
        if (!image) {
            return 1;
        }
        const container = previewFrame || previewCanvas?.parentElement || null;
        let availableWidth = MAX_PREVIEW_WIDTH;
        let availableHeight = MAX_PREVIEW_HEIGHT;
        if (container) {
            const rect = container.getBoundingClientRect();
            if (rect.width > 1) {
                availableWidth = rect.width;
            }
            if (rect.height > 1) {
                availableHeight = rect.height;
            } else {
                const styles = window.getComputedStyle(container);
                const maxHeight = parseFloat(styles.maxHeight) || MAX_PREVIEW_HEIGHT;
                if (Number.isFinite(maxHeight) && maxHeight > 0) {
                    availableHeight = maxHeight;
                }
            }
            const styles = window.getComputedStyle(container);
            const paddingX = (parseFloat(styles.paddingLeft) || 0) + (parseFloat(styles.paddingRight) || 0);
            const paddingY = (parseFloat(styles.paddingTop) || 0) + (parseFloat(styles.paddingBottom) || 0);
            const borderX = (parseFloat(styles.borderLeftWidth) || 0) + (parseFloat(styles.borderRightWidth) || 0);
            const borderY = (parseFloat(styles.borderTopWidth) || 0) + (parseFloat(styles.borderBottomWidth) || 0);
            availableWidth = Math.max(1, availableWidth - paddingX - borderX - 2);
            availableHeight = Math.max(1, availableHeight - paddingY - borderY - 2);
        }
        const fitWidth = availableWidth / image.width;
        const fitHeight = availableHeight / image.height;
        const fitScale = Math.min(1, fitWidth, fitHeight);
        const clamped = Math.max(PREVIEW_MIN_SCALE, Math.min(PREVIEW_MAX_SCALE, fitScale));
        return clamped;
    }

    function drawPreview() {
        if (!previewCanvas || !state.previewImage) {
            return;
        }
        const ctx = previewCanvas.getContext('2d');
        const scale = state.previewScale || 1;
        const width = Math.max(1, Math.round(state.previewImage.width * scale));
        const height = Math.max(1, Math.round(state.previewImage.height * scale));
        previewCanvas.width = width;
        previewCanvas.height = height;
        previewCanvas.style.width = `${width}px`;
        previewCanvas.style.height = `${height}px`;
        ctx.clearRect(0, 0, width, height);
        ctx.imageSmoothingEnabled = scale < 1;
        ctx.drawImage(state.previewImage, 0, 0, width, height);

        if (state.showDetections && Array.isArray(state.previewDetections) && state.previewDetections.length > 0) {
            const lineWidth = Math.min(4, Math.max(0.5, 2 * scale));
            const fontSize = Math.min(18, Math.max(6, Math.round(12 * scale)));
            ctx.font = `${fontSize}px Inter, sans-serif`;
            const baseStroke = '#31f576';
            const baseLabelFill = 'rgba(5, 18, 29, 0.6)';
            const highlightStroke = '#ff8a3d';
            const highlightLabelFill = 'rgba(255, 138, 61, 0.65)';
            state.previewDetections.forEach((detection, index) => {
                const [x, y, w, h] = normalizeBox(detection);
                const scaledX = x * scale;
                const scaledY = y * scale;
                const scaledW = w * scale;
                const scaledH = h * scale;
                const isActive = typeof detection.__index === 'number' && detection.__index === state.activeDetectionIndex;
                const strokeColor = isActive ? highlightStroke : baseStroke;
                const labelFill = isActive ? highlightLabelFill : baseLabelFill;
                const effectiveLineWidth = isActive ? Math.min(6, lineWidth * 1.5) : lineWidth;
                ctx.lineWidth = effectiveLineWidth;
                ctx.strokeStyle = strokeColor;
                ctx.strokeRect(scaledX, scaledY, scaledW, scaledH);
                const label = detection.label || `#${index + 1}`;
                const score = typeof detection.score === 'number' ? formatFloat(detection.score) : '--';
                const caption = `${label} (${score})`;
                const padding = Math.min(12, Math.max(2, Math.round(4 * scale)));
                const textWidth = ctx.measureText(caption).width + padding * 2;
                const textHeight = fontSize + padding * 2;
                const labelX = scaledX;
                const labelY = Math.max(0, scaledY - textHeight);
                ctx.fillStyle = labelFill;
                ctx.fillRect(labelX, labelY, textWidth, textHeight);
                ctx.fillStyle = '#ffffff';
                ctx.fillText(caption, labelX + padding, labelY + textHeight - padding - 2);
                ctx.fillStyle = baseLabelFill;
            });
        }

        updatePreviewScaleLabel();
    }

    function renderPreview(sourceDescriptor) {
        if (!previewCanvas || !sourceDescriptor || !sourceDescriptor.preview) {
            clearPreview();
            return;
        }

        state.previewSourceDescriptor = sourceDescriptor;
        state.previewImage = null;
        state.previewScale = 1;
        state.previewFitScale = 1;
        updatePreviewScaleLabel();

        const image = new Image();
        image.onload = () => {
            state.previewImage = image;
            const fitScale = calculateFitScale(image);
            state.previewFitScale = fitScale;
            state.previewScale = fitScale;
            drawPreview();
        };
        image.onerror = () => {
            clearPreview();
        };
        image.src = sourceDescriptor.preview;
        updatePreviewScaleLabel();
    }

    function setPreviewScale(rawScale) {
        if (!state.previewImage) {
            return;
        }
        const clamped = Math.max(PREVIEW_MIN_SCALE, Math.min(PREVIEW_MAX_SCALE, rawScale));
        if (Math.abs(clamped - state.previewScale) < 0.0001) {
            drawPreview();
            return;
        }
        state.previewScale = clamped;
        drawPreview();
    }

    function adjustPreviewScale(delta) {
        if (!state.previewImage) {
            return;
        }
        const direction = delta < 0 ? 1 : -1;
        const factor = 1 + PREVIEW_ZOOM_STEP * direction;
        setPreviewScale(state.previewScale * factor);
    }

    function resetPreviewScale(useFitScale = false) {
        if (!state.previewImage) {
            return;
        }
        const target = useFitScale ? state.previewFitScale : 1;
        setPreviewScale(target);
    }

    function refreshFitScale(redraw = false) {
        if (!state.previewImage) {
            return;
        }
        state.previewFitScale = calculateFitScale(state.previewImage);
        if (redraw) {
            if (Math.abs(state.previewScale - state.previewFitScale) < 0.0001) {
                state.previewScale = state.previewFitScale;
                drawPreview();
            } else {
                updatePreviewScaleLabel();
            }
        }
    }

    function renderDetections() {
        if (!resultTableBody) {
            return;
        }
        resultTableBody.innerHTML = '';
        const detections = state.visibleDetections;
        if (!Array.isArray(detections) || detections.length === 0) {
            const row = createElement('tr');
            const cell = createElement('td', 'Brak detekcji.');
            cell.colSpan = 4;
            row.appendChild(cell);
            resultTableBody.appendChild(row);
            return;
        }
        const fragment = document.createDocumentFragment();
        detections.forEach((detection, index) => {
            const row = createElement('tr');
            const originalIndex = typeof detection.__index === 'number' ? detection.__index : index;
            if (originalIndex === state.activeDetectionIndex) {
                row.classList.add('table-primary');
            }
            const idCell = createElement('td', detection.id || `#${index + 1}`);
            const labelCell = createElement('td', detection.label || 'component');
            const scoreValue = typeof detection.score === 'number' ? formatFloat(detection.score, 3) : '--';
            const scoreCell = createElement('td', scoreValue);
            const [x, y, w, h] = normalizeBox(detection);
            const boxCell = createElement('td', `${formatFloat(x)} × ${formatFloat(y)} → ${formatFloat(w)} × ${formatFloat(h)}`);
            row.appendChild(idCell);
            row.appendChild(labelCell);
            row.appendChild(scoreCell);
            row.appendChild(boxCell);
            row.dataset.index = String(originalIndex);
            row.tabIndex = 0;
            row.addEventListener('click', () => {
                setActiveDetection(originalIndex);
            });
            row.addEventListener('keydown', (event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    setActiveDetection(originalIndex);
                }
            });
            fragment.appendChild(row);
        });
        resultTableBody.appendChild(fragment);
    }

    function renderSummary(result, sourceDescriptor) {
        updateResultCounters();
        if (resultDetector) {
            const info = result.detector || {};
            const name = info.name || state.selectedDetector || '--';
            const version = info.version ? ` v${info.version}` : '';
            resultDetector.textContent = `${name}${version}`;
        }
        if (resultLatency) {
            const latency = result.summary && typeof result.summary.latencyMs === 'number'
                ? `${formatFloat(result.summary.latencyMs)} ms`
                : '--';
            resultLatency.textContent = latency;
        }
        if (resultSummary) {
            const parts = [];
            if (sourceDescriptor && sourceDescriptor.description) {
                parts.push(sourceDescriptor.description);
            }
            if (Array.isArray(state.visibleDetections)) {
                const uniqueLabels = new Set(state.visibleDetections.map((entry) => entry.label).filter(Boolean));
                if (uniqueLabels.size > 0) {
                    parts.push(`etykiety: ${Array.from(uniqueLabels).join(', ')}`);
                }
            }
            if (state.confidenceThreshold > 0) {
                parts.push(`próg pewności ≥ ${formatFloat(state.confidenceThreshold, 2)}`);
            }
            resultSummary.textContent = parts.join(' | ') || 'Brak dodatkowych informacji.';
        }
        if (rawOutputPre) {
            if (result.summary && result.summary.rawOutput) {
                rawOutputPre.textContent = JSON.stringify(result.summary.rawOutput, null, 2);
            } else {
                rawOutputPre.textContent = 'Brak danych RAW.';
            }
        }
        if (historyLink) {
            const historyEntry = result.historyEntry;
            if (historyEntry && historyEntry.url) {
                historyLink.href = historyEntry.url;
                historyLink.classList.remove('hidden');
            } else {
                historyLink.href = '#';
                historyLink.classList.add('hidden');
            }
        }
    }

    function handleResult(result, sourceDescriptor) {
        state.lastResult = result;
        state.lastSource = sourceDescriptor;
        setDetections(result.detections);
        renderSummary(result, sourceDescriptor);
        renderPreview(sourceDescriptor);

        // If server returned a history entry, persist and notify observers.
        if (result.historyEntry) {
            upsertHistoryEntry(result.historyEntry);
        }

        // Always notify history observers with the best available source entry:
        // prefer server-provided history entry, otherwise synthesize a minimal entry
        // based on the sourceDescriptor so other modules (segmentation) can react.
        if (historyObservers.size > 0) {
            const notifyEntry = result.historyEntry || {
                id: null,
                meta: {
                    source: {
                        imageUrl: sourceDescriptor.preview || sourceDescriptor.value || null,
                        url: sourceDescriptor.value || sourceDescriptor.preview || null,
                    },
                },
                label: sourceDescriptor.description || 'Ostatni wynik detekcji',
            };
            historyObservers.forEach((observer) => {
                try {
                    observer(notifyEntry);
                } catch (error) {
                    console.error('Błąd obsługi wpisu historii detekcji symboli', error);
                }
            });
        }
    }

    async function runDetection(sourceDescriptor) {
        if (!state.selectedDetector) {
            setStatus('Brak wybranego detektora.', 'error');
            return;
        }
        if (!sourceDescriptor) {
            setStatus('Nie wybrano źródła obrazu.', 'error');
            return;
        }
        setLoading(true);
        setStatus('Uruchamiam detekcję symboli...', 'info');
        try {
            const payload = {
                detector: state.selectedDetector,
            };
            if (storeHistoryCheckbox && storeHistoryCheckbox.checked) {
                payload.storeHistory = true;
            }
            if (sourceDescriptor.type === 'data') {
                payload.imageData = sourceDescriptor.value;
            } else if (sourceDescriptor.type === 'url') {
                payload.imageUrl = sourceDescriptor.value;
            }
            if (sourceDescriptor.historyId) {
                payload.historyId = sourceDescriptor.historyId;
            }

            const response = await fetch(DETECT_ENDPOINT, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                },
                body: JSON.stringify(payload),
            });
            if (!response.ok) {
                const errorPayload = await response.json().catch(() => ({}));
                const message = errorPayload.error || `HTTP ${response.status}`;
                throw new Error(message);
            }
            const result = await response.json();
            handleResult(result, sourceDescriptor);
            setStatus(`Zakończono. Wykryto ${result.count ?? 0} symbol(i).`, 'success');
        } catch (error) {
            setStatus(`Błąd detekcji: ${error.message || error}`, 'error');
        } finally {
            setLoading(false);
            updateButtons();
        }
    }

    function handleDetectorChange() {
        if (!detectorSelect) {
            return;
        }
        state.selectedDetector = detectorSelect.value || null;
    }

    function handleFileChange(event) {
        if (!fileInput) {
            return;
        }
        const [file] = event.target?.files || [];
        if (!file) {
            state.pendingFile = null;
            state.pendingFileName = '';
            if (fileNameLabel) {
                fileNameLabel.textContent = 'Nie wybrano pliku.';
            }
            refreshFileThumbnail();
            updateButtons();
            return;
        }
        if (!file.type.startsWith('image/')) {
            setStatus('Obsługiwane są wyłącznie pliki graficzne (PNG/JPEG/WEBP).', 'error');
            fileInput.value = '';
            refreshFileThumbnail();
            return;
        }
        const reader = new FileReader();
        reader.onload = () => {
            const result = reader.result;
            if (typeof result === 'string') {
                state.pendingFile = result;
                state.pendingFileName = file.name;
                if (fileNameLabel) {
                    fileNameLabel.textContent = `${file.name} (${Math.round(file.size / 1024)} KB)`;
                }
                setStatus(`Załadowano plik ${file.name}.`, 'success');
            } else {
                state.pendingFile = null;
                state.pendingFileName = '';
                if (fileNameLabel) {
                    fileNameLabel.textContent = 'Nie udało się odczytać pliku.';
                }
                setStatus('Nie udało się odczytać danych pliku.', 'error');
            }
            refreshFileThumbnail();
            updateButtons();
        };
        reader.onerror = () => {
            state.pendingFile = null;
            state.pendingFileName = '';
            if (fileNameLabel) {
                fileNameLabel.textContent = 'Błąd odczytu pliku.';
            }
            setStatus('Wystąpił błąd podczas odczytu pliku.', 'error');
            refreshFileThumbnail();
            updateButtons();
        };
        reader.readAsDataURL(file);
    }

    function detectFromPdf() {
        if (!state.pdfContext || !state.pdfContext.lastImageUrl) {
            setStatus('Brak załadowanej strony PDF.', 'error');
            return;
        }
        const url = state.pdfContext.lastImageUrl;
        const resolved = new URL(url, window.location.origin).toString();
        const description = state.pdfContext.filename
            ? `${state.pdfContext.filename} (strona ${state.pdfContext.currentPage}/${state.pdfContext.totalPages})`
            : 'Bieżąca strona PDF';
        runDetection({
            type: 'url',
            value: resolved,
            preview: resolved,
            description,
        });
    }

    async function detectFromSegmentation() {
        let context = state.segmentationContext;
        if (!context && typeof getSegmentationContext === 'function') {
            updateSegmentationContext(getSegmentationContext());
            context = state.segmentationContext;
        }
        if (!context) {
            setStatus('Brak aktywnego fragmentu segmentacji.', 'error');
            return;
        }

        let releaseLoading = false;
        if (!state.loading) {
            setLoading(true);
            releaseLoading = true;
        }

        try {
            let effectiveContext = context;
            if (effectiveContext.requiresUpload) {
                if (typeof ensureSegmentationSource !== 'function') {
                    setStatus('Źródło segmentacji wymaga przesłania na serwer, ale brak obsługi.', 'error');
                    return;
                }
                setStatus('Przesyłam fragment segmentacji na serwer...', 'info');
                const success = await ensureSegmentationSource();
                if (!success) {
                    setStatus('Nie udało się przesłać fragmentu segmentacji.', 'error');
                    return;
                }
                if (typeof getSegmentationContext === 'function') {
                    updateSegmentationContext(getSegmentationContext());
                } else {
                    updateSegmentationContext(effectiveContext);
                }
                effectiveContext = state.segmentationContext;
                if (!effectiveContext || effectiveContext.requiresUpload) {
                    setStatus('Fragment segmentacji nadal nie jest gotowy do detekcji.', 'error');
                    return;
                }
            }

            const entry = effectiveContext.entry || {};
            if (!entry.url) {
                setStatus('Fragment segmentacji nie ma dostępnego adresu URL.', 'error');
                return;
            }

            const parts = [];
            if (entry.label) {
                parts.push(entry.label);
            } else {
                parts.push('Fragment segmentacji');
            }
            if (effectiveContext.origin) {
                parts.push(`źródło: ${effectiveContext.origin}`);
            }

            const descriptor = {
                type: 'url',
                value: entry.url,
                preview: entry.url,
                description: parts.join(' • '),
            };
            const historyId = entry.historyId || entry.id || effectiveContext.historyId;
            if (historyId) {
                descriptor.historyId = historyId;
            }

            releaseLoading = false;
            await runDetection(descriptor);
        } finally {
            if (releaseLoading) {
                setLoading(false);
            }
        }
    }

    function detectFromFile() {
        if (!state.pendingFile) {
            setStatus('Najpierw wybierz plik do analizy.', 'error');
            return;
        }
        runDetection({
            type: 'data',
            value: state.pendingFile,
            preview: state.pendingFile,
            description: state.pendingFileName || 'Załadowany plik',
        });
    }

    function wireEvents() {
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                void fetchDetectors();
            });
        }
        if (detectorSelect) {
            detectorSelect.addEventListener('change', handleDetectorChange);
        }
        if (fileInput) {
            fileInput.addEventListener('change', handleFileChange);
        }
        if (fileDetectBtn) {
            fileDetectBtn.addEventListener('click', detectFromFile);
        }
        if (usePdfBtn) {
            usePdfBtn.addEventListener('click', detectFromPdf);
        }
        if (segmentationDetectBtn) {
            segmentationDetectBtn.addEventListener('click', () => {
                void detectFromSegmentation();
            });
        }
        if (historyRefreshBtn) {
            historyRefreshBtn.addEventListener('click', () => {
                void fetchDetectionHistory();
            });
        }
    }

    function updatePdfContext(context) {
        state.pdfContext = context || null;
        updatePdfInfo();
        updateButtons();
    }

    function onTabVisible() {
        if (!state.detectors.length && !state.loading) {
            void fetchDetectors();
        }
        if (state.lastResult && state.lastSource) {
            if (state.previewImage) {
                drawPreview();
            } else {
                renderPreview(state.lastSource, state.lastResult.detections);
            }
        }
        if (typeof getSegmentationContext === 'function') {
            updateSegmentationContext(getSegmentationContext());
        } else {
            refreshSegmentationInfo();
        }
        updatePdfInfo();
        updateButtons();
    }

    function onTabHidden() {
        // No-op placeholder for symmetry with other modules
    }

    function registerHistoryObserver(handler) {
        if (typeof handler !== 'function') {
            return () => {};
        }
        historyObservers.add(handler);
        return () => {
            historyObservers.delete(handler);
        };
    }

    if (previewCanvas) {
        previewCanvas.addEventListener('wheel', (event) => {
            if (!state.previewImage) {
                return;
            }
            event.preventDefault();
            adjustPreviewScale(event.deltaY);
        }, { passive: false });

        previewCanvas.addEventListener('dblclick', () => {
            if (!state.previewImage) {
                return;
            }
            refreshFitScale();
            const epsilon = 0.01;
            const atFitScale = Math.abs(state.previewScale - state.previewFitScale) < epsilon;
            const atHundredPercent = Math.abs(state.previewScale - 1) < epsilon;

            if (atHundredPercent) {
                setPreviewScale(state.previewFitScale);
            } else if (atFitScale) {
                setPreviewScale(1);
            } else {
                setPreviewScale(state.previewFitScale);
            }
        });

        previewCanvas.addEventListener('mousedown', (event) => {
            if (!state.previewImage || !previewFrame) {
                return;
            }
            if (event.button !== 0) {
                return;
            }
            state.isPanning = true;
            state.panStartX = event.clientX;
            state.panStartY = event.clientY;
            state.scrollStartX = previewFrame.scrollLeft;
            state.scrollStartY = previewFrame.scrollTop;
            previewCanvas.style.cursor = 'grabbing';
            event.preventDefault();
        });

        previewCanvas.addEventListener('mousemove', (event) => {
            if (!state.isPanning || !previewFrame) {
                return;
            }
            const deltaX = state.panStartX - event.clientX;
            const deltaY = state.panStartY - event.clientY;
            previewFrame.scrollLeft = state.scrollStartX + deltaX;
            previewFrame.scrollTop = state.scrollStartY + deltaY;
            event.preventDefault();
        });

        previewCanvas.addEventListener('mouseup', (event) => {
            if (event.button !== 0) {
                return;
            }
            state.isPanning = false;
            previewCanvas.style.cursor = '';
        });

        previewCanvas.addEventListener('click', (event) => {
            if (!state.previewImage) {
                return;
            }
            const rect = previewCanvas.getBoundingClientRect();
            const canvasX = event.clientX - rect.left;
            const canvasY = event.clientY - rect.top;
            const hitIndex = hitTestDetection(canvasX, canvasY);
            if (hitIndex !== null && hitIndex !== undefined) {
                setActiveDetection(hitIndex, { scroll: true });
            }
        });

        previewCanvas.addEventListener('mouseleave', () => {
            state.isPanning = false;
            previewCanvas.style.cursor = '';
        });

        previewCanvas.style.cursor = 'grab';
    }

    if (previewOverlayToggle) {
        previewOverlayToggle.checked = state.showDetections;
        previewOverlayToggle.addEventListener('change', () => {
            state.showDetections = Boolean(previewOverlayToggle.checked);
            drawPreview();
        });
    }

    if (confidenceSlider) {
        const initialValue = Number(confidenceSlider.value);
        const normalized = Number.isFinite(initialValue)
            ? Math.max(0, Math.min(1, initialValue))
            : state.confidenceThreshold;
        state.confidenceThreshold = normalized;
        confidenceSlider.value = String(normalized);
        updateConfidenceLabel();
        confidenceSlider.addEventListener('input', (event) => {
            setConfidenceThreshold(event.target.value);
        });
    } else {
        updateConfidenceLabel();
    }

    renderDetections();
    updateResultCounters();
    renderHistoryEntries();

    window.addEventListener('resize', () => {
        refreshFitScale(true);
    });

    wireEvents();
    updatePdfInfo();
    refreshSegmentationInfo();
    refreshFileThumbnail();
    updateButtons();
    setStatus('Wybierz detektor i źródło obrazu, aby rozpocząć.', 'muted');
    void fetchDetectors();
    void fetchDetectionHistory({ silent: true });

    return {
        updatePdfContext,
        updateSegmentationContext,
        onTabVisible,
        onTabHidden,
        registerHistoryObserver,
        loadAnnotations,  // Eksportuj nową funkcję
    };
}

/**
 * Ładuje anotacje z pliku JSON (Label Studio lub COCO).
 * Automatycznie wykrywa i konwertuje rotated rectangles.
 *
 * @param {string} annotationFile - Ścieżka do pliku anotacji
 * @param {boolean} validate - Czy walidować format (domyślnie true)
 * @returns {Promise<Object>} Dane COCO
 */
export async function loadAnnotations(annotationFile, validate = true) {
    const LOAD_ANNOTATIONS_ENDPOINT = '/api/symbols/load-annotations';

    console.log(`Ładowanie anotacji z: ${annotationFile}`);

    try {
        const response = await fetch(LOAD_ANNOTATIONS_ENDPOINT, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                annotationFile: annotationFile,
                validate: validate,
            }),
        });

        const result = await response.json();

        if (!response.ok || !result.success) {
            const errorMsg = result.error || `HTTP ${response.status}`;
            console.error('Błąd ładowania anotacji:', errorMsg);
            showNotification(
                `❌ Błąd ładowania anotacji: ${errorMsg}`,
                'error'
            );
            throw new Error(errorMsg);
        }

        // Wyświetl komunikat użytkownikowi
        const info = result.info || {};
        console.log('✅ Anotacje załadowane:', info);

        let notificationMsg = info.message || 'Anotacje załadowane pomyślnie';

        // Jeśli była konwersja, pokaż szczegóły
        if (info.conversionPerformed) {
            notificationMsg = `🔄 ${notificationMsg}`;
            console.log(
                `Konwersja wykonana: ${info.rotatedCount} rotated rectangles → segmentation polygons`
            );
        } else {
            notificationMsg = `✅ ${notificationMsg}`;
        }

        // Pokaż ostrzeżenia walidacji (jeśli są)
        if (info.validationErrors && info.validationErrors.length > 0) {
            console.warn('⚠️  Ostrzeżenia walidacji:', info.validationErrors);
            notificationMsg += `\n⚠️  ${info.validationErrors.length} ostrzeżeń walidacji (sprawdź konsolę)`;
        }

        showNotification(notificationMsg, info.conversionPerformed ? 'warning' : 'success');

        return result.data;

    } catch (error) {
        console.error('Wyjątek podczas ładowania anotacji:', error);
        showNotification(
            `❌ Błąd ładowania anotacji: ${error.message}`,
            'error'
        );
        throw error;
    }
}

/**
 * Wyświetla powiadomienie użytkownikowi.
 *
 * @param {string} message - Wiadomość do wyświetlenia
 * @param {string} type - Typ: 'success', 'error', 'warning', 'info'
 */
function showNotification(message, type = 'info') {
    // Jeśli jest toast container - użyj go
    const toastContainer = document.getElementById('toast-container');
    if (toastContainer) {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        toast.style.cssText = `
            background: ${type === 'error' ? '#dc3545' : type === 'warning' ? '#ffc107' : '#28a745'};
            color: white;
            padding: 12px 20px;
            border-radius: 4px;
            margin-bottom: 10px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        `;
        toastContainer.appendChild(toast);

        // Auto-remove po 5 sekundach
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transition = 'opacity 0.3s';
            setTimeout(() => toast.remove(), 300);
        }, 5000);
    } else {
        // Fallback: console + alert dla błędów
        console.log(`[${type.toUpperCase()}] ${message}`);
        if (type === 'error') {
            alert(message);
        }
    }
}
