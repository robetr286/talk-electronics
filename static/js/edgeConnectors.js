import { formatTimestamp as tsFormatTimestamp } from './utils/timestamp.js';

const API_BASE = '/api/edge-connectors';
const TOKEN_STORAGE_KEY = 'app:edgeConnectorsToken';
const EDGE_ID_PATTERN = /^[ABCD][0-9]{2}$/;
const ALLOWED_GEOMETRY_TYPES = new Set(['polygon', 'rect', 'polyline']);
const DEFAULT_GEOMETRY_TEMPLATE = {
    type: 'polygon',
    points: [
        [0, 0],
        [120, 0],
        [120, 30],
        [0, 30],
    ],
};

function cacheBust(url) {
    if (!url || typeof url !== 'string') {
        return url;
    }
    if (/^(data|blob):/i.test(url)) {
        return url;
    }
    const token = `_=${Date.now()}`;
    return url.includes('?') ? `${url}&${token}` : `${url}?${token}`;
}

function trimToNull(value) {
    if (typeof value !== 'string') {
        return null;
    }
    const trimmed = value.trim();
    return trimmed.length ? trimmed : null;
}

function formatTimestamp(value) {
    // Delegate to shared util, keep previous empty marker
    if (!value) return '--';
    return tsFormatTimestamp(value, { empty: '--' });
}

function resolveHeaderName() {
    if (typeof window !== 'undefined' && window.EDGE_CONNECTORS_HEADER) {
        return window.EDGE_CONNECTORS_HEADER;
    }
    return 'X-Edge-Token';
}

function resolveToken() {
    if (typeof window === 'undefined') {
        return null;
    }
    if (window.EDGE_CONNECTORS_TOKEN) {
        return window.EDGE_CONNECTORS_TOKEN;
    }
    try {
        return window.localStorage.getItem(TOKEN_STORAGE_KEY);
    } catch (error) {
        console.warn('[edgeConnectors] Nie udało się odczytać tokenu z localStorage.', error);
        return null;
    }
}

function extractTokenFromUrl(url) {
    if (!url || typeof url !== 'string') {
        return null;
    }
    try {
        const parsed = new URL(url, window.location.origin);
        const pathname = parsed.pathname || '';
        const filename = pathname.split('/').pop() || '';
        // przykłady: 878f4b..._page_1.png lub import_abcd1234.png
        const match = filename.match(/^([a-zA-Z0-9]+)(?:_[^.]*)?\./);
        return match ? match[1] : null;
    } catch (error) {
        return null;
    }
}

function buildAuthHeaders() {
    const token = resolveToken();
    if (!token) {
        return {};
    }
    return {
        [resolveHeaderName()]: token,
    };
}

function safeJsonStringify(value) {
    try {
        return JSON.stringify(value, null, 2);
    } catch (error) {
        return '';
    }
}

function loadImageSize(url) {
    return new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => resolve({ width: img.naturalWidth, height: img.naturalHeight });
        img.onerror = reject;
        img.src = cacheBust(url);
    });
}

function deriveRoi(meta, geometry) {
    const metaObj = meta && typeof meta === 'object' ? meta : {};
    const candidates = [metaObj.roi_abs, metaObj.roiAbs, metaObj.roi];
        for (const candidate of candidates) {
        if (!candidate || typeof candidate !== 'object') {
            continue;
        }
        const { x, y, w, h } = candidate;
        if ([x, y, w, h].every((v) => Number.isFinite(Number(v)))) {
            return {
                x: Number(x),
                y: Number(y),
                w: Number(w),
                h: Number(h),
            };
        }
    }
    const geom = geometry && typeof geometry === 'object' ? geometry : null;
    const points = geom && Array.isArray(geom.points) ? geom.points : null;
    if (!points || points.length < 2) {
        return null;
    }
    const xs = [];
    const ys = [];
    points.forEach((pt) => {
        if (!Array.isArray(pt) || pt.length < 2) {
            return;
        }
        const px = Number(pt[0]);
        const py = Number(pt[1]);
        if (Number.isFinite(px) && Number.isFinite(py)) {
            xs.push(px);
            ys.push(py);
        }
    });
    if (!xs.length || !ys.length) {
        return null;
    }
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    return {
        x: minX,
        y: minY,
        w: Math.max(maxX - minX, 1),
        h: Math.max(maxY - minY, 1),
    };
}

function normalizeEdgeConnectorEntry(entry) {
    if (!entry || typeof entry !== 'object') {
        return null;
    }
    const historyId = entry.historyId || entry?.metadata?.historyId || null;
    const roiAbs = normalizeRoi(
        entry.roiAbs
        || entry.roi
        || entry?.metadata?.roi_abs
        || entry?.metadata?.roi
        || entry?.metadata?.geometry?.roi
        || deriveRoi(entry?.metadata, entry?.geometry || entry?.payload?.geometry)
    );
    return {
        id: entry.id || null,
        edgeId: entry.edgeId || entry.label || null,
        page: entry.page || entry?.metadata?.page || null,
        netName: entry.netName || null,
        label: entry.label || null,
        note: entry.note || null,
        updatedAt: entry.updatedAt || entry.createdAt || null,
        historyId,
        historyIdNormalized: historyId ? String(historyId).toLowerCase() : null,
        roiAbs,
    };
}

export function initEdgeConnectors(dom = {}, deps = {}) {
    const {
        statusLabel,
        pdfInfo,
        pageInfo,
        selectionInfo,
        usePdfBtn,
        form,
        edgeIdInput,
        pageInput,
        labelInput,
        netNameInput,
        sheetIdInput,
        historyIdInput,
        noteInput,
        geometryInput,
        geometryTemplateBtn,
        previewCanvas,
        previewMockBtn,
        previewLoadBtn,
        shrinkSlider,
        shrinkValue,
        saveBtn,
        resetBtn,
        countBadge,
        refreshBtn,
        listBody,
        listEmpty,
        detailTitle,
        detailJson,
        copyBtn,
    } = dom;

    const { getPdfContext = null, getSegmentationContext = null } = deps;

    const state = {
        loading: false,
        saving: false,
        deleting: false,
        connectors: [],
        loadedOnce: false,
        activeId: null,
        activeEntry: null,
        pdfContext: getPdfContext ? getPdfContext() : null,
        segmentationContext: getSegmentationContext ? getSegmentationContext() : null,
        detailCache: new Map(),
        shrink: 0,
        autoHistoryId: null,
        autoGeometryFilled: false,
    };

    const preview = {
        canvas: previewCanvas,
        ctx: previewCanvas ? previewCanvas.getContext('2d') : null,
        bgImage: null,
        bgUrl: null,
        bgNaturalWidth: null,
        bgNaturalHeight: null,
    };

    function loadPreviewFromCandidates(candidates = []) {
        if (!preview.ctx || !preview.canvas) {
            return;
        }
        console.debug('[edgeConnectors] loadPreviewFromCandidates candidates=', candidates);
        const queue = candidates.filter(Boolean);
        const tryNext = () => {
            if (!queue.length) {
                console.debug('[edgeConnectors] loadPreviewFromCandidates: none matched');
                preview.bgImage = null;
                preview.bgUrl = null;
                preview.bgNaturalWidth = null;
                preview.bgNaturalHeight = null;
                clearPreview('Brak podglądu tła');
                return;
            }
            const rawUrl = queue.shift();
            const effectiveUrl = cacheBust(rawUrl);
            console.debug('[edgeConnectors] try preview url=', effectiveUrl);
            const img = new Image();
            img.onload = () => {
                console.debug('[edgeConnectors] preview loaded url=', effectiveUrl, 'size=', img.naturalWidth, img.naturalHeight);
                preview.bgImage = img;
                preview.bgUrl = effectiveUrl;
                preview.bgNaturalWidth = img.naturalWidth;
                preview.bgNaturalHeight = img.naturalHeight;
                renderPreviewFromForm();
            };
            img.onerror = (err) => {
                console.debug('[edgeConnectors] preview failed url=', effectiveUrl, err);
                tryNext();
            };
            preview.bgImage = null;
            preview.bgUrl = null;
            preview.bgNaturalWidth = null;
            preview.bgNaturalHeight = null;
            img.src = effectiveUrl;
        };
        tryNext();
    }

    // Wyznacza tight bbox z obrazu na podstawie nie-białych pikseli (sampling dla wydajności)
    function computePercentile(sortedArr, p) {
        if (!Array.isArray(sortedArr) || sortedArr.length === 0) return null;
        const idx = Math.floor((p / 100) * (sortedArr.length - 1));
        return sortedArr[Math.max(0, Math.min(sortedArr.length - 1, idx))];
    }

    function computeImageContentBBox(img, sample = 8, whitenessThreshold = 250) {
        if (!img || typeof img.naturalWidth !== 'number' || typeof img.naturalHeight !== 'number') {
            return null;
        }
        try {
            const w = img.naturalWidth;
            const h = img.naturalHeight;
            const canvas = document.createElement('canvas');
            canvas.width = w;
            canvas.height = h;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(img, 0, 0, w, h);
            // Adaptacyjne próbkowanie: dla dużych obrazów zwiększ gęstość próbkowania
            const autoStep = Math.max(1, Math.floor(Math.min(w, h) / 800));
            const step = Math.max(1, Math.min(Math.floor(sample), autoStep));
            const xs = [];
            const ys = [];
            for (let y = 0; y < h; y += step) {
                const row = ctx.getImageData(0, y, w, 1).data;
                for (let x = 0; x < w; x += step) {
                    const i = (x % w) * 4;
                    const r = row[i];
                    const g = row[i + 1];
                    const b = row[i + 2];
                    const lum = 0.299 * r + 0.587 * g + 0.114 * b;
                    if (lum < whitenessThreshold) {
                        xs.push(x);
                        ys.push(y);
                    }
                }
            }
            if (!xs.length || !ys.length) return null;
            xs.sort((a, b) => a - b);
            ys.sort((a, b) => a - b);
            // Użyj percentyli (mniej agresywne okrawanie) zamiast min/max, aby pominąć pojedyncze artefakty przy krawędziach
            const pLow = 1;
            const pHigh = 99;
            const minX = computePercentile(xs, pLow);
            const maxX = computePercentile(xs, pHigh);
            const minY = computePercentile(ys, pLow);
            const maxY = computePercentile(ys, pHigh);
            if (minX === null || maxX === null || minY === null || maxY === null) return null;
            // rozszerz bbox o padding procentowy i minPad — delikatniejsze wartości domyślne
            const contentArea = (maxX - minX) * (maxY - minY);
            const totalArea = w * h;
            const areaRatio = contentArea / Math.max(1, totalArea);
            let padPercent = 0.06;
            let minPad = 10;
            if (areaRatio > 0.02) {
                // większe obiekty - można przyciąć trochę mocniej, ale nadal ostrożnie
                padPercent = 0.04;
                minPad = 6;
            }
            const padX = Math.max(minPad, Math.round((maxX - minX) * padPercent));
            const padY = Math.max(minPad, Math.round((maxY - minY) * padPercent));
            const x0 = Math.max(0, minX - padX);
            const y0 = Math.max(0, minY - padY);
            const x1 = Math.min(w, maxX + padX);
            const y1 = Math.min(h, maxY + padY);
            // jeśli percentylowy bbox jest prawie cały obraz, odrzuć go (może oznaczać brak istotnej zawartości)
            if (x0 <= 0 && y0 <= 0 && x1 >= w - 1 && y1 >= h - 1) {
                return null;
            }
            console.debug('[edgeConnectors] computeImageContentBBox areaRatio=', areaRatio.toFixed(4), 'padPercent=', padPercent, 'minPad=', minPad);
            return { x: x0, y: y0, w: Math.max(1, x1 - x0), h: Math.max(1, y1 - y0) };
        } catch (err) {
            console.debug('[edgeConnectors] computeImageContentBBox failed', err);
            return null;
        }
    }

    function setStatus(message, tone = 'muted') {
        if (!statusLabel) {
            return;
        }
        const base = 'status-pill';
        let toneClass = 'text-muted';
        if (tone === 'success') {
            toneClass = 'text-success';
        } else if (tone === 'error') {
            toneClass = 'text-danger';
        } else if (tone === 'warning') {
            toneClass = 'text-warning';
        } else if (tone === 'info') {
            toneClass = 'text-primary';
        }
        statusLabel.className = `${base} ${toneClass}`;
        statusLabel.textContent = message || '';
        if (message && tone === 'info' && state.segmentationContext?.sourceEntry) {
            // Podpowiedź UX: gdy mamy kontekst segmentacji, pokaż ID i dostępność ROI w łączeniu schematów
            const historyId = state.segmentationContext.sourceEntry.historyId || state.segmentationContext.sourceEntry.id;
            const roiHint = state.segmentationContext.edgeConnectorRoi ? 'ROI dostępne' : 'brak ROI';
            statusLabel.title = historyId ? `Źródło: ${historyId} • ${roiHint}` : roiHint;
        } else if (statusLabel.title) {
            statusLabel.title = '';
        }
    }

    function describePdfContext(context) {
        if (!context || !context.token) {
            return 'Brak pliku';
        }
        const filename = context.filename || 'Nieznany plik';
        const total = Number.isFinite(context.totalPages) ? context.totalPages : '?';
        const dpi = context.imageDpi ? `${context.imageDpi} DPI` : 'DPI nieznane';
        return `${filename} • ${dpi}`;
    }

    function updatePdfPanel() {
        if (pdfInfo) {
            pdfInfo.textContent = describePdfContext(state.pdfContext);
        }
        if (pageInfo) {
            if (state.pdfContext && Number.isFinite(state.pdfContext.currentPage)) {
                const total = Number.isFinite(state.pdfContext.totalPages) ? state.pdfContext.totalPages : '?';
                pageInfo.textContent = `Strona ${state.pdfContext.currentPage} / ${total}`;
            } else {
                pageInfo.textContent = '-';
            }
        }
        if (usePdfBtn) {
            usePdfBtn.disabled = !state.pdfContext || !state.pdfContext.token;
        }
    }

    function updateSelectionLabel() {
        if (!selectionInfo) {
            return;
        }
        if (state.activeEntry && (state.activeEntry.edgeId || state.activeEntry.payload?.edgeId)) {
            const edgeId = state.activeEntry.payload?.edgeId || state.activeEntry.edgeId;
            selectionInfo.textContent = `Edycja: ${edgeId}`;
        } else {
            selectionInfo.textContent = 'Nowy konektor';
        }
    }

    function extractHistoryIdFromSegmentation(context) {
        const entry = context && typeof context === 'object' ? context.sourceEntry : null;
        if (!entry || typeof entry !== 'object') {
            return null;
        }
        const collected = new Set();
        const push = (value) => {
            if (typeof value === 'string') {
                const trimmed = value.trim();
                if (trimmed) {
                    collected.add(trimmed);
                }
            }
        };
        push(entry.historyId || entry.history_id || entry.id);
        // Spróbuj wyciągnąć token z URL, jeśli brak jawnego historyId
        push(extractTokenFromUrl(entry.url || entry.imageUrl));
        if (entry.meta && typeof entry.meta === 'object') {
            push(entry.meta.historyId || entry.meta.history_id);
            if (entry.meta.source && typeof entry.meta.source === 'object') {
                push(entry.meta.source.historyId);
                push(entry.meta.source.id);
                push(extractTokenFromUrl(entry.meta.source.url || entry.meta.source.imageUrl));
            }
        }
        if (entry.payload && typeof entry.payload === 'object') {
            push(entry.payload.historyId || entry.payload.history_id);
            if (entry.payload.source && typeof entry.payload.source === 'object') {
                push(entry.payload.source.historyId);
                push(entry.payload.source.id);
                push(extractTokenFromUrl(entry.payload.source.url || entry.payload.source.imageUrl));
            }
        }
        const items = Array.from(collected);
        return items.length ? items[0] : null;
    }

    function applySegmentationHistoryId() {
        if (!historyIdInput) {
            return;
        }
        const nextId = extractHistoryIdFromSegmentation(state.segmentationContext);
        const current = trimToNull(historyIdInput.value || '');
        if (!nextId) {
            return;
        }
        if (!current || current === state.autoHistoryId) {
            historyIdInput.value = nextId;
            state.autoHistoryId = nextId;
            setStatus('Przepisano History ID z segmentacji.', 'info');
        }
    }

    async function fillGeometryFromSegmentationSource() {
        if (state.autoGeometryFilled) {
            return;
        }
        if (!geometryInput || geometryInput.value.trim()) {
            return;
        }
        const entry = state.segmentationContext?.sourceEntry;
        const imageUrl = entry?.url || entry?.imageUrl;
        if (!imageUrl) {
            return;
        }
        try {
            const { width, height } = await loadImageSize(imageUrl);
            if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
                return;
            }
            const geom = {
                type: 'polygon',
                points: [
                    [0, 0],
                    [width, 0],
                    [width, height],
                    [0, height],
                ],
            };
            geometryInput.value = safeJsonStringify(geom);
            renderPreviewFromGeometry(geom, null);
            geometryInput.classList.remove('is-invalid');
            state.autoGeometryFilled = true;
            setStatus('Ustawiono ramkę na pełny obraz z segmentacji.', 'info');
        } catch (error) {
            console.warn('[edgeConnectors] Nie udało się odczytać wymiarów obrazu segmentacji', error);
        }
    }

    function toggleFormDisabled(disabled) {
        const inputs = [
            edgeIdInput,
            pageInput,
            labelInput,
            netNameInput,
            sheetIdInput,
            historyIdInput,
            noteInput,
            geometryInput,
            saveBtn,
            resetBtn,
        ];
        inputs.forEach((element) => {
            if (element) {
                element.disabled = Boolean(disabled);
            }
        });
    }

    function renderDetail(entry) {
        if (!detailTitle || !detailJson || !copyBtn) {
            return;
        }
        if (!entry) {
            detailTitle.textContent = 'Nie wybrano wpisu';
            detailJson.textContent = 'Wybierz konektor z listy, aby zobaczyć szczegóły i wczytać go do formularza.';
            copyBtn.disabled = true;
            return;
        }
        const payload = entry.payload && typeof entry.payload === 'object' ? entry.payload : entry;
        const titleParts = [];
        if (payload.edgeId) {
            titleParts.push(payload.edgeId);
        }
        if (payload.page) {
            titleParts.push(`strona ${payload.page}`);
        }
        detailTitle.textContent = titleParts.length ? titleParts.join(' • ') : 'Szczegóły konektora';
        detailJson.textContent = safeJsonStringify(payload);
        copyBtn.disabled = false;
    }

    function renderList() {
        if (!listBody || !countBadge) {
            return;
        }
        listBody.innerHTML = '';
        const entries = [...state.connectors].sort((a, b) => {
            const timeA = new Date(a.updatedAt || a.createdAt || 0).getTime();
            const timeB = new Date(b.updatedAt || b.createdAt || 0).getTime();
            return timeB - timeA;
        });
        countBadge.textContent = String(entries.length);
        if (listEmpty) {
            listEmpty.classList.toggle('hidden', entries.length > 0);
        }
        if (!entries.length) {
            return;
        }
        const fragment = document.createDocumentFragment();
        entries.forEach((entry) => {
            const row = document.createElement('tr');
            row.dataset.entryId = entry.id;
            if (entry.id === state.activeId) {
                row.classList.add('table-active');
            }

            const idCell = document.createElement('td');
            idCell.textContent = entry.edgeId || '—';
            row.appendChild(idCell);

            const pageCell = document.createElement('td');
            pageCell.textContent = entry.page || '—';
            row.appendChild(pageCell);

            const netCell = document.createElement('td');
            netCell.textContent = entry.netName || '—';
            row.appendChild(netCell);

            const labelCell = document.createElement('td');
            labelCell.textContent = entry.label || entry.edgeId || '—';
            row.appendChild(labelCell);

            const updatedCell = document.createElement('td');
            updatedCell.textContent = formatTimestamp(entry.updatedAt || entry.createdAt);
            row.appendChild(updatedCell);

            const actionsCell = document.createElement('td');
            actionsCell.className = 'text-end';

            const editBtn = document.createElement('button');
            editBtn.type = 'button';
            editBtn.className = 'btn btn-link btn-sm';
            editBtn.dataset.action = 'edit';
            editBtn.dataset.entryId = entry.id;
            editBtn.textContent = 'Edytuj';
            actionsCell.appendChild(editBtn);

            const deleteBtn = document.createElement('button');
            deleteBtn.type = 'button';
            deleteBtn.className = 'btn btn-link btn-sm text-danger';
            deleteBtn.dataset.action = 'delete';
            deleteBtn.dataset.entryId = entry.id;
            deleteBtn.textContent = 'Usuń';
            actionsCell.appendChild(deleteBtn);

            row.appendChild(actionsCell);
            fragment.appendChild(row);
        });
        listBody.appendChild(fragment);
    }

    function highlightActiveRow() {
        if (!listBody) {
            return;
        }
        listBody.querySelectorAll('tr').forEach((row) => {
            row.classList.toggle('table-active', row.dataset.entryId === state.activeId);
        });
    }

    async function refreshList({ silent = false } = {}) {
        if (state.loading) {
            return;
        }
        state.loading = true;
        if (refreshBtn) {
            refreshBtn.disabled = true;
        }
        if (!silent) {
            setStatus('Ładowanie konektorów...', 'info');
        }
        try {
            const response = await fetch(API_BASE);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json();
            const items = Array.isArray(data.items) ? data.items : [];
            state.connectors = items;
            state.loadedOnce = true;
            renderList();
            highlightActiveRow();
            setStatus(items.length ? `Załadowano ${items.length} konektorów.` : 'Brak zapisanych konektorów.', items.length ? 'success' : 'muted');
        } catch (error) {
            console.error('[edgeConnectors] Nie udało się pobrać listy konektorów.', error);
            setStatus('Nie udało się pobrać listy konektorów.', 'error');
        } finally {
            state.loading = false;
            if (refreshBtn) {
                refreshBtn.disabled = false;
            }
        }
    }

    function resetForm() {
        state.activeId = null;
        state.activeEntry = null;
        if (form) {
            form.reset();
        }
        if (geometryInput) {
            geometryInput.value = '';
            geometryInput.classList.remove('is-invalid');
        }
        updateSelectionLabel();
        renderDetail(null);
        highlightActiveRow();
        if (state.pdfContext && pageInput && Number.isFinite(state.pdfContext.currentPage)) {
            pageInput.value = String(state.pdfContext.currentPage);
        }
        clearPreview('Brak geometrii');
    }

    function applyEntryToForm(entry) {
        if (!entry) {
            return;
        }
        const payload = entry.payload && typeof entry.payload === 'object' ? entry.payload : entry;
        if (edgeIdInput) {
            edgeIdInput.value = payload.edgeId || '';
        }
        if (pageInput) {
            pageInput.value = payload.page || '';
        }
        if (labelInput) {
            labelInput.value = payload.label || '';
        }
        if (netNameInput) {
            netNameInput.value = payload.netName || '';
        }
        if (sheetIdInput) {
            sheetIdInput.value = payload.sheetId || '';
        }
        if (historyIdInput) {
            historyIdInput.value = payload.historyId || '';
        }
        if (noteInput) {
            noteInput.value = payload.note || '';
        }
        if (geometryInput) {
            geometryInput.value = safeJsonStringify(payload.geometry) || '';
            geometryInput.classList.remove('is-invalid');
        }
        renderPreviewFromGeometry(payload.geometry, payload.meta || payload.metadata || null);
    }

    async function loadEntry(entryId) {
        if (!entryId) {
            return;
        }
        setStatus('Pobieranie szczegółów konektora...', 'info');
        try {
            const response = await fetch(`${API_BASE}/${entryId}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json();
            state.activeId = entryId;
            state.activeEntry = data;
            state.detailCache.set(entryId, data);
            applyEntryToForm(data);
            updateSelectionLabel();
            renderDetail(data);
            highlightActiveRow();
            setStatus('Załadowano konektor do edycji.', 'success');
        } catch (error) {
            console.error('[edgeConnectors] Nie udało się pobrać konektora.', error);
            setStatus('Nie udało się pobrać konektora.', 'error');
        }
    }

    function buildPayloadFromForm() {
        const edgeId = trimToNull(edgeIdInput?.value || '')?.toUpperCase();
        const pageValue = trimToNull(pageInput?.value || '');
        if (!edgeId) {
            throw new Error('Podaj identyfikator krawędzi (A05/B12...).');
        }
        if (!EDGE_ID_PATTERN.test(edgeId)) {
            edgeIdInput?.classList.add('is-invalid');
            throw new Error('Identyfikator musi mieć format A05/B12/C03/D08.');
        }
        edgeIdInput?.classList.remove('is-invalid');
        if (!pageValue) {
            throw new Error('Podaj numer strony.');
        }
        const geometryText = geometryInput?.value ? geometryInput.value.trim() : '';
        if (!geometryText) {
            throw new Error('Uzupełnij geometrię (JSON).');
        }
        let geometry;
        try {
            geometry = JSON.parse(geometryText);
        } catch (error) {
            throw new Error('Geometria musi być poprawnym JSON-em.');
        }
        if (typeof geometry !== 'object' || geometry === null || Array.isArray(geometry)) {
            throw new Error('Geometria powinna być obiektem z polami type/points.');
        }
        geometry = parseGeometry(geometry);
        const segHistoryId = extractHistoryIdFromSegmentation(state.segmentationContext);
        const resolvedHistoryId = trimToNull(historyIdInput?.value || '') || state.autoHistoryId || segHistoryId || undefined;
        if (historyIdInput) {
            historyIdInput.classList.remove('is-invalid');
        }
        if (!resolvedHistoryId) {
            historyIdInput?.classList.add('is-invalid');
            throw new Error('Brak History ID – uzupełnij pole lub wczytaj źródło z segmentacji.');
        }
        const payload = {
            edgeId,
            page: pageValue,
            label: trimToNull(labelInput?.value || '') || undefined,
            netName: trimToNull(netNameInput?.value || '') || undefined,
            sheetId: trimToNull(sheetIdInput?.value || '') || undefined,
            note: trimToNull(noteInput?.value || '') || undefined,
            historyId: resolvedHistoryId,
            geometry,
            metadata: {},
        };
        const context = state.pdfContext || (getPdfContext ? getPdfContext() : null);
        if (context) {
            payload.source = {
                type: 'pdf',
                filename: context.filename || null,
                token: context.token || null,
                page: context.currentPage || null,
                totalPages: context.totalPages || null,
                previewUrl: context.lastImageUrl || null,
            };
            payload.metadata = {
                pageWidthPx: context.pageWidthPx || null,
                pageHeightPx: context.pageHeightPx || null,
                imageDpi: context.imageDpi || null,
            };
        }
        if (payload.metadata && !Object.values(payload.metadata).some((value) => value !== null && value !== undefined)) {
            delete payload.metadata;
        }
        return payload;
    }

    async function handleFormSubmit(event) {
        event?.preventDefault();
        if (state.saving) {
            return;
        }
        let payload;
        try {
            payload = buildPayloadFromForm();
        } catch (error) {
            setStatus(error.message || 'Formularz zawiera błędy.', 'error');
            return;
        }
        state.saving = true;
        toggleFormDisabled(true);
        setStatus(state.activeId ? 'Aktualizowanie konektora...' : 'Dodawanie nowego konektora...', 'info');
        const isUpdate = Boolean(state.activeId);
        const url = isUpdate ? `${API_BASE}/${state.activeId}` : API_BASE;
        const method = isUpdate ? 'PUT' : 'POST';
        try {
            const response = await fetch(url, {
                method,
                headers: {
                    'Content-Type': 'application/json',
                    ...buildAuthHeaders(),
                },
                body: JSON.stringify(payload),
            });
            const data = await response.json();
            if (!response.ok || data.error) {
                throw new Error(data.error || `HTTP ${response.status}`);
            }
            state.activeId = data.id;
            state.activeEntry = data;
            state.detailCache.set(data.id, data);
            const savedHistoryId = trimToNull(data.historyId || data?.payload?.historyId || null);
            if (savedHistoryId) {
                state.autoHistoryId = savedHistoryId;
                if (historyIdInput) {
                    historyIdInput.value = savedHistoryId;
                    historyIdInput.classList.remove('is-invalid');
                }
            }
            applyEntryToForm(data);
            renderDetail(data);
            updateSelectionLabel();
            highlightActiveRow();
            setStatus(
                savedHistoryId
                    ? `${isUpdate ? 'Zaktualizowano' : 'Dodano'} konektor (History ID: ${savedHistoryId}).`
                    : `${isUpdate ? 'Zaktualizowano' : 'Dodano'} konektor (brak History ID w odpowiedzi).`,
                savedHistoryId ? 'success' : 'warning',
            );
            await refreshList({ silent: true });
        } catch (error) {
            console.error('[edgeConnectors] Nie udało się zapisać konektora.', error);
            setStatus('Nie udało się zapisać konektora.', 'error');
        } finally {
            state.saving = false;
            toggleFormDisabled(false);
        }
    }

    async function handleDelete(entryId) {
        if (!entryId || state.deleting) {
            return;
        }
        const confirmed = window.confirm('Czy na pewno chcesz usunąć ten konektor?');
        if (!confirmed) {
            return;
        }
        state.deleting = true;
        setStatus('Usuwanie konektora...', 'warning');
        try {
            const response = await fetch(`${API_BASE}/${entryId}`, {
                method: 'DELETE',
                headers: buildAuthHeaders(),
            });
            const data = await response.json();
            if (!response.ok || data.error) {
                throw new Error(data.error || `HTTP ${response.status}`);
            }
            if (state.activeId === entryId) {
                resetForm();
            }
            await refreshList({ silent: true });
            setStatus('Konektor usunięty.', 'success');
        } catch (error) {
            console.error('[edgeConnectors] Nie udało się usunąć konektora.', error);
            setStatus('Nie udało się usunąć konektora.', 'error');
        } finally {
            state.deleting = false;
        }
    }

    function handleListClick(event) {
        const button = event.target.closest('button[data-action]');
        if (!button) {
            return;
        }
        const entryId = button.dataset.entryId;
        if (!entryId) {
            return;
        }
        if (button.dataset.action === 'edit') {
            void loadEntry(entryId);
        } else if (button.dataset.action === 'delete') {
            void handleDelete(entryId);
        }
    }

    function handleUsePdfClick() {
        const context = state.pdfContext || (getPdfContext ? getPdfContext() : null);
        if (!context) {
            setStatus('Brak aktywnego podglądu PDF.', 'warning');
            return;
        }
        if (pageInput && Number.isFinite(context.currentPage)) {
            pageInput.value = String(context.currentPage);
        }
        // Używamy neutralnego komunikatu niezależnie od źródła (PDF/obraz)
        setStatus('Przepisano numer strony z podglądu.', 'info');
    }

    function handleTemplateInsert() {
        if (!geometryInput) {
            return;
        }
        geometryInput.value = safeJsonStringify(DEFAULT_GEOMETRY_TEMPLATE);
        geometryInput.focus();
        renderPreviewFromGeometry(DEFAULT_GEOMETRY_TEMPLATE);
        geometryInput.classList.remove('is-invalid');
    }

    function parseGeometry(value) {
        if (!value) {
            throw new Error('Brak geometrii.');
        }
        const geom = value.geometry ? value.geometry : value;
        if (typeof geom !== 'object' || geom === null) {
            throw new Error('Geometria musi być obiektem z polami type/points.');
        }
        const points = Array.isArray(geom.points) ? geom.points : null;
        const geomType = geom.type;
        if (!geomType || !ALLOWED_GEOMETRY_TYPES.has(geomType)) {
            throw new Error('Pole geometry.type musi być polygon/rect/polyline.');
        }
        if (!points || !points.length) {
            throw new Error('Pole geometry.points musi zawierać co najmniej 2 punkty.');
        }
        const normalized = points
            .map((p) => (Array.isArray(p) && p.length >= 2 ? [Number(p[0]), Number(p[1])] : null))
            .filter((p) => p && Number.isFinite(p[0]) && Number.isFinite(p[1]));
        if (!normalized.length) {
            throw new Error('Punkty geometrii muszą być liczbami.');
        }
        if (geomType !== 'polyline' && normalized.length < 3) {
            throw new Error('Polygon/rect wymaga co najmniej 3 punktów.');
        }
        if (geomType === 'polyline' && normalized.length < 2) {
            throw new Error('Polyline wymaga co najmniej 2 punktów.');
        }
        const xs = normalized.map((p) => p[0]);
        const ys = normalized.map((p) => p[1]);
        const spanX = Math.max(...xs) - Math.min(...xs);
        const spanY = Math.max(...ys) - Math.min(...ys);
        if (spanX === 0 || spanY === 0) {
            throw new Error('Geometria ma zerowy wymiar — sprawdź punkty.');
        }
        return { type: geomType, points: normalized };
    }

    function clearPreview(message = 'Brak geometrii') {
        if (!preview.ctx || !preview.canvas) {
            return;
        }
        const { width, height } = preview.canvas;
        preview.ctx.save();
        preview.ctx.clearRect(0, 0, width, height);
        preview.ctx.fillStyle = '#f8f9fa';
        preview.ctx.fillRect(0, 0, width, height);
        preview.ctx.strokeStyle = '#dee2e6';
        preview.ctx.strokeRect(0.5, 0.5, width - 1, height - 1);
        if (message) {
            preview.ctx.fillStyle = '#6c757d';
            preview.ctx.font = '12px sans-serif';
            preview.ctx.textAlign = 'center';
            preview.ctx.textBaseline = 'middle';
            preview.ctx.fillText(message, width / 2, height / 2);
        }
        preview.ctx.restore();
    }

    function renderPreviewFromGeometry(geometry, meta = null) {
        if (!preview.ctx || !preview.canvas) {
            return;
        }
        let parsed;
        try {
            parsed = parseGeometry(geometry);
        } catch (error) {
            clearPreview(error?.message || 'Geometria niepoprawna');
            geometryInput?.classList.add('is-invalid');
            setStatus(error?.message || 'Geometria niepoprawna.', 'error');
            return;
        }
        geometryInput?.classList.remove('is-invalid');

        const doc = state.pdfContext || (getPdfContext ? getPdfContext() : null);
        const segSource = state.segmentationContext?.sourceEntry || null;
        const bgUrl = doc?.lastImageUrl
            || segSource?.imageUrl
            || segSource?.url
            || preview.bgUrl
            || null;
        const bgWidth = doc?.pageWidthPx
            || doc?.image?.naturalWidth
            || preview.bgNaturalWidth
            || null;
        const bgHeight = doc?.pageHeightPx
            || doc?.image?.naturalHeight
            || preview.bgNaturalHeight
            || null;
        const { width: canvasW, height: canvasH } = preview.canvas;
        const padding = 10;

        // załaduj tło jeśli dostępne i jeszcze nie wczytane
        if (bgUrl && (!preview.bgImage || preview.bgUrl !== bgUrl)) {
            const img = new Image();
            img.onload = () => {
                preview.bgImage = img;
                preview.bgUrl = bgUrl;
                renderPreviewFromGeometry(parsed, meta);
            };
            img.onerror = () => {
                preview.bgImage = null;
                preview.bgUrl = null;
                clearPreview('Brak podglądu tła');
                setStatus('Nie udało się załadować tła podglądu.', 'warning');
            };
            img.src = cacheBust(bgUrl);
            clearPreview('Ładowanie podglądu...');
            return;
        }

        // przygotuj skalowanie (preferujemy wymiary strony, inaczej skala z geometrii)
        let scale = 1;
        let offsetX = 0;
        let offsetY = 0;

        // Jeśli mamy metadane o wymiarach obrazu źródłowego, przeskaluj geometrię
        let transformed = parsed;
        try {
            const metaSize = Array.isArray(meta?.image_size) ? meta.image_size : null;
            if (metaSize && bgWidth && bgHeight && metaSize.length >= 2) {
                const srcW = Number(metaSize[0]) || 1;
                const srcH = Number(metaSize[1]) || 1;
                const sx = bgWidth / srcW;
                const sy = bgHeight / srcH;
                transformed = {
                    type: parsed.type,
                    points: parsed.points.map((pt) => [pt[0] * sx, pt[1] * sy]),
                };
                console.debug('[edgeConnectors] geometry scaled from meta image_size', { srcW, srcH, sx, sy });
            } else {
                // Heurystyka: jeśli brak meta i wykryta ramka jest bardzo mała względem tła,
                // lepiej wypełnić całą stronę lub skalować tak, by ramka zajęła większą część obrazu
                const xs = parsed.points.map((p) => p[0]);
                const ys = parsed.points.map((p) => p[1]);
                const minX = Math.min(...xs);
                const minY = Math.min(...ys);
                const maxX = Math.max(...xs);
                const maxY = Math.max(...ys);
                const spanX = Math.max(maxX - minX, 1);
                const spanY = Math.max(maxY - minY, 1);
                const areaFrac = (spanX * spanY) / (bgWidth * bgHeight);
                // jeśli wykryta ramka jest mniejsza niż threshold czyni to mało użytecznym, użyj pełnego obrazu
                const FULL_IMAGE_THRESHOLD = 0.10; // 10%
                if (bgWidth && bgHeight && areaFrac < FULL_IMAGE_THRESHOLD) {
                    // Spróbuj najpierw znaleźć tight bbox z zawartości obrazu
                    const contentBox = computeImageContentBBox(preview.bgImage, 8, 250);
                    if (contentBox) {
                        // Sprawdź, czy contentBox nie jest zbyt mały (mogłoby oznaczać artefakt) — w takim przypadku odrzuć go.
                        const contentAreaFrac = (contentBox.w * contentBox.h) / (bgWidth * bgHeight);
                        const MIN_CONTENT_FRAC = 0.003; // 0.3% obrazu
                        if (contentAreaFrac < MIN_CONTENT_FRAC) {
                            console.debug('[edgeConnectors] contentBox too small — ignoring (likely artifact)', { contentAreaFrac, contentBox });
                            transformed = {
                                type: 'polygon',
                                points: [
                                    [0, 0],
                                    [bgWidth, 0],
                                    [bgWidth, bgHeight],
                                    [0, bgHeight],
                                ],
                            };
                        } else {
                            // przeskaluj punkty ramki, żeby pasowały do contentBox
                            const scaleW = contentBox.w / Math.max(spanX, 1);
                            const scaleH = contentBox.h / Math.max(spanY, 1);
                            const scaleFactor = Math.min(scaleW, scaleH);
                            transformed = {
                                type: 'polygon',
                                points: [
                                    [contentBox.x, contentBox.y],
                                    [contentBox.x + contentBox.w, contentBox.y],
                                    [contentBox.x + contentBox.w, contentBox.y + contentBox.h],
                                    [contentBox.x, contentBox.y + contentBox.h],
                                ],
                            };
                            console.debug('[edgeConnectors] geometry replaced with content bbox (heuristic)', { contentBox, contentAreaFrac, areaFrac, spanX, spanY, bgWidth, bgHeight });
                        }
                    } else {
                        transformed = {
                            type: 'polygon',
                            points: [
                                [0, 0],
                                [bgWidth, 0],
                                [bgWidth, bgHeight],
                                [0, bgHeight],
                            ],
                        };
                        console.debug('[edgeConnectors] geometry replaced with full-image bbox fallback (heuristic)', { areaFrac, spanX, spanY, bgWidth, bgHeight });
                    }
                } else if (bgWidth && bgHeight) {
                    // skaluj tak, aby wykryta ramka wypełniła możliwie dużo obrazu (fit by max)
                    const scaleX = bgWidth / spanX;
                    const scaleY = bgHeight / spanY;
                    let scaleFactor = Math.max(scaleX, scaleY);
                    scaleFactor = Math.max(1, Math.min(scaleFactor, 100));
                    transformed = {
                        type: parsed.type,
                        points: parsed.points.map((pt) => [ (pt[0] - minX) * scaleFactor, (pt[1] - minY) * scaleFactor ]),
                    };
                    console.debug('[edgeConnectors] geometry heuristically scaled-to-fill', { scaleFactor, minX, minY, spanX, spanY, bgWidth, bgHeight });
                }
            }
        } catch (err) {
            console.debug('[edgeConnectors] geometry scale from meta failed', err);
            transformed = parsed;
        }

        // Jeśli użytkownik ustawił shrink — zastosuj go do już przekształconej geometrii (nie przed heurystykami),
        // dzięki temu suwak natychmiast wpływa na widoczny podgląd niezależnie od dalszych heurystyk.
        try {
            if (state && state.shrink && state.shrink > 0) {
                transformed = applyShrinkToGeometry(transformed, state.shrink);
                console.debug('[edgeConnectors] applied shrink to transformed geometry', { shrink: state.shrink });
            }
        } catch (err) {
            console.debug('[edgeConnectors] applyShrinkToGeometry failed', err);
        }

        if (bgUrl && preview.bgImage && bgWidth && bgHeight) {
            scale = Math.min((canvasW - padding * 2) / bgWidth, (canvasH - padding * 2) / bgHeight);
            offsetX = (canvasW - bgWidth * scale) / 2;
            offsetY = (canvasH - bgHeight * scale) / 2;
        } else {
            const xs = transformed.points.map((p) => p[0]);
            const ys = transformed.points.map((p) => p[1]);
            const minX = Math.min(...xs);
            const maxX = Math.max(...xs);
            const minY = Math.min(...ys);
            const maxY = Math.max(...ys);
            const spanX = Math.max(maxX - minX, 1);
            const spanY = Math.max(maxY - minY, 1);
            scale = Math.min((canvasW - padding * 2) / spanX, (canvasH - padding * 2) / spanY);
            offsetX = (canvasW - spanX * scale) / 2 - minX * scale;
            offsetY = (canvasH - spanY * scale) / 2 - minY * scale;
        }

        // rysuj tło jeśli dostępne
        clearPreview('');
        if (bgUrl && preview.bgImage && bgWidth && bgHeight) {
            preview.ctx.drawImage(preview.bgImage, offsetX, offsetY, bgWidth * scale, bgHeight * scale);
        }

        // rysuj geometrię nałożoną na tło/skala
        preview.ctx.save();
        preview.ctx.translate(offsetX, offsetY);
        preview.ctx.scale(scale, scale);
        preview.ctx.lineWidth = 2 / scale;
        preview.ctx.strokeStyle = '#008080';
        preview.ctx.fillStyle = 'rgba(0, 128, 128, 0.1)';
        preview.ctx.beginPath();
        transformed.points.forEach((pt, idx) => {
            if (idx === 0) {
                preview.ctx.moveTo(pt[0], pt[1]);
            } else {
                preview.ctx.lineTo(pt[0], pt[1]);
            }
        });
        if (transformed.type === 'polygon' || transformed.type === 'rect') {
            preview.ctx.closePath();
            preview.ctx.fill();
        }
        preview.ctx.stroke();
        preview.ctx.restore();
    }

    function renderPreviewFromForm() {
        const text = geometryInput?.value || '';
        if (!text.trim()) {
            clearPreview('Brak geometrii');
            return;
        }
        try {
            const geom = JSON.parse(text);
            renderPreviewFromGeometry(geom);
            geometryInput?.classList.remove('is-invalid');
        } catch (error) {
            clearPreview('Geometria nie jest poprawnym JSON');
            geometryInput?.classList.add('is-invalid');
            setStatus('Geometria nie jest poprawnym JSON.', 'error');
        }
    }

    function applyShrinkToGeometry(geometry, shrink) {
        if (!geometry || !Array.isArray(geometry.points) || !geometry.points.length) return geometry;
        if (!shrink || shrink <= 0) return geometry;
        // Compute bbox
        const xs = geometry.points.map((p) => p[0]);
        const ys = geometry.points.map((p) => p[1]);
        const minX = Math.min(...xs);
        const maxX = Math.max(...xs);
        const minY = Math.min(...ys);
        const maxY = Math.max(...ys);
        const bw = Math.max(1, maxX - minX);
        const bh = Math.max(1, maxY - minY);
        const dx = Math.round(bw * shrink);
        const dy = Math.round(bh * shrink);
        const nx = Math.max(0, minX + dx);
        const ny = Math.max(0, minY + dy);
        const nw = Math.max(1, bw - 2 * dx);
        const nh = Math.max(1, bh - 2 * dy);
        return {
            type: 'polygon',
            points: [
                [nx, ny],
                [nx + nw, ny],
                [nx + nw, ny + nh],
                [nx, ny + nh],
            ],
        };
    }

    function applyShrinkToPreview() {
        try {
            const text = geometryInput?.value || '';
            if (!text.trim()) return;
            let geom = JSON.parse(text);
            const shrunk = applyShrinkToGeometry(geom, state.shrink);
            renderPreviewFromGeometry(shrunk, state.segmentationContext?.sourceEntry?.meta || null);
        } catch (err) {
            // ignore parse errors
        }
    }

    async function loadDetectedPreview() {
        setStatus('Pobieranie wykrytych konektorów...', 'info');
        try {
            // Upewnij się, że mamy najświeższy kontekst segmentacji (może być winny race condition)
            if (typeof getSegmentationContext === 'function') {
                try {
                    const fresh = getSegmentationContext();
                    if (fresh) {
                        updateSegmentationContext(fresh);
                    }
                } catch (err) {
                    // ignoruj błędy w pobieraniu kontekstu
                    console.debug('[edgeConnectors] getSegmentationContext failed', err);
                }
            }
            const context = state.pdfContext || (getPdfContext ? getPdfContext() : null);
            const seg = state.segmentationContext?.sourceEntry;
            const params = new URLSearchParams();
            const pageCandidate = (context && Number.isFinite(context.currentPage))
                ? context.currentPage
                : seg?.meta?.page || seg?.page || seg?.payload?.page || null;
            if (Number.isFinite(pageCandidate)) {
                params.set('page', pageCandidate);
            }
            const tokenCandidate = (context && context.token)
                || seg?.meta?.source?.token
                || seg?.payload?.source?.token
                || extractTokenFromUrl(seg?.url || seg?.imageUrl);
                const pageForGuess = Number.isFinite(pageCandidate) ? pageCandidate : 1;
                if (tokenCandidate) {
                    params.set('token', tokenCandidate);
                }
                const candidates = [
                    seg?.imageUrl,
                    seg?.url,
                    context?.lastImageUrl,
                ];
                if (tokenCandidate) {
                    candidates.push(`/uploads/${tokenCandidate}_page_${pageForGuess}.png`);
                    candidates.push(`/uploads/${tokenCandidate}.png`);
                }
                loadPreviewFromCandidates(candidates.filter(Boolean));
            if (state.shrink > 0) {
                params.set('shrink', String(state.shrink));
            }
            const query = params.toString() ? `?${params.toString()}` : '';

            // Najpierw próbujemy dedykowanego endpointu detekcji (mock w backendzie)
            let response = await fetch(`${API_BASE}/detect${query}`, { headers: buildAuthHeaders() });
            if (!response.ok) {
                // fallback do zwykłego listowania z includePayload
                response = await fetch(`${API_BASE}?includePayload=1`, { headers: buildAuthHeaders() });
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();
            let items = Array.isArray(data.items) ? data.items : [];

            // Normalizujemy: niektóre mocki mogą zwracać geometry w payload lub bezpośrednio
            let withGeometry = items.filter((item) => (item.payload && item.payload.geometry) || item.geometry);
            if (!withGeometry.length) {
                clearPreview('Brak geometrii');
                setStatus('Brak dostępnych wyników detekcji.', 'warning');
                return;
            }

            withGeometry.sort((a, b) => {
                const tA = new Date(a.updatedAt || a.createdAt || 0).getTime();
                const tB = new Date(b.updatedAt || b.createdAt || 0).getTime();
                return tB - tA;
            });
            const picked = withGeometry[0];

            state.connectors = items;
            state.loadedOnce = true;
            state.activeId = null; // traktujemy wykryty wpis jako szablon do utworzenia nowego
            state.activeEntry = null;
            state.detailCache.set(picked.id, picked);
            renderDetail(picked);
            updateSelectionLabel();
            renderList();
            highlightActiveRow();

            const geom = (picked.payload && picked.payload.geometry) || picked.geometry;
            const meta = (picked.payload && (picked.payload.meta || picked.payload.metadata)) || picked.metadata || {};
            const roi = deriveRoi(meta, geom);
            if (geometryInput) {
                geometryInput.value = safeJsonStringify(geom);
                geometryInput.classList.remove('is-invalid');
            }
            renderPreviewFromGeometry(geom, meta);
            const statusParts = [`Załadowano wykryty konektor ${picked.edgeId || ''}`.trim()];
            if (roi) {
                statusParts.push(`(ROI ${Math.round(roi.w)}x${Math.round(roi.h)} @ ${Math.round(roi.x)},${Math.round(roi.y)})`);
            }
            statusParts.push('(zapis utworzy nowy konektor)');
            setStatus(statusParts.join(' '), 'success');
        } catch (error) {
            console.error('[edgeConnectors] Nie udało się pobrać wykrytych konektorów.', error);
            setStatus('Nie udało się pobrać wykrytych konektorów.', 'error');
        }
    }

    async function handleCopyJson() {
        if (!copyBtn || copyBtn.disabled || !detailJson) {
            return;
        }
        const payloadText = detailJson.textContent || '';
        if (!payloadText.trim()) {
            return;
        }
        if (!navigator.clipboard) {
            setStatus('Przeglądarka nie wspiera schowka.', 'warning');
            return;
        }
        try {
            await navigator.clipboard.writeText(payloadText);
            setStatus('Skopiowano JSON do schowka.', 'success');
        } catch (error) {
            console.error('[edgeConnectors] Nie udało się skopiować JSON.', error);
            setStatus('Nie udało się skopiować JSON.', 'error');
        }
    }

    function updateShrinkDisplay(value) {
        if (shrinkValue) {
            const pct = Math.round((value || 0) * 100);
            shrinkValue.textContent = `${pct}%`;
        }
        if (shrinkSlider) {
            shrinkSlider.value = String(value || 0);
        }
    }

    function wireEvents() {
        refreshBtn?.addEventListener('click', () => {
            void refreshList();
        });
        listBody?.addEventListener('click', handleListClick);
        form?.addEventListener('submit', handleFormSubmit);
        resetBtn?.addEventListener('click', () => {
            resetForm();
            setStatus('Wyczyszczono formularz.', 'info');
        });
        usePdfBtn?.addEventListener('click', handleUsePdfClick);
        geometryTemplateBtn?.addEventListener('click', handleTemplateInsert);
        copyBtn?.addEventListener('click', handleCopyJson);
        geometryInput?.addEventListener('input', renderPreviewFromForm);
        previewMockBtn?.addEventListener('click', () => {
            if (geometryInput && !geometryInput.value.trim()) {
                geometryInput.value = safeJsonStringify(DEFAULT_GEOMETRY_TEMPLATE);
            }
            renderPreviewFromGeometry(DEFAULT_GEOMETRY_TEMPLATE);
            setStatus('Pokazano przykładowy konektor.', 'info');
        });
        previewLoadBtn?.addEventListener('click', () => {
            void loadDetectedPreview();
        });
        shrinkSlider?.addEventListener('input', (event) => {
            const raw = Number.parseFloat(event.target.value);
            const clamped = Number.isFinite(raw) ? Math.min(Math.max(raw, 0), 0.15) : 0;
            state.shrink = clamped;
            updateShrinkDisplay(clamped);
            setStatus('Zmniejszanie ramki dla kolejnego pobrania.', 'info');
            // Zastosuj wartość shrink natychmiast do aktualnego podglądu geometrii
            try {
                applyShrinkToPreview();
            } catch (err) {
                console.debug('[edgeConnectors] applyShrinkToPreview failed', err);
            }
        });
    }

    function updatePdfContext(context) {
        state.pdfContext = context || null;
        preview.bgImage = null;
        preview.bgUrl = null;
        updatePdfPanel();
        if (!state.activeId && pageInput && context && Number.isFinite(context.currentPage)) {
            pageInput.value = String(context.currentPage);
        }
    }

    function updateSegmentationContext(context) {
        // Normalize different segmentation context shapes (lineSegmentation provides { entry: ... })
        const sourceEntry = context?.sourceEntry || context?.entry || null;
        const normalized = context && typeof context === 'object' ? { ...context, sourceEntry } : null;
        state.segmentationContext = normalized;
        console.debug('[edgeConnectors] updateSegmentationContext segSrc=', sourceEntry, 'normalized=', normalized);
        applySegmentationHistoryId();

        // Jeśli kontekst segmentacji zawiera historyId, od razu spróbuj odświeżyć listę konektorów
        // i dopasować wpisy — to usuwa konieczność ręcznego klikania "Odśwież" przez użytkownika.
        try {
            const extracted = extractHistoryIdFromSegmentation(normalized);
            if (extracted) {
                (async () => {
                    try {
                        await refreshList({ silent: true });
                        const normalizedId = String(extracted).toLowerCase();
                        const matches = (state.connectors || [])
                            .map((e) => normalizeEdgeConnectorEntry(e))
                            .filter((e) => e && e.historyIdNormalized === normalizedId);
                        state.edgeConnectorMatches = matches;
                        renderConnectorMatches(matches, { fingerprint: { candidates: [extracted], preferred: extracted } });
                        if (matches.length) {
                            setConnectorStatus(`Powiązano ${matches.length} konektorów (historyId: ${extracted}).`, 'success');
                        } else {
                            setConnectorStatus(`Brak konektorów dla historyId: ${extracted}. Kliknij „Odśwież”, aby spróbować ponownie.`, 'warning');
                        }
                        updateRoiAvailability();
                    } catch (err) {
                        console.debug('[edgeConnectors] auto-refresh connectors failed', err);
                    }
                })();
            }
        } catch (err) {
            console.debug('[edgeConnectors] extractHistoryIdFromSegmentation failed', err);
        }

        const segBg = sourceEntry?.imageUrl || sourceEntry?.url;
        if (segBg) {
            console.debug('[edgeConnectors] updateSegmentationContext loading bg=', segBg);
            loadPreviewFromCandidates([segBg]);
        }
        void fillGeometryFromSegmentationSource();
    }

    function onTabVisible() {
        if (!state.loadedOnce && !state.loading) {
            void refreshList();
        }
        if (typeof getSegmentationContext === 'function') {
            updateSegmentationContext(getSegmentationContext());
        }
    }

    updatePdfPanel();
    updateSelectionLabel();
    renderDetail(null);
    clearPreview('Brak geometrii');
    updateShrinkDisplay(state.shrink);
    wireEvents();
    if (typeof getSegmentationContext === 'function') {
        updateSegmentationContext(getSegmentationContext());
    }

    return {
        updatePdfContext,
        updateSegmentationContext,
        onTabVisible,
        onTabHidden: () => {},
    };
}
