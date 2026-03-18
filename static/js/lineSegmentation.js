const RETOUCH_BUFFER_ENDPOINT = '/processing/retouch-buffer';
const IMPORT_FRAGMENT_ENDPOINT = '/processing/import';
const SEGMENT_LINES_ENDPOINT = '/api/segment/lines';
const SEGMENT_NETLIST_ENDPOINT = '/api/segment/netlist';
const SEGMENT_SPICE_ENDPOINT = '/api/segment/netlist/spice';
const PROCESSING_HISTORY_ENDPOINT = '/processing/history';
const EDGE_CONNECTORS_ENDPOINT = '/api/edge-connectors';
const FIXTURES_INDEX_URL = '/static/fixtures/line-segmentation/index.json';
const SYMBOL_STATUS_DEFAULT = 'Brak detekcji symboli.';
const LINE_HISTORY_TYPES = new Set(['line-segmentation', 'netlist', 'spice-netlist']);

function toggleVisibility(element, placeholder, shouldShow) {
    if (!element || !placeholder) {
        return;
    }
    if (shouldShow) {
        element.classList.remove('hidden');
        placeholder.classList.add('hidden');
    } else {
        element.classList.add('hidden');
        placeholder.classList.remove('hidden');
    }
}

function cacheBustUrl(url) {
    if (!url || typeof url !== 'string') {
        return url;
    }
    if (/^(data|blob):/i.test(url)) {
        return url;
    }
    const token = `_=${Date.now()}`;
    return url.includes('?') ? `${url}&${token}` : `${url}?${token}`;
}

function setDebugList(container, urls) {
    if (!container) {
        return;
    }
    container.innerHTML = '';
    if (!urls || urls.length === 0) {
        const li = document.createElement('li');
        li.className = 'processing-history-empty';
        li.textContent = 'Brak plików debug.';
        container.appendChild(li);
        return;
    }
    urls.forEach((url) => {
        const li = document.createElement('li');
        li.className = 'processing-history-item';
        const link = document.createElement('a');
        link.href = url;
        link.textContent = url;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        li.appendChild(link);
        container.appendChild(li);
    });
}

export function initLineSegmentation(dom = {}, dependencies = {}) {
    const {
        loadRetouchBtn,
        loadToolsBtn,
        loadFileBtn,
        loadFileInput,
        historyList,
        historyRefreshBtn,
        fixtureSelect,
        loadFixtureBtn,
        fixtureInfo,
        runBtn,
        netlistBtn,
        netlistExportBtn,
        storeHistoryCheckbox,
        debugCheckbox,
        binaryCheckbox,
        useConnectorRoiCheckbox,
        roiStatusLabel,
        historyIdLabel,
        statusLabel,
        sourceImage,
        sourcePlaceholder,
        sourceStage,
        zoomInBtn,
        zoomOutBtn,
        zoomResetBtn,
        zoomLabel,
        overlayCanvas,
        overlayToggle,
        symbolOverlayCanvas,
        symbolOverlayToggle,
        symbolOverlayStatus,
        summaryLines,
        summaryNodes,
        summaryTime,
        summaryShape,
        summaryBinary,
        summarySkeleton,
        summaryFlagged,
        debugList,
        resultPre,
        netlistStatus,
        netlistSummaryNodes,
        netlistSummaryEdges,
        netlistSummaryEssential,
        netlistSummaryNonEssential,
        netlistSummaryEndpoints,
        netlistSummaryComponents,
        netlistSummaryCycles,
        netlistPre,
        symbolSection,
        symbolStatus: netlistSymbolStatus,
        symbolCount,
        symbolDetector,
        symbolLatency,
        symbolCapturedAt,
        symbolHistoryLink,
        symbolTableWrapper,
        symbolTableBody,
        symbolTableEmpty,
        connectorStatus,
        connectorRefreshBtn,
        connectorTableWrapper,
        connectorTableBody,
        connectorTableEmpty,
        connectorHint,
        spiceStatus,
        componentSummary,
        componentSummaryTableWrapper,
        componentSummaryTableBody,
        componentSummaryEmpty,
        spicePre,
        spiceDownloadLink,
        logToggle,
        logList,
        logCopyBtn,
        logClearBtn,
        logExport,
        logCategory,
        logNoteInput,
        logFeedback,
        diagnosticPanel,
        diagnosticStatus,
        diagnosticFlaggedList,
        diagnosticStartBtn,
        diagnosticChatBox,
        diagnosticChatLog,
        diagnosticChatInput,
        diagnosticChatSendBtn,
        diagnosticChatCloseBtn,
        highlightClearBtn: diagnosticHighlightClearBtn,
        isolateToggle: diagnosticHighlightIsolate,
    } = dom;

    const { getProcessingOriginal = null, getCanvasRetouchImage = null, diagnosticChat = null } = dependencies;

    const defaultLogCategoryValue = logCategory ? logCategory.value : '';

    const sourceObservers = new Set();

    const state = {
        sourceEntry: null,
        tabVisible: false,
        sourceOrigin: null,
        fixtures: [],
        fixturesLoaded: false,
        fixturesLoading: false,
        fixturesError: false,
        selectedFixtureId: null,
        activeFixtureId: null,
        localFileUrl: null,
        pendingLocalFile: null,
        lastResult: null,
        lastNetlist: null,
        lastSpice: null,
        spiceDownloadUrl: null,
        overlayEnabled: true,
        symbolOverlayEnabled: Boolean(symbolOverlayToggle ? symbolOverlayToggle.checked : false),
        zoomLevel: 1,
        pan: { x: 0, y: 0 },
        isPanning: false,
        pointerId: null,
        panStart: { x: 0, y: 0 },
        baseOffset: { x: 0, y: 0 },
        offsetReady: false,
        panAtPointerStart: { x: 0, y: 0 },
        panMoved: false,
        suppressClick: false,
        logEnabled: false,
        loggedPoints: [],
        logFeedbackTimer: null,
        logSequence: 0,
        activeLogEntryId: null,
        segmentIndex: new Map(),
        highlightedSegmentId: null,
        isolateHighlight: false,
        edgeConnectorRoiAvailable: false,
        symbolOverlayEntry: null,
        symbolOverlaySource: null,
        symbolOverlayDetector: null,
        symbolOverlayRequestId: 0,
        symbolDetections: [],
        symbolDetectionIndex: [],
        symbolDetectionIndexLoaded: false,
        symbolDetectionIndexPromise: null,
        symbolDetectionCache: new Map(),
        componentAssignments: [],
        netlistSymbols: [],
        symbolSummary: null,
        symbolListActiveKey: null,
        symbolOverlayActiveKey: null,
        historyEntries: [],
        historyLoaded: false,
        historyLoading: false,
        lastAutoHistoryId: null,
        edgeConnectorEntries: [],
        edgeConnectorMatches: [],
        edgeConnectorLoading: false,
        edgeConnectorLastFetch: 0,
        edgeConnectorFingerprint: null,
        edgeConnectorRoi: null,
    };

    function getHistoryTimestamp(entry) {
        const createdAt = entry?.meta?.createdAt || entry?.createdAt;
        if (!createdAt) {
            return 0;
        }
        const parsed = Date.parse(createdAt);
        return Number.isNaN(parsed) ? 0 : parsed;
    }

    function renderHistoryEntries() {
        if (!historyList) {
            return;
        }
        historyList.innerHTML = '';
        if (!state.historyEntries.length) {
            const empty = document.createElement('li');
            empty.className = 'processing-history-empty';
            empty.textContent = 'Brak zapisanych wyników segmentacji.';
            historyList.append(empty);
            return;
        }

        const sorted = [...state.historyEntries].sort((a, b) => getHistoryTimestamp(b) - getHistoryTimestamp(a));

        sorted.forEach((entry) => {
            if (!entry || typeof entry !== 'object') {
                return;
            }
            const item = document.createElement('li');
            item.className = 'processing-history-item';

            const thumb = document.createElement('div');
            thumb.className = 'processing-history-thumb';
            thumb.dataset.empty = 'true';
            const typeLabel = entry?.meta?.typeLabel
                || (entry.type === 'line-segmentation'
                    ? 'Segmentacja'
                    : entry.type === 'netlist'
                        ? 'Netlista'
                        : entry.type === 'spice-netlist'
                            ? 'SPICE'
                            : 'Historia');
            thumb.textContent = typeLabel;

            const info = document.createElement('div');
            const title = document.createElement('div');
            title.className = 'fw-semibold';
            title.textContent = entry.label || typeLabel;
            info.append(title);

            const details = [];
            const createdAt = entry?.meta?.createdAt || entry?.createdAt;
            if (createdAt) {
                const createdDate = new Date(createdAt);
                details.push(formatTimestamp(createdAt));
            }
            if (entry?.meta?.lines) {
                details.push(`Odcinki: ${entry.meta.lines}`);
            }
            if (entry?.meta?.nodes) {
                details.push(`Węzły: ${entry.meta.nodes}`);
            }
            if (entry?.meta?.components) {
                details.push(`Komponenty: ${entry.meta.components}`);
            }
            if (details.length) {
                const meta = document.createElement('p');
                meta.className = 'processing-history-meta';
                meta.textContent = details.join(' • ');
                info.append(meta);
            }

            const actions = document.createElement('div');
            actions.className = 'processing-history-actions';
            if (entry.url) {
                const openLink = document.createElement('a');
                openLink.className = 'btn btn-outline-primary btn-sm';
                openLink.href = entry.url;
                openLink.target = '_blank';
                openLink.rel = 'noopener noreferrer';
                openLink.textContent = 'Otwórz';
                actions.append(openLink);
            } else {
                const disabledBtn = document.createElement('button');
                disabledBtn.type = 'button';
                disabledBtn.className = 'btn btn-outline-secondary btn-sm';
                disabledBtn.disabled = true;
                disabledBtn.textContent = 'Brak pliku';
                actions.append(disabledBtn);
            }

            item.append(thumb, info, actions);
            historyList.append(item);
        });
    }

    function setHistoryEntries(entries) {
        if (Array.isArray(entries)) {
            state.historyEntries = entries.filter(
                (entry) => entry && typeof entry === 'object' && LINE_HISTORY_TYPES.has(entry.type),
            );
        } else {
            state.historyEntries = [];
        }
        state.historyLoaded = true;
        renderHistoryEntries();
        autoSelectLatestHistorySource({ allowWhenFixture: true });
    }

    function upsertHistoryEntry(entry) {
        if (!entry || typeof entry !== 'object' || !LINE_HISTORY_TYPES.has(entry.type)) {
            return;
        }
        const entries = state.historyEntries.slice();
        const existingIndex = entries.findIndex((item) => item?.id === entry.id);
        if (existingIndex >= 0) {
            entries[existingIndex] = entry;
        } else {
            entries.push(entry);
        }
        state.historyEntries = entries;
        state.historyLoaded = true;
        renderHistoryEntries();
        autoSelectLatestHistorySource({ allowWhenFixture: true });
    }

    async function fetchHistoryEntries() {
        if (state.historyLoading) {
            return;
        }
        state.historyLoading = true;
        if (historyRefreshBtn) {
            historyRefreshBtn.disabled = true;
        }
        try {
            const response = await fetch(`${PROCESSING_HISTORY_ENDPOINT}?scope=line-segmentation`, {
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
            console.error('Nie udało się pobrać historii segmentacji', error);
            if (!state.historyLoaded) {
                setHistoryEntries([]);
            }
        } finally {
            state.historyLoading = false;
            if (historyRefreshBtn) {
                historyRefreshBtn.disabled = false;
            }
        }
    }

    function normalizeHistorySourceEntry(entry) {
        if (!entry || typeof entry !== 'object') {
            return null;
        }
        const meta = entry.meta && typeof entry.meta === 'object' ? entry.meta : {};
        const payloadSource = entry.payload && typeof entry.payload === 'object' ? entry.payload.source : null;
        const metaSource = meta.source && typeof meta.source === 'object' ? meta.source : null;
        const inputSource = meta.input && typeof meta.input === 'object' ? meta.input : null;
        const source = payloadSource || metaSource || inputSource || null;
        const urlCandidates = [
            source?.imageUrl,
            source?.url,
            source?.previewUrl,
            meta.imageUrl,
            meta.previewUrl,
            entry.imageUrl,
            entry.previewUrl,
            entry.url,
            source?.originalUrl,
            meta.originalUrl,
        ];
        const resolvedUrl = urlCandidates.find((candidate) => isImageUrl(candidate) && !/^data:/i.test(candidate));
        if (!resolvedUrl) {
            return null;
        }
+        console.debug('[lineSeg] normalizeHistorySourceEntry resolvedUrl ->', resolvedUrl, 'entryId=', entry?.id);
        const fixtureUrl = pickFixtureUrl({
            url: resolvedUrl,
            imageUrl: source?.imageUrl || entry.imageUrl || entry.url || entry.previewUrl,
            previewUrl: entry.previewUrl || meta.previewUrl,
            originalUrl: source?.originalUrl || meta.originalUrl,
        });
        if (fixtureUrl) {
            return null;
        }
        const originalImage = [
            source?.originalUrl,
            meta.originalUrl,
            resolvedUrl,
        ].find((candidate) => isImageUrl(candidate));
        const historyId = entry.id
            || source?.historyId
            || source?.id
            || meta.historyId
            || meta.history_id
            || extractTokenFromUrl(resolvedUrl);
        const label = source?.label
            || source?.filename
            || meta.filename
            || entry.label
            || 'Ostatni import';
        return {
            url: resolvedUrl,
            imageUrl: source?.imageUrl || resolvedUrl,
            previewUrl: entry.previewUrl || source?.previewUrl || meta.previewUrl || null,
            originalUrl: originalImage || resolvedUrl,
            historyId,
            label,
            meta: {
                ...meta,
                source: source || metaSource || null,
            },
        };
    }

    function loadFromProcessingOriginal() {
        if (typeof getProcessingOriginal !== 'function') {
            return false;
        }
        const original = getProcessingOriginal();
        if (!original) {
            return false;
        }
        const candidates = [
            original.url,
            original.imageUrl,
            original.previewUrl,
            original.originalUrl,
        ];
        const resolved = candidates.find((candidate) => (isImageUrl(candidate) || /^data:image\//i.test(candidate)) && typeof candidate === 'string');
        if (!resolved) {
            return false;
        }
        console.debug('[lineSeg] loadFromProcessingOriginal resolved ->', resolved);
        const entry = {
            ...original,
            url: resolved,
            imageUrl: original.imageUrl || resolved,
            previewUrl: original.previewUrl || null,
            originalUrl: original.originalUrl || resolved,
            label: original.label || original.filename || 'Ostatni obraz',
        };
        updateSource(entry, 'processing-original');
        setStatus('Załadowano obraz z detekcji symboli.');
        return true;
    }

    function normalizeSymbolHistoryEntry(entry) {
        if (!entry || typeof entry !== 'object') {
            return null;
        }
        const src = entry.source && typeof entry.source === 'object' ? entry.source : entry.meta?.source || null;
        if (!src || typeof src !== 'object') {
            return null;
        }
        const urlCandidates = [
            src.imageUrl,
            src.url,
            src.previewUrl,
            src.originalUrl,
        ];
        const resolved = urlCandidates.find((candidate) => isImageUrl(candidate) || /^data:image\//i.test(candidate));
        if (!resolved) {
            return null;
        }
+        console.debug('[lineSeg] normalizeSymbolHistoryEntry resolved ->', resolved, 'entryId=', entry?.id);
        return {
            url: resolved,
            imageUrl: src.imageUrl || resolved,
            previewUrl: src.previewUrl || null,
            originalUrl: src.originalUrl || resolved,
            historyId: src.historyId || entry.id || null,
            label: src.label || src.filename || entry.label || 'Ostatni wynik detekcji',
            meta: entry.meta ? { ...entry.meta } : undefined,
        };
    }

    function autoSelectLatestHistorySource({ allowWhenFixture = false } = {}) {
        const hasUserSource = state.sourceEntry
            && state.sourceOrigin
            && state.sourceOrigin !== 'fixture'
            && state.sourceOrigin !== 'history-auto';
        const hasLocalPending = state.pendingLocalFile || state.sourceOrigin === 'local';
        if (hasUserSource || hasLocalPending) {
            console.debug('[lineSeg] autoSelectLatestHistorySource skipping: user source or pending local present', { hasUserSource, hasLocalPending, sourceOrigin: state.sourceOrigin });
            return false;
        }
        if (state.sourceEntry && state.sourceOrigin === 'fixture' && !allowWhenFixture) {
            return false;
        }
        const sorted = [...state.historyEntries].sort((a, b) => getHistoryTimestamp(b) - getHistoryTimestamp(a));
        for (const entry of sorted) {
            const normalized = normalizeHistorySourceEntry(entry);
            if (!normalized) {
                continue;
            }
            if (state.sourceEntry && normalized.historyId && state.sourceEntry.historyId === normalized.historyId) {
                state.lastAutoHistoryId = normalized.historyId;
                return false;
            }
            if (state.lastAutoHistoryId && normalized.historyId && state.lastAutoHistoryId === normalized.historyId) {
                return false;
            }
            console.debug('[lineSeg] autoSelectLatestHistorySource selecting', { historyId: normalized.historyId, url: normalized.url, entryId: entry?.id });
            updateSource(normalized, 'history-auto');
            state.lastAutoHistoryId = normalized.historyId || entry.id || null;
            setStatus(`Załadowano ostatni import (${normalized.label || 'historia'}).`);
            return true;
        }
        return false;
    }

    function cloneSourceContext(context) {
        if (!context) {
            return null;
        }
        const { entry, ...rest } = context;
        return {
            ...rest,
            entry: entry ? { ...entry } : null,
        };
    }

    function buildSourceContext() {
        if (!state.sourceEntry) {
            return null;
        }
        const requiresUpload = state.sourceOrigin === 'local' && Boolean(state.pendingLocalFile);
        return {
            entry: { ...state.sourceEntry },
            origin: state.sourceOrigin || null,
            requiresUpload,
            ready: !requiresUpload,
        };
    }

    const overlayCtx = overlayCanvas ? overlayCanvas.getContext('2d') : null;
    const symbolOverlayCtx = symbolOverlayCanvas ? symbolOverlayCanvas.getContext('2d') : null;
    const overlayStyles = {
        essential: {
            radius: 7,
            stroke: 'rgba(239, 68, 68, 0.9)',
            strokeWidth: 2.4,
            ringStroke: 'rgba(239, 68, 68, 0.35)',
            ringWidth: 1.4,
            ringOffset: 3.5,
        },
        non_essential: {
            radius: 6,
            stroke: 'rgba(234, 179, 8, 0.9)',
            strokeWidth: 2.2,
        },
        endpoint: {
            radius: 5,
            stroke: 'rgba(59, 130, 246, 0.9)',
            strokeWidth: 2.2,
        },
        isolated: {
            radius: 4,
            stroke: 'rgba(107, 114, 128, 0.9)',
            strokeWidth: 2.1,
        },
        unspecified: {
            radius: 4,
            stroke: 'rgba(148, 163, 184, 0.72)',
            strokeWidth: 2.1,
        },
    };
    const ZOOM_MIN = 0.25;
    const ZOOM_MAX = 4;
    const ZOOM_STEP = 0.15;
    const LOG_LIST_PREVIEW_LIMIT = 12;
    const LOG_STORAGE_LIMIT = 200;
    const LOG_TAG_LABELS = {
        false_endpoint: 'Fałszywa końcówka',
        text: 'Tekst / opis',
        junction: 'Węzeł poprawny',
        noise: 'Szum / artefakt',
    };

    function pickFixtureUrl(entry) {
        if (!entry || typeof entry !== 'object') {
            return null;
        }
        const candidates = [
            entry.fixtureUrl,
            entry.originalUrl,
            entry.meta?.originalUrl,
            entry.meta?.source?.originalUrl,
            entry.url,
            entry.imageUrl,
            entry.previewUrl,
        ];
        return candidates.find(
            (candidate) => candidate
                && typeof candidate === 'string'
                && candidate.includes('/static/fixtures/line-segmentation/'),
        ) || null;
    }

    function isImageUrl(candidate) {
        if (!candidate || typeof candidate !== 'string') {
            return false;
        }
        if (/\.json(?:$|[?#])/i.test(candidate)) {
            return false;
        }
        return /\.(png|jpe?g|webp|bmp|tiff?)($|[?#])/i.test(candidate);
    }

    function extractTokenFromUrl(url) {
        if (!url || typeof url !== 'string') {
            return null;
        }
        try {
            const parsed = new URL(url, window.location.origin);
            const filename = (parsed.pathname || '').split('/').pop() || '';
            const match = filename.match(/^([a-zA-Z0-9]+)(?:_[^.]*)?\./);
            return match ? match[1] : null;
        } catch (error) {
            return null;
        }
    }

    function hasSourceImage() {
        return Boolean(sourceImage && !sourceImage.classList.contains('hidden'));
    }

    function applyTransforms() {
        const translate = `translate(${state.pan.x}px, ${state.pan.y}px)`;
        const scale = `scale(${state.zoomLevel})`;
        if (sourceImage) {
            sourceImage.style.transform = `${translate} ${scale}`;
            sourceImage.style.transformOrigin = 'top left';
        }
        if (overlayCanvas) {
            overlayCanvas.style.transform = `${translate} ${scale}`;
            overlayCanvas.style.transformOrigin = 'top left';
        }
        if (symbolOverlayCanvas) {
            symbolOverlayCanvas.style.transform = `${translate} ${scale}`;
            symbolOverlayCanvas.style.transformOrigin = 'top left';
        }
    }

    function measureBaseOffset() {
        state.offsetReady = false;
        if (!sourceImage || !sourceStage || sourceImage.classList.contains('hidden')) {
            state.baseOffset = { x: 0, y: 0 };
            return;
        }

        let offsetLeft = sourceImage.offsetLeft;
        let offsetTop = sourceImage.offsetTop;
        let current = sourceImage.offsetParent;

        while (current && current !== sourceStage) {
            offsetLeft += current.offsetLeft;
            offsetTop += current.offsetTop;
            current = current.offsetParent;
        }

        if (current !== sourceStage && sourceStage) {
            const stageRect = sourceStage.getBoundingClientRect();
            const imageRect = sourceImage.getBoundingClientRect();
            offsetLeft = imageRect.left - stageRect.left - state.pan.x;
            offsetTop = imageRect.top - stageRect.top - state.pan.y;
        }

        state.baseOffset = {
            x: offsetLeft,
            y: offsetTop,
        };
        state.offsetReady = true;
    }

    function markSourceStageEmpty(isEmpty) {
        if (!sourceStage) {
            return;
        }
        sourceStage.classList.toggle('is-empty', Boolean(isEmpty));
    }

    function getStagePointFromEvent(event) {
        if (!sourceStage) {
            return null;
        }
        const rect = sourceStage.getBoundingClientRect();
        return {
            x: sourceStage.scrollLeft + (event.clientX - rect.left),
            y: sourceStage.scrollTop + (event.clientY - rect.top),
        };
    }

    function stagePointToImage(point) {
        if (!point || !state.offsetReady) {
            return null;
        }
        const baseX = state.baseOffset.x || 0;
        const baseY = state.baseOffset.y || 0;
        return {
            x: (point.x - baseX - state.pan.x) / state.zoomLevel,
            y: (point.y - baseY - state.pan.y) / state.zoomLevel,
        };
    }

    function toRounded(value, fractionDigits = 2) {
        return Number.parseFloat(Number(value).toFixed(fractionDigits));
    }

    function truncateText(value, maxLength = 48) {
        if (typeof value !== 'string') {
            return value;
        }
        if (value.length <= maxLength) {
            return value;
        }
        return `${value.slice(0, Math.max(0, maxLength - 3))}...`;
    }

    function notifySourceObservers(contextOverride) {
        if (sourceObservers.size === 0) {
            return;
        }
        const effectiveContext = contextOverride === undefined ? buildSourceContext() : contextOverride;
        const payload = cloneSourceContext(effectiveContext);
        sourceObservers.forEach((observer) => {
            try {
                observer(payload);
            } catch (error) {
                console.error('Błąd powiadamiania obserwatora źródła segmentacji', error);
            }
        });
    }

    function registerSourceObserver(observer) {
        if (typeof observer !== 'function') {
            return () => {};
        }
        sourceObservers.add(observer);
        try {
            observer(cloneSourceContext(buildSourceContext()));
        } catch (error) {
            console.error('Błąd w inicjalnym powiadomieniu obserwatora źródła segmentacji', error);
        }
        return () => {
            sourceObservers.delete(observer);
        };
    }

    function getSourceContext() {
        return cloneSourceContext(buildSourceContext());
    }

    function ensureSourceUploaded() {
        return ensureRemoteSource();
    }

    function setActiveLogEntry(entryId) {
        state.activeLogEntryId = entryId ?? null;
    }

    function findLogEntryIndexById(entryId) {
        if (!entryId) {
            return -1;
        }
        return state.loggedPoints.findIndex((entry) => entry.id === entryId);
    }

    function getActiveLogEntry() {
        const index = findLogEntryIndexById(state.activeLogEntryId);
        if (index === -1) {
            return null;
        }
        return state.loggedPoints[index];
    }

    function ensureActiveLogEntry() {
        if (!state.activeLogEntryId && state.loggedPoints.length > 0) {
            state.activeLogEntryId = state.loggedPoints[0].id;
        }
        return getActiveLogEntry();
    }

    function updateZoomUI() {
        const active = hasSourceImage() && state.offsetReady;
        if (zoomLabel) {
            zoomLabel.textContent = active ? `${Math.round(state.zoomLevel * 100)}%` : '--%';
        }
        if (zoomInBtn) {
            zoomInBtn.disabled = !active || state.zoomLevel >= ZOOM_MAX - 0.001;
        }
        if (zoomOutBtn) {
            zoomOutBtn.disabled = !active || state.zoomLevel <= ZOOM_MIN + 0.001;
        }
        if (zoomResetBtn) {
            const isDefault = Math.abs(state.zoomLevel - 1) < 0.001 && Math.abs(state.pan.x) < 0.5 && Math.abs(state.pan.y) < 0.5;
            zoomResetBtn.disabled = !active || isDefault;
        }
    }

    function resetViewTransform() {
        state.zoomLevel = 1;
        state.pan = { x: 0, y: 0 };
        applyTransforms();
        updateZoomUI();
    }

    function stageCenterPoint() {
        if (!sourceStage) {
            return null;
        }
        return {
            x: sourceStage.scrollLeft + sourceStage.clientWidth / 2,
            y: sourceStage.scrollTop + sourceStage.clientHeight / 2,
        };
    }

    function stageHasScrollableOverflow() {
        if (!sourceStage) {
            return false;
        }
        const scrollableY = Math.abs(sourceStage.scrollHeight - sourceStage.clientHeight) > 1;
        const scrollableX = Math.abs(sourceStage.scrollWidth - sourceStage.clientWidth) > 1;
        return scrollableY || scrollableX;
    }

    function updateZoom(delta, focusPoint = null) {
        if (!hasSourceImage() || !state.offsetReady) {
            return;
        }
        const prevLevel = state.zoomLevel;
        const nextLevel = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, prevLevel + delta));
        if (Math.abs(nextLevel - prevLevel) < 0.001) {
            return;
        }

        if (focusPoint) {
            const baseX = state.baseOffset.x || 0;
            const baseY = state.baseOffset.y || 0;
            const offsetX = focusPoint.x - baseX - state.pan.x;
            const offsetY = focusPoint.y - baseY - state.pan.y;
            state.pan.x = focusPoint.x - baseX - (offsetX * nextLevel) / prevLevel;
            state.pan.y = focusPoint.y - baseY - (offsetY * nextLevel) / prevLevel;
        }

        state.zoomLevel = nextLevel;
        applyTransforms();
        updateZoomUI();
    }

    function beginPan(event) {
        if (!hasSourceImage() || !sourceStage || !state.offsetReady) {
            return;
        }
        const isPrimaryButton = event.button === 0;
        const isMiddleButton = event.button === 1;
        if (!isPrimaryButton && !isMiddleButton) {
            return;
        }
        const allowPanWithoutZoom = stageHasScrollableOverflow();
        if (state.zoomLevel <= 1.001 && !allowPanWithoutZoom) {
            return;
        }
        if (state.logEnabled && isPrimaryButton && !event.shiftKey) {
            return;
        }
    if (event.target.closest('.overlay-legend-panel') || event.target.closest('.processing-toolbar') || event.target.closest('button')) {
            return;
        }
        event.preventDefault();
        state.isPanning = true;
        state.pointerId = event.pointerId;
        state.panStart = {
            x: event.clientX - state.pan.x,
            y: event.clientY - state.pan.y,
        };
        state.panAtPointerStart = { x: state.pan.x, y: state.pan.y };
        state.panMoved = false;
        try {
            sourceStage.setPointerCapture(event.pointerId);
        } catch (error) {
            console.debug('Pointer capture failed', error);
        }
        sourceStage.classList.add('is-panning');
    }

    function continuePan(event) {
        if (!state.isPanning || event.pointerId !== state.pointerId) {
            return;
        }
        state.pan.x = event.clientX - state.panStart.x;
        state.pan.y = event.clientY - state.panStart.y;
        if (!state.panMoved) {
            const deltaX = Math.abs(state.pan.x - state.panAtPointerStart.x);
            const deltaY = Math.abs(state.pan.y - state.panAtPointerStart.y);
            if (deltaX > 1.5 || deltaY > 1.5) {
                state.panMoved = true;
            }
        }
        applyTransforms();
    }

    function endPan(event) {
        if (event.pointerId !== state.pointerId) {
            return;
        }
        state.isPanning = false;
        state.pointerId = null;
        if (sourceStage) {
            sourceStage.classList.remove('is-panning');
            try {
                sourceStage.releasePointerCapture(event.pointerId);
            } catch (error) {
                console.debug('Pointer capture already released', error);
            }
        }
        if (state.panMoved) {
            state.suppressClick = true;
            window.setTimeout(() => {
                state.suppressClick = false;
            }, 0);
        }
        state.panMoved = false;
        updateZoomUI();
    }

    function handleWheel(event) {
        if (!hasSourceImage() || !sourceStage || !state.offsetReady) {
            return;
        }
    if (event.target.closest('.overlay-legend-panel')) {
            return;
        }
        const stageScrollable = stageHasScrollableOverflow();
        const wantsZoom = event.ctrlKey || event.metaKey || event.altKey || !stageScrollable;
        if (!wantsZoom) {
            return;
        }
        event.preventDefault();
        const rect = sourceStage.getBoundingClientRect();
        const focus = {
            x: sourceStage.scrollLeft + (event.clientX - rect.left),
            y: sourceStage.scrollTop + (event.clientY - rect.top),
        };
        const delta = event.deltaY < 0 ? ZOOM_STEP : -ZOOM_STEP;
        updateZoom(delta, focus);
    }

    function wireZoomControls() {
        if (sourceStage) {
            sourceStage.classList.add('zoomable');
            sourceStage.addEventListener('pointerdown', beginPan);
            sourceStage.addEventListener('pointermove', continuePan);
            sourceStage.addEventListener('pointerup', endPan);
            sourceStage.addEventListener('pointercancel', endPan);
            sourceStage.addEventListener('pointerleave', (event) => {
                if (state.isPanning) {
                    endPan(event);
                }
            });
            sourceStage.addEventListener('wheel', handleWheel, { passive: false });
            sourceStage.addEventListener('click', handleStageClick);
            sourceStage.addEventListener('contextmenu', (event) => event.preventDefault());
        }
        if (zoomInBtn) {
            zoomInBtn.addEventListener('click', () => {
                const focus = stageCenterPoint();
                updateZoom(ZOOM_STEP, focus);
            });
        }
        if (zoomOutBtn) {
            zoomOutBtn.addEventListener('click', () => {
                const focus = stageCenterPoint();
                updateZoom(-ZOOM_STEP, focus);
            });
        }
        if (zoomResetBtn) {
            zoomResetBtn.addEventListener('click', () => {
                if (!hasSourceImage()) {
                    return;
                }
                resetViewTransform();
            });
        }
    }

    function clearCanvas(canvas, ctx) {
        if (!canvas) {
            return;
        }
        const context = ctx || (typeof canvas.getContext === 'function' ? canvas.getContext('2d') : null);
        if (context) {
            context.clearRect(0, 0, canvas.width || 0, canvas.height || 0);
        }
        canvas.width = 0;
        canvas.height = 0;
        canvas.classList.add('hidden');
        canvas.style.left = '0px';
        canvas.style.top = '0px';
    }

    function prepareCanvasGeometry(canvas) {
        if (!canvas || !sourceImage || sourceImage.classList.contains('hidden')) {
            return null;
        }
        const naturalWidth = Number(sourceImage.naturalWidth);
        const naturalHeight = Number(sourceImage.naturalHeight);
        const displayWidth = Number(sourceImage.clientWidth);
        const displayHeight = Number(sourceImage.clientHeight);
        if (!naturalWidth || !naturalHeight || !displayWidth || !displayHeight) {
            return null;
        }
        canvas.width = displayWidth;
        canvas.height = displayHeight;
        canvas.style.width = `${displayWidth}px`;
        canvas.style.height = `${displayHeight}px`;
        canvas.style.left = `${sourceImage.offsetLeft}px`;
        canvas.style.top = `${sourceImage.offsetTop}px`;
        canvas.classList.remove('hidden');
        return {
            scaleX: displayWidth / naturalWidth,
            scaleY: displayHeight / naturalHeight,
        };
    }

    function clearOverlay() {
        clearCanvas(overlayCanvas, overlayCtx);
        applyTransforms();
    }

    function clearSymbolOverlay() {
        clearCanvas(symbolOverlayCanvas, symbolOverlayCtx);
        applyTransforms();
    }

    function resetSymbolOverlayState() {
        state.symbolOverlayEntry = null;
        state.symbolOverlaySource = null;
        state.symbolOverlayDetector = null;
        state.symbolDetections = [];
        state.symbolOverlayActiveKey = null;
        state.symbolListActiveKey = null;
        updateSymbolTableSelection();
        renderComponentAssignments([]);
    }

    function normalizePosition(position) {
        if (!position) {
            return null;
        }
        if (Array.isArray(position) && position.length >= 2) {
            const x = Number(position[0]);
            const y = Number(position[1]);
            if (Number.isFinite(x) && Number.isFinite(y)) {
                return { x, y };
            }
            return null;
        }
        if (typeof position === 'object') {
            const maybeX = Number(position.x ?? position[0]);
            const maybeY = Number(position.y ?? position[1]);
            if (Number.isFinite(maybeX) && Number.isFinite(maybeY)) {
                return { x: maybeX, y: maybeY };
            }
        }
        return null;
    }

    function extractAttachments(node) {
        if (!node) {
            return [];
        }
        if (Array.isArray(node.attached_segments)) {
            return node.attached_segments;
        }
        if (Array.isArray(node.attachedSegments)) {
            return node.attachedSegments;
        }
        return [];
    }

    function normalizeClassification(value, degree) {
        if (typeof value === 'string') {
            const normalized = value.trim().toLowerCase();
            if (normalized === 'essential') {
                return 'essential';
            }
            if (normalized === 'non_essential' || normalized === 'non-essential' || normalized === 'nonessential') {
                return 'non_essential';
            }
            if (normalized === 'endpoint' || normalized === 'endpoints') {
                return 'endpoint';
            }
            if (normalized === 'isolated') {
                return 'isolated';
            }
        }
        if (typeof degree === 'number') {
            if (degree >= 3) {
                return 'essential';
            }
            if (degree === 2) {
                return 'non_essential';
            }
            if (degree === 1) {
                return 'endpoint';
            }
            if (degree === 0) {
                return 'isolated';
            }
        }
        return 'unspecified';
    }

    function normalizeDetectionBox(detection) {
        if (!detection || typeof detection !== 'object') {
            return null;
        }
        if (Array.isArray(detection.bbox) && detection.bbox.length >= 4) {
            const [rawX, rawY, rawWidth, rawHeight] = detection.bbox;
            const x = Number(rawX);
            const y = Number(rawY);
            const width = Number(rawWidth);
            const height = Number(rawHeight);
            if ([x, y, width, height].every(Number.isFinite)) {
                return { x, y, width, height };
            }
        }
        const box = detection.box;
        if (box && typeof box === 'object') {
            const x = Number(box.x ?? box.left ?? box[0]);
            const y = Number(box.y ?? box.top ?? box[1]);
            const width = Number(box.width ?? box.w ?? box[2]);
            const height = Number(box.height ?? box.h ?? box[3]);
            if ([x, y, width, height].every(Number.isFinite)) {
                return { x, y, width, height };
            }
        }
        return null;
    }

    function symbolDetectionKey(detection, fallbackIndex = null) {
        if (!detection || typeof detection !== 'object') {
            return fallbackIndex !== null && fallbackIndex !== undefined ? `index-${fallbackIndex}` : null;
        }
        if (detection.id !== undefined && detection.id !== null && detection.id !== '') {
            return String(detection.id);
        }
        if (detection.uuid !== undefined && detection.uuid !== null) {
            return String(detection.uuid);
        }
        if (detection.historyId) {
            return `hist-${detection.historyId}`;
        }
        if (fallbackIndex !== null && fallbackIndex !== undefined) {
            return `index-${fallbackIndex}`;
        }
        return null;
    }

    function attachDetectionKey(detection, index) {
        if (!detection || typeof detection !== 'object') {
            return null;
        }
        const key = symbolDetectionKey(detection, index);
        if (!key) {
            return { ...detection };
        }
        if (detection.__key === key) {
            return detection;
        }
        return { ...detection, __key: key };
    }

    function normalizePath(value) {
        if (typeof value !== 'string' || !value) {
            return null;
        }
        try {
            const url = new URL(value, window.location.origin);
            const pathname = url.pathname.replace(/\\/g, '/');
            const trimmed = pathname.replace(/\/+$/, '');
            return trimmed ? trimmed.toLowerCase() : '/';
        } catch (error) {
            const sanitized = value.split('?')[0].split('#')[0];
            if (!sanitized) {
                return null;
            }
            const replaced = sanitized.replace(/\\/g, '/');
            const prefixed = replaced.startsWith('/') ? replaced : `/${replaced}`;
            const trimmed = prefixed.replace(/\/+$/, '');
            return trimmed ? trimmed.toLowerCase() : '/';
        }
    }

    function extractFilename(value) {
        if (typeof value !== 'string' || !value) {
            return null;
        }
        const sanitized = value.split('?')[0].split('#')[0].replace(/\\/g, '/');
        if (!sanitized) {
            return null;
        }
        const parts = sanitized.split('/');
        const candidate = parts[parts.length - 1];
        return candidate ? candidate.toLowerCase() : null;
    }

    function describeSymbolOrigin(detection) {
        if (!detection || typeof detection !== 'object') {
            return '—';
        }
        const source = detection.source && typeof detection.source === 'object'
            ? detection.source
            : detection.meta && typeof detection.meta.source === 'object'
                ? detection.meta.source
                : null;
        if (source) {
            if (typeof source.label === 'string' && source.label.trim()) {
                return source.label.trim();
            }
            if (typeof source.filename === 'string' && source.filename.trim()) {
                return source.filename.trim();
            }
            if (typeof source.page === 'number' && Number.isFinite(source.page)) {
                return `Strona ${source.page}`;
            }
        }
        if (typeof detection.filename === 'string' && detection.filename.trim()) {
            return detection.filename.trim();
        }
        if (typeof detection.historyId === 'string') {
            return `Historia ${detection.historyId}`;
        }
        return '—';
    }

    function buildNetlistSymbolEntry(detection, index) {
        const withKey = attachDetectionKey(detection, index);
        if (!withKey) {
            return null;
        }
        const box = normalizeDetectionBox(withKey);
        const key = withKey.__key || symbolDetectionKey(withKey, index) || `index-${index}`;
        return {
            key,
            index,
            label: withKey.label || withKey.class || 'symbol',
            confidenceLabel: formatConfidence(withKey.score),
            bboxLabel: formatBoxLabel(box),
            origin: describeSymbolOrigin(withKey),
            detection: withKey,
            box,
        };
    }

    function buildSourceFingerprint(descriptor) {
        if (!descriptor || typeof descriptor !== 'object') {
            return {
                normalizedUrl: null,
                filename: null,
                historyId: null,
            };
            updateHistoryIdLabel();
        }

        const candidates = [];
        const directUrl = typeof descriptor.url === 'string' ? descriptor.url : null;
        const imageUrl = typeof descriptor.imageUrl === 'string' ? descriptor.imageUrl : null;
        const valueUrl = typeof descriptor.value === 'string' ? descriptor.value : null;
        const filenameFromDescriptor = typeof descriptor.filename === 'string' ? descriptor.filename : null;
        const labelCandidate = typeof descriptor.label === 'string' ? descriptor.label : null;

        if (directUrl) candidates.push(directUrl);
        if (imageUrl) candidates.push(imageUrl);
        if (valueUrl) candidates.push(valueUrl);
        if (filenameFromDescriptor) candidates.push(filenameFromDescriptor);
        if (labelCandidate) candidates.push(labelCandidate);

        if (descriptor.storage && typeof descriptor.storage === 'object') {
            const storageFilename = descriptor.storage.filename;
            if (typeof storageFilename === 'string') {
                candidates.push(storageFilename);
            }
        }

        if (descriptor.payload && typeof descriptor.payload === 'object') {
            const payload = descriptor.payload;
            if (typeof payload.filename === 'string') {
                candidates.push(payload.filename);
            }
            if (payload.source && typeof payload.source === 'object') {
                const nested = payload.source;
                if (typeof nested.filename === 'string') {
                    candidates.push(nested.filename);
                }
                if (typeof nested.imageUrl === 'string') {
                    candidates.push(nested.imageUrl);
                }
            }
        }

        const normalizedUrl = normalizePath(directUrl || imageUrl || valueUrl);

        let filename = null;
        for (const candidate of candidates) {
            const extracted = extractFilename(candidate);
            if (extracted) {
                filename = extracted;
                break;
            }
        }

        let historyId = null;
        if (descriptor.historyId || descriptor.id) {
            historyId = descriptor.historyId || descriptor.id;
        }
        if (!historyId && descriptor.payload && typeof descriptor.payload === 'object') {
            const payload = descriptor.payload;
            if (typeof payload.historyId === 'string') {
                historyId = payload.historyId;
            } else if (payload.source && typeof payload.source === 'object' && payload.source.historyId) {
                historyId = payload.source.historyId;
            }
        }

        const normalizedHistoryId = historyId ? String(historyId).toLowerCase() : null;

        return {
            normalizedUrl,
            filename,
            historyId: normalizedHistoryId,
        };
    }

    function getEntryTimestamp(entry) {
        if (!entry || typeof entry !== 'object') {
            return 0;
        }
        const metaCreated = entry.meta && typeof entry.meta.createdAt === 'string' ? entry.meta.createdAt : null;
        const payloadCreated = entry.payload && typeof entry.payload.createdAt === 'string' ? entry.payload.createdAt : null;
        const candidate = metaCreated || payloadCreated;
        if (!candidate) {
            return 0;
        }
        const timestamp = Date.parse(candidate);
        return Number.isFinite(timestamp) ? timestamp : 0;
    }

    function upsertSymbolDetectionEntry(entry) {
        if (!entry || typeof entry !== 'object' || !entry.id) {
            return;
        }
        const identifier = String(entry.id);
        let replaced = false;
        state.symbolDetectionIndex = state.symbolDetectionIndex.map((existing) => {
            if (existing && existing.id === identifier) {
                replaced = true;
                return entry;
            }
            return existing;
        });
        if (!replaced) {
            state.symbolDetectionIndex.push(entry);
        }
        if (state.symbolDetectionCache instanceof Map) {
            state.symbolDetectionCache.delete(identifier);
        }
        state.symbolDetectionIndexLoaded = true;
    }

    async function fetchSymbolDetectionEntries(forceRefresh = false) {
        if (!forceRefresh && state.symbolDetectionIndexLoaded && !state.symbolDetectionIndexPromise) {
            return state.symbolDetectionIndex;
        }
        if (state.symbolDetectionIndexPromise) {
            return state.symbolDetectionIndexPromise;
        }

        state.symbolDetectionIndexPromise = (async () => {
            try {
                const response = await fetch(PROCESSING_HISTORY_ENDPOINT, {
                    method: 'GET',
                    headers: { Accept: 'application/json' },
                });
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }
                const payload = await response.json();
                const entries = Array.isArray(payload?.entries) ? payload.entries : [];
                const filtered = entries.filter((entry) => entry && entry.type === 'symbol-detection');
                state.symbolDetectionIndex = filtered;
                state.symbolDetectionIndexLoaded = true;
                return filtered;
            } finally {
                state.symbolDetectionIndexPromise = null;
            }
        })();

        try {
            return await state.symbolDetectionIndexPromise;
        } catch (error) {
            state.symbolDetectionIndexLoaded = false;
            state.symbolDetectionIndex = [];
            state.symbolDetectionIndexPromise = null;
            throw error;
        }
    }

    async function fetchSymbolDetectionPayload(entry) {
        if (!entry || typeof entry !== 'object' || !entry.id || !entry.url) {
            return null;
        }
        const identifier = String(entry.id);
        if (state.symbolDetectionCache instanceof Map && state.symbolDetectionCache.has(identifier)) {
            return state.symbolDetectionCache.get(identifier);
        }
        const response = await fetch(entry.url, {
            method: 'GET',
            headers: { Accept: 'application/json' },
        });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const payload = await response.json();
        if (state.symbolDetectionCache instanceof Map) {
            state.symbolDetectionCache.set(identifier, payload);
        }
        return payload;
    }

    function findMatchingSymbolEntry(entries, sourceEntry) {
        if (!Array.isArray(entries) || entries.length === 0 || !sourceEntry) {
            return null;
        }

        const sourceDescriptor = {
            url: sourceEntry.url,
            imageUrl: sourceEntry.imageUrl,
            filename:
                sourceEntry.filename
                || (sourceEntry.payload && sourceEntry.payload.filename)
                || sourceEntry.label,
            historyId: sourceEntry.historyId || sourceEntry.id,
            storage: sourceEntry.storage,
        };
        const sourceFingerprint = buildSourceFingerprint(sourceDescriptor);

        let bestEntry = null;
        let bestScore = 0;
        let bestTimestamp = 0;

        entries.forEach((entry) => {
            if (!entry || entry.type !== 'symbol-detection') {
                return;
            }
            const detectionSource = entry.payload && entry.payload.source ? entry.payload.source : {};
            const detectionDescriptor = {
                url: detectionSource.imageUrl || detectionSource.url,
                imageUrl: detectionSource.imageUrl,
                filename: detectionSource.filename || entry.payload?.filename,
                historyId: detectionSource.historyId || detectionSource.id,
                storage: entry.storage,
            };
            const targetFingerprint = buildSourceFingerprint(detectionDescriptor);

            let score = 0;
            if (sourceFingerprint.historyId && targetFingerprint.historyId && sourceFingerprint.historyId === targetFingerprint.historyId) {
                score += 80;
            }
            if (sourceFingerprint.normalizedUrl && targetFingerprint.normalizedUrl && sourceFingerprint.normalizedUrl === targetFingerprint.normalizedUrl) {
                score += 50;
            }
            if (sourceFingerprint.filename && targetFingerprint.filename && sourceFingerprint.filename === targetFingerprint.filename) {
                score += 25;
            }
            if (sourceFingerprint.filename && entry.storage && typeof entry.storage.filename === 'string') {
                const storageFilename = extractFilename(entry.storage.filename);
                if (storageFilename && storageFilename === sourceFingerprint.filename) {
                    score += 10;
                }
            }

            if (score === 0) {
                return;
            }

            const timestamp = getEntryTimestamp(entry);
            if (score > bestScore || (score === bestScore && timestamp > bestTimestamp)) {
                bestScore = score;
                bestEntry = entry;
                bestTimestamp = timestamp;
            }
        });

        return bestScore > 0 ? bestEntry : null;
    }

    async function refreshSymbolOverlayForSource(options = {}) {
        const { force = false, preferredEntry = null } = options;
        const currentSource = state.sourceEntry;
        state.symbolOverlayRequestId += 1;
        const requestId = state.symbolOverlayRequestId;
        resetSymbolOverlayState();

        if (!currentSource || !currentSource.url) {
            clearSymbolOverlay();
            setSymbolStatus(SYMBOL_STATUS_DEFAULT, 'muted');
            return;
        }

        setSymbolStatus('Wyszukuję zapis detekcji symboli...', 'muted');

        let entries;
        try {
            entries = await fetchSymbolDetectionEntries(force);
        } catch (error) {
            if (requestId !== state.symbolOverlayRequestId) {
                return;
            }
            console.error('Nie udało się pobrać historii detekcji symboli', error);
            clearSymbolOverlay();
            setSymbolStatus('Nie udało się pobrać historii detekcji symboli.', 'error');
            return;
        }

        if (requestId !== state.symbolOverlayRequestId) {
            return;
        }

        if (preferredEntry) {
            upsertSymbolDetectionEntry(preferredEntry);
            entries = state.symbolDetectionIndex;
        }

        if (!Array.isArray(entries) || entries.length === 0) {
            clearSymbolOverlay();
            setSymbolStatus('Brak zapisów detekcji symboli.', 'muted');
            return;
        }

        let matchedEntry = preferredEntry || findMatchingSymbolEntry(entries, currentSource);

        if (!matchedEntry) {
            clearSymbolOverlay();
            setSymbolStatus('Brak dopasowanych detekcji symboli.', 'muted');
            return;
        }

        setSymbolStatus('Wczytuję obrysy symboli...', 'info');
        let payload;
        try {
            payload = await fetchSymbolDetectionPayload(matchedEntry);
        } catch (error) {
            if (requestId !== state.symbolOverlayRequestId) {
                return;
            }
            console.error('Nie udało się wczytać zapisu detekcji symboli', error);
            clearSymbolOverlay();
            setSymbolStatus('Nie udało się wczytać zapisu detekcji symboli.', 'error');
            return;
        }

        if (requestId !== state.symbolOverlayRequestId) {
            return;
        }

        const detections = Array.isArray(payload?.detections) ? payload.detections : [];
        const normalizedDetections = detections
            .map((detection, index) => attachDetectionKey(detection, index))
            .filter(Boolean);
        state.symbolOverlayEntry = matchedEntry;
        state.symbolOverlaySource = payload?.source || matchedEntry.payload?.source || null;
        state.symbolOverlayDetector = payload?.detector || matchedEntry.payload?.detector || null;
        state.symbolDetections = normalizedDetections;
        state.symbolOverlayActiveKey = null;
        state.symbolListActiveKey = null;
        updateSymbolTableSelection();

        if (!normalizedDetections.length) {
            clearSymbolOverlay();
            setSymbolStatus('Zapis detekcji nie zawiera obrysów.', 'muted');
            return;
        }

        if (state.symbolOverlayEnabled) {
            drawSymbolOverlay();
        } else {
            clearSymbolOverlay();
        }

        const detectorInfo = state.symbolOverlayDetector;
        const detectorName = detectorInfo && typeof detectorInfo === 'object'
            ? detectorInfo.name || detectorInfo.id || 'detektor'
            : detectorInfo || matchedEntry.meta?.detector || 'detektor';
        const createdAt = matchedEntry.meta?.createdAt || matchedEntry.payload?.createdAt;
        const detectionCount = normalizedDetections.length;
        let countLabel = 'symboli';
        if (detectionCount === 1) {
            countLabel = 'symbol';
        } else if (detectionCount >= 2 && detectionCount <= 4) {
            countLabel = 'symbole';
        }
        const summaryParts = [`${detectionCount} ${countLabel}`];
        if (detectorName) {
            summaryParts.push(detectorName);
        }
        if (createdAt) {
            summaryParts.push(formatTimestamp(createdAt));
        }
        setSymbolStatus(`Wczytano ${summaryParts.join(' • ')}.`, 'success');
    }

    function prepareOverlayGeometry() {
        return prepareCanvasGeometry(overlayCanvas);
    }

    function prepareSymbolOverlayGeometry() {
        return prepareCanvasGeometry(symbolOverlayCanvas);
    }

    function drawNodeOverlay(result) {
        if (!overlayCanvas || !overlayCtx) {
            return;
        }
        if (!state.overlayEnabled) {
            clearOverlay();
            return;
        }
        if (!sourceImage || sourceImage.classList.contains('hidden')) {
            clearOverlay();
            return;
        }
        const metrics = prepareOverlayGeometry();
        if (!metrics || !Number.isFinite(metrics.scaleX) || !Number.isFinite(metrics.scaleY)) {
            clearOverlay();
            return;
        }

        const nodes = Array.isArray(result?.nodes) ? result.nodes : [];
        const highlighted = state.highlightedSegmentId ? getSegmentById(state.highlightedSegmentId) : null;
        if (state.isolateHighlight && !highlighted) {
            state.isolateHighlight = false;
            updateHighlightControls();
        }

        overlayCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);

        if (!state.isolateHighlight && nodes.length > 0) {
            nodes.forEach((node) => {
                const position = normalizePosition(node?.position);
                if (!position) {
                    return;
                }
                const attachments = extractAttachments(node);
                const degree = attachments.length;
                const classification = normalizeClassification(node?.classification, degree);
                const style = overlayStyles[classification] || overlayStyles.unspecified;

                const x = position.x * metrics.scaleX;
                const y = position.y * metrics.scaleY;
                if (!Number.isFinite(x) || !Number.isFinite(y)) {
                    return;
                }

                overlayCtx.save();
                const strokeColor = style.stroke || 'rgba(148, 163, 184, 0.72)';
                const strokeWidth = style.strokeWidth ?? (classification === 'endpoint' ? 2 : 2.2);
                overlayCtx.lineWidth = strokeWidth;
                overlayCtx.strokeStyle = strokeColor;
                overlayCtx.shadowColor = 'rgba(15, 23, 42, 0.25)';
                overlayCtx.shadowBlur = 1.5;
                overlayCtx.beginPath();
                overlayCtx.arc(x, y, style.radius, 0, Math.PI * 2);
                overlayCtx.stroke();
                overlayCtx.shadowBlur = 0;

                if (style.ringStroke && style.ringOffset) {
                    overlayCtx.beginPath();
                    overlayCtx.lineWidth = style.ringWidth ?? 1.2;
                    overlayCtx.strokeStyle = style.ringStroke;
                    overlayCtx.arc(x, y, style.radius + style.ringOffset, 0, Math.PI * 2);
                    overlayCtx.stroke();
                }
                overlayCtx.restore();
            });
        }

        if (highlighted) {
            drawHighlightedSegment(highlighted, metrics);
        }

        applyTransforms();
    }

    function setOverlayEnabled(enabled) {
        state.overlayEnabled = Boolean(enabled);
        if (!state.overlayEnabled) {
            clearOverlay();
        } else if (state.lastResult) {
            drawNodeOverlay(state.lastResult);
        }
    }

    function drawSymbolOverlay() {
        if (!symbolOverlayCanvas || !symbolOverlayCtx) {
            return;
        }
        if (!state.symbolOverlayEnabled) {
            clearSymbolOverlay();
            return;
        }
        if (!Array.isArray(state.symbolDetections) || state.symbolDetections.length === 0) {
            clearSymbolOverlay();
            return;
        }
        if (!sourceImage || sourceImage.classList.contains('hidden')) {
            clearSymbolOverlay();
            return;
        }

        const metrics = prepareSymbolOverlayGeometry();
        if (!metrics || !Number.isFinite(metrics.scaleX) || !Number.isFinite(metrics.scaleY)) {
            clearSymbolOverlay();
            return;
        }

        const canvasWidth = symbolOverlayCanvas.width;
        const canvasHeight = symbolOverlayCanvas.height;
        symbolOverlayCtx.clearRect(0, 0, canvasWidth, canvasHeight);

        const padding = 4;

        state.symbolDetections.forEach((detection, index) => {
            const box = normalizeDetectionBox(detection);
            if (!box) {
                return;
            }
            const key = detection?.__key || symbolDetectionKey(detection, index);
            const isActive = key && state.symbolOverlayActiveKey && key === state.symbolOverlayActiveKey;
            const x = box.x * metrics.scaleX;
            const y = box.y * metrics.scaleY;
            const width = box.width * metrics.scaleX;
            const height = box.height * metrics.scaleY;
            if (![x, y, width, height].every(Number.isFinite) || width <= 0 || height <= 0) {
                return;
            }

            symbolOverlayCtx.save();
            symbolOverlayCtx.lineWidth = isActive ? 3 : 2;
            symbolOverlayCtx.strokeStyle = isActive ? 'rgba(255, 138, 61, 0.95)' : 'rgba(56, 189, 248, 0.9)';
            symbolOverlayCtx.shadowColor = 'rgba(15, 23, 42, 0.25)';
            symbolOverlayCtx.shadowBlur = isActive ? 4 : 2;
            symbolOverlayCtx.strokeRect(x, y, width, height);
            symbolOverlayCtx.restore();

            const label = detection.label || `symbol-${index + 1}`;
            const score = typeof detection.score === 'number' && Number.isFinite(detection.score)
                ? detection.score.toFixed(2)
                : null;
            const caption = score ? `${label} (${score})` : label;

            symbolOverlayCtx.save();
            symbolOverlayCtx.font = '12px Inter, system-ui, sans-serif';
            const textMetrics = symbolOverlayCtx.measureText(caption);
            const textWidth = textMetrics.width + padding * 2;
            const textHeight = 14 + padding * 2;
            const labelX = x;
            const labelY = Math.max(0, y - textHeight);
            symbolOverlayCtx.fillStyle = isActive ? 'rgba(15, 23, 42, 0.9)' : 'rgba(15, 23, 42, 0.75)';
            symbolOverlayCtx.fillRect(labelX, labelY, textWidth, textHeight);
            symbolOverlayCtx.fillStyle = isActive ? '#ffd3ba' : '#ffffff';
            const baseline = labelY + textHeight - padding - 2;
            symbolOverlayCtx.fillText(caption, labelX + padding, baseline);
            symbolOverlayCtx.restore();
        });

        applyTransforms();
    }

    function setSymbolOverlayEnabled(enabled) {
        state.symbolOverlayEnabled = Boolean(enabled);
        if (!state.symbolOverlayEnabled) {
            clearSymbolOverlay();
            return;
        }
        if (Array.isArray(state.symbolDetections) && state.symbolDetections.length > 0) {
            drawSymbolOverlay();
        }
    }

    if (sourceImage) {
        sourceImage.addEventListener('load', () => {
            measureBaseOffset();
            applyTransforms();
            updateZoomUI();
            if (state.lastResult) {
                drawNodeOverlay(state.lastResult);
            } else {
                clearOverlay();
            }
            if (state.symbolOverlayEnabled && Array.isArray(state.symbolDetections) && state.symbolDetections.length > 0) {
                drawSymbolOverlay();
            } else {
                clearSymbolOverlay();
            }
        });
    }

    if (overlayCanvas) {
        window.addEventListener('resize', () => {
            measureBaseOffset();
            applyTransforms();
            updateZoomUI();
            if (state.lastResult) {
                drawNodeOverlay(state.lastResult);
            }
            if (state.symbolOverlayEnabled && Array.isArray(state.symbolDetections) && state.symbolDetections.length > 0) {
                drawSymbolOverlay();
            }
        });
    }

    if (overlayToggle) {
        state.overlayEnabled = Boolean(overlayToggle.checked);
        overlayToggle.addEventListener('change', (event) => {
            setOverlayEnabled(event.target.checked);
        });
    }

    if (symbolOverlayToggle) {
        state.symbolOverlayEnabled = Boolean(symbolOverlayToggle.checked);
        symbolOverlayToggle.addEventListener('change', (event) => {
            setSymbolOverlayEnabled(event.target.checked);
            if (!event.target.checked) {
                return;
            }
            if (state.sourceOrigin === 'local') {
                setSymbolStatus('Wyślij obraz na serwer, aby wczytać obrysy symboli.', 'muted');
                return;
            }
            if (!Array.isArray(state.symbolDetections) || state.symbolDetections.length === 0) {
                void refreshSymbolOverlayForSource();
            }
        });
    } else {
        state.symbolOverlayEnabled = false;
    }

    updateLogUI();
    setLogFeedback('', 'success', 0);

    if (logToggle) {
        logToggle.checked = false;
        logToggle.addEventListener('change', (event) => {
            setLogEnabled(event.target.checked);
        });
    }

    if (logCategory) {
        logCategory.addEventListener('change', (event) => {
            if (state.loggedPoints.length === 0) {
                setLogFeedback('Najpierw zarejestruj punkt, aby przypisać tag.', 'error', 2600);
                return;
            }
            const entry = ensureActiveLogEntry();
            if (!entry) {
                setLogFeedback('Brak aktywnego punktu do aktualizacji.', 'error', 2600);
                return;
            }
            setActiveLogEntry(entry.id);
            const rawTag = (event.target.value ?? '').trim();
            if (rawTag) {
                entry.tag = rawTag;
            } else {
                delete entry.tag;
            }
            updateLogUI();
            setLogFeedback(`Zaktualizowano tag punktu #${entry.id}.`, 'success', 1600);
        });
    }

    if (logNoteInput) {
        logNoteInput.addEventListener('input', (event) => {
            if (state.loggedPoints.length === 0) {
                return;
            }
            const entry = ensureActiveLogEntry();
            if (!entry) {
                return;
            }
            setActiveLogEntry(entry.id);
            const note = event.target.value.trim();
            if (note.length > 0) {
                entry.note = note;
            } else {
                delete entry.note;
            }
            updateLogUI();
        });
    }

    if (logCopyBtn) {
        logCopyBtn.addEventListener('click', async () => {
            const success = await copyLogToClipboard();
            if (success) {
                setLogFeedback('Dane skopiowane do schowka.', 'success', 2000);
            } else {
                setLogFeedback('Nie udało się skopiować danych do schowka.', 'error', 3200);
            }
        });
    }

    if (logClearBtn) {
        logClearBtn.addEventListener('click', () => {
            if (state.loggedPoints.length === 0) {
                setLogFeedback('Brak danych do wyczyszczenia.', 'error', 2200);
                return;
            }
            const confirmed = window.confirm('Wyczyścić wszystkie zapisane punkty?');
            if (confirmed) {
                clearLog();
            }
        });
    }

    function toFiniteNumber(value) {
        if (typeof value === 'number' && Number.isFinite(value)) {
            return value;
        }
        if (typeof value === 'string' && value.trim() !== '') {
            const parsed = Number(value);
            if (Number.isFinite(parsed)) {
                return parsed;
            }
        }
        return null;
    }

    function formatCount(value) {
        const numeric = toFiniteNumber(value);
        return numeric === null ? null : numeric.toLocaleString('pl-PL');
    }

    function formatConfidence(score) {
        if (typeof score === 'number' && Number.isFinite(score)) {
            return score.toFixed(score >= 1 ? 1 : 2);
        }
        if (typeof score === 'string' && score.trim() !== '') {
            return score.trim();
        }
        return '—';
    }

    function formatBoxLabel(box) {
        if (!box) {
            return '—';
        }
        const x = Number.isFinite(box.x) ? Math.round(box.x) : null;
        const y = Number.isFinite(box.y) ? Math.round(box.y) : null;
        const width = Number.isFinite(box.width) ? Math.round(box.width) : null;
        const height = Number.isFinite(box.height) ? Math.round(box.height) : null;
        if ([x, y, width, height].every((value) => value !== null)) {
            return `${x},${y} • ${width}×${height}`;
        }
        return '—';
    }

    function parseTimestamp(value) {
        if (value instanceof Date) {
            return Number.isFinite(value.getTime()) ? value : null;
        }
        if (typeof value === 'number' && Number.isFinite(value)) {
            return new Date(value);
        }
        if (typeof value === 'string' && value.trim()) {
            const parsed = Date.parse(value);
            if (Number.isFinite(parsed)) {
                return new Date(parsed);
            }
        }
        return null;
    }

    function formatTimestamp(value) {
        const date = (typeof parseTimestamp === 'function') ? parseTimestamp(value) : (value ? new Date(value) : null);
        if (!date) {
            return '—';
        }
        const pad = (n) => String(n).padStart(2, '0');
        const tzParts = date.toLocaleTimeString([], { timeZoneName: 'short' }).split(' ');
        const tz = tzParts[tzParts.length - 1] || '';
        const datePart = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
        const timePart = `${pad(date.getHours())}:${pad(date.getMinutes())}`;
        return `${datePart} ${timePart} ${tz}`.trim();
    }

    function extractFlaggedSegments(metadata) {
        if (!metadata || typeof metadata !== 'object') {
            return [];
        }
        const confidence = metadata.confidence && typeof metadata.confidence === 'object' ? metadata.confidence : null;
        const scores = confidence && confidence.scores && typeof confidence.scores === 'object' ? confidence.scores : null;
        const collected = [];

        if (confidence && Array.isArray(confidence.flagged_segments) && confidence.flagged_segments.length > 0) {
            confidence.flagged_segments.forEach((item) => {
                if (!item || typeof item !== 'object') {
                    return;
                }
                const identifier = item.id || item.segment_id || item.segmentId;
                if (!identifier) {
                    return;
                }
                const entry = { ...item };
                if (!entry.label && scores && scores[identifier] && typeof scores[identifier] === 'object') {
                    entry.label = scores[identifier].label;
                }
                collected.push(entry);
            });
            return collected;
        }

        const flaggedIds = Array.isArray(metadata.flagged_segments) ? metadata.flagged_segments : [];
        if (!flaggedIds.length || !scores) {
            return [];
        }

        flaggedIds.forEach((identifier) => {
            const entry = scores[identifier];
            if (entry && typeof entry === 'object') {
                collected.push({ id: identifier, ...entry });
            } else {
                collected.push({ id: identifier });
            }
        });

        return collected;
    }

    function setStatus(message) {
        if (statusLabel) {
            statusLabel.textContent = message;
        }
    }

    function setSymbolStatus(message, tone = 'muted') {
        if (!symbolOverlayStatus) {
            return;
        }
        const baseClass = 'small mb-0 mt-2';
        let toneClass = 'text-muted';
        if (tone === 'success') {
            toneClass = 'text-success';
        } else if (tone === 'error') {
            toneClass = 'text-danger';
        } else if (tone === 'info') {
            toneClass = 'text-primary';
        }
        symbolOverlayStatus.className = `${baseClass} ${toneClass}`;
        symbolOverlayStatus.textContent = message || '';
    }

    function setSummary(lines = '--', nodes = '--', time = '--', shape = '--', binary = '--', skeleton = '--', flagged = '--') {
        if (summaryLines) summaryLines.textContent = lines;
        if (summaryNodes) summaryNodes.textContent = nodes;
        if (summaryTime) summaryTime.textContent = time;
        if (summaryShape) summaryShape.textContent = shape;
        if (summaryBinary) summaryBinary.textContent = binary;
        if (summarySkeleton) summarySkeleton.textContent = skeleton;
        if (summaryFlagged) summaryFlagged.textContent = flagged;
    }

    function updateHighlightControls() {
        const highlighted = getSegmentById(state.highlightedSegmentId);
        const hasHighlight = Boolean(highlighted);
        if (diagnosticHighlightClearBtn) {
            diagnosticHighlightClearBtn.disabled = !hasHighlight;
        }
        if (diagnosticHighlightIsolate) {
            diagnosticHighlightIsolate.disabled = !hasHighlight;
            diagnosticHighlightIsolate.checked = hasHighlight && state.isolateHighlight;
        }
        if (diagnosticPanel) {
            diagnosticPanel.dataset.highlightActive = hasHighlight ? 'true' : 'false';
        }
    }

    function buildSegmentIndex(lines) {
        state.segmentIndex = new Map();
        if (!Array.isArray(lines)) {
            return;
        }
        lines.forEach((segment) => {
            if (!segment || segment.id === undefined || segment.id === null) {
                return;
            }
            state.segmentIndex.set(String(segment.id), segment);
        });
    }

    function getSegmentById(segmentId) {
        if (!segmentId && segmentId !== 0) {
            return null;
        }
        const key = String(segmentId);
        if (state.segmentIndex && typeof state.segmentIndex.get === 'function') {
            const cached = state.segmentIndex.get(key);
            if (cached) {
                return cached;
            }
        }
        if (!state.lastResult || !Array.isArray(state.lastResult.lines)) {
            return null;
        }
        const found = state.lastResult.lines.find((segment) => segment && String(segment.id) === key);
        if (found) {
            if (!state.segmentIndex || typeof state.segmentIndex.set !== 'function') {
                state.segmentIndex = new Map();
            }
            state.segmentIndex.set(key, found);
        }
        return found || null;
    }

    function drawHighlightEndpoint(x, y) {
        if (!overlayCtx) {
            return;
        }
        overlayCtx.save();
        overlayCtx.beginPath();
        overlayCtx.fillStyle = 'rgba(37, 99, 235, 0.95)';
        overlayCtx.strokeStyle = 'rgba(255, 255, 255, 0.9)';
        overlayCtx.lineWidth = 1.6;
        const radius = state.isolateHighlight ? 5.4 : 4.4;
        overlayCtx.arc(x, y, radius, 0, Math.PI * 2);
        overlayCtx.fill();
        overlayCtx.stroke();
        overlayCtx.restore();
    }

    function drawHighlightedSegment(segment, metrics) {
        if (!overlayCtx || !segment || !metrics) {
            return;
        }
        const start = normalizePosition(segment.start || segment.start_position || segment.startPosition);
        const end = normalizePosition(segment.end || segment.end_position || segment.endPosition);
        if (!start || !end) {
            return;
        }

        const startX = start.x * metrics.scaleX;
        const startY = start.y * metrics.scaleY;
        const endX = end.x * metrics.scaleX;
        const endY = end.y * metrics.scaleY;

        overlayCtx.save();
        overlayCtx.lineCap = 'round';
        overlayCtx.lineJoin = 'round';
        overlayCtx.lineWidth = state.isolateHighlight ? 6 : 4;
        overlayCtx.strokeStyle = 'rgba(37, 99, 235, 0.92)';
        overlayCtx.shadowColor = 'rgba(59, 130, 246, 0.65)';
        overlayCtx.shadowBlur = state.isolateHighlight ? 18 : 10;
        overlayCtx.beginPath();
        overlayCtx.moveTo(startX, startY);
        overlayCtx.lineTo(endX, endY);
        overlayCtx.stroke();
        overlayCtx.restore();

        drawHighlightEndpoint(startX, startY);
        drawHighlightEndpoint(endX, endY);

        const label = segment.id ?? segment.label;
        if (label !== undefined && label !== null && label !== '') {
            overlayCtx.save();
            overlayCtx.font = '600 12px "Segoe UI", sans-serif';
            overlayCtx.lineWidth = 3;
            overlayCtx.strokeStyle = 'rgba(255, 255, 255, 0.85)';
            overlayCtx.fillStyle = 'rgba(15, 23, 42, 0.92)';
            const midX = (startX + endX) / 2;
            const midY = (startY + endY) / 2;
            const text = String(label);
            overlayCtx.strokeText(text, midX + 8, midY - 4);
            overlayCtx.fillText(text, midX + 8, midY - 4);
            overlayCtx.restore();
        }
    }

    function clearHighlightedSegment(options = {}) {
        const { silent = false, redraw = true, syncDiagnostic = true } = options;
        const hadHighlight = Boolean(state.highlightedSegmentId);
        state.highlightedSegmentId = null;
        state.isolateHighlight = false;
        updateHighlightControls();
        if (syncDiagnostic && diagnosticChat && typeof diagnosticChat.clearSelection === 'function') {
            diagnosticChat.clearSelection({ silent: true, reason: 'visual' });
        }
        if (redraw && state.lastResult) {
            drawNodeOverlay(state.lastResult);
        } else if (redraw && !state.lastResult) {
            clearOverlay();
        }
        if (hadHighlight && !silent && diagnosticChat && typeof diagnosticChat.setStatus === 'function') {
            diagnosticChat.setStatus('Podświetlenie wyłączone.');
        }
        refreshLogCursor();
    }

    function setHighlightedSegment(segmentId, options = {}) {
        const {
            isolate,
            silent = false,
            syncDiagnostic = true,
            segmentData = null,
        } = options;
        if (segmentId === undefined || segmentId === null || segmentId === '') {
            clearHighlightedSegment({ silent, syncDiagnostic });
            return null;
        }
        let target = getSegmentById(segmentId);
        if (!target && segmentData) {
            const start = segmentData.start || segmentData.start_position || segmentData.startPosition;
            const end = segmentData.end || segmentData.end_position || segmentData.endPosition;
            if (start && end) {
                target = {
                    id: segmentData.id ?? segmentId,
                    start,
                    end,
                };
            }
        }
        if (!target) {
            clearHighlightedSegment({ silent, syncDiagnostic });
            return null;
        }
        const normalizedId = String(target.id ?? segmentId);
        if (typeof isolate === 'boolean') {
            state.isolateHighlight = isolate;
        }
        state.highlightedSegmentId = normalizedId;
        updateHighlightControls();
        if (syncDiagnostic && diagnosticChat && typeof diagnosticChat.setSelection === 'function') {
            diagnosticChat.setSelection(normalizedId, { silent: true, reason: 'visual' });
        }
        if (!silent && diagnosticChat && typeof diagnosticChat.setStatus === 'function') {
            diagnosticChat.setStatus(`Podświetlam odcinek ${normalizedId}.`);
        }
        if (state.lastResult) {
            drawNodeOverlay(state.lastResult);
        }
        if (state.logEnabled) {
            state.suppressClick = false;
        }
        refreshLogCursor();
        return target;
    }

    if (diagnosticChat) {
        if (typeof diagnosticChat.registerSegmentFocus === 'function') {
            diagnosticChat.registerSegmentFocus((segment, meta = {}) => {
                if (!segment || !segment.id) {
                    clearHighlightedSegment({ silent: true, syncDiagnostic: false });
                    return;
                }
                setHighlightedSegment(segment.id, {
                    segmentData: segment,
                    silent: meta?.reason === 'auto',
                    syncDiagnostic: false,
                });
                refreshLogCursor();
            });
        }
        if (typeof diagnosticChat.registerSelectionClear === 'function') {
            diagnosticChat.registerSelectionClear(() => {
                clearHighlightedSegment({ silent: true, syncDiagnostic: false });
                refreshLogCursor();
            });
        }
    }

    function labelForLogTag(tag) {
        if (!tag) {
            return 'Brak';
        }
        return LOG_TAG_LABELS[tag] || tag;
    }

    function setLogFeedback(message, tone = 'success', durationMs = 2400) {
        if (!logFeedback) {
            return;
        }
        if (state.logFeedbackTimer) {
            window.clearTimeout(state.logFeedbackTimer);
            state.logFeedbackTimer = null;
        }
        if (!message) {
            logFeedback.classList.add('visually-hidden');
            return;
        }
        logFeedback.textContent = message;
        logFeedback.classList.remove('visually-hidden', 'text-success', 'text-danger');
        logFeedback.classList.add(tone === 'error' ? 'text-danger' : 'text-success');
        state.logFeedbackTimer = window.setTimeout(() => {
            if (logFeedback) {
                logFeedback.classList.add('visually-hidden');
            }
            state.logFeedbackTimer = null;
        }, Math.max(0, durationMs));
    }

    function updateLogUI() {
        if (logList) {
            logList.innerHTML = '';
            if (state.loggedPoints.length === 0) {
                const empty = document.createElement('li');
                empty.className = 'text-muted small';
                empty.textContent = 'Brak zarejestrowanych punktów.';
                logList.appendChild(empty);
            } else {
                const preview = state.loggedPoints.slice(0, LOG_LIST_PREVIEW_LIMIT);
                preview.forEach((entry) => {
                    const li = document.createElement('li');
                    li.className = 'line-seg-log-entry';
                    if (entry.id === state.activeLogEntryId) {
                        li.dataset.active = 'true';
                    }

                    const head = document.createElement('div');
                    head.className = 'line-seg-log-entry-head';
                    const idSpan = document.createElement('span');
                    idSpan.className = 'fw-semibold';
                    idSpan.textContent = `#${entry.id}`;
                    head.appendChild(idSpan);
                    if (entry.tag) {
                        const tag = document.createElement('span');
                        tag.className = 'line-seg-log-entry-tag';
                        tag.textContent = labelForLogTag(entry.tag);
                        head.appendChild(tag);
                    }
                    li.appendChild(head);

                    const meta = document.createElement('div');
                    meta.className = 'line-seg-log-entry-meta';
                    const coords = document.createElement('span');
                    coords.textContent = `x: ${entry.x}, y: ${entry.y}`;
                    meta.appendChild(coords);
                    const zoomInfo = document.createElement('span');
                    zoomInfo.textContent = `zoom: ${entry.zoom}`;
                    meta.appendChild(zoomInfo);
                    const panInfo = document.createElement('span');
                    panInfo.textContent = `pan: ${entry.pan.x}, ${entry.pan.y}`;
                    meta.appendChild(panInfo);
                    if (entry.sample) {
                        const sampleInfo = document.createElement('span');
                        sampleInfo.textContent = `źródło: ${truncateText(entry.sample)}`;
                        meta.appendChild(sampleInfo);
                    }
                    try {
                        const when = new Date(entry.timestamp);
                        if (!Number.isNaN(when.getTime())) {
                            const timeInfo = document.createElement('span');
                            timeInfo.textContent = when.toLocaleString('pl-PL', { hour12: false });
                            meta.appendChild(timeInfo);
                        }
                    } catch (error) {
                        // Ignoruj nieprawidłową datę
                    }
                    li.appendChild(meta);

                    if (entry.note) {
                        const note = document.createElement('div');
                        note.className = 'line-seg-log-entry-note';
                        note.textContent = entry.note;
                        li.appendChild(note);
                    }

                    logList.appendChild(li);
                });

                if (state.loggedPoints.length > LOG_LIST_PREVIEW_LIMIT) {
                    const rest = document.createElement('li');
                    rest.className = 'text-muted small';
                    rest.textContent = `+${state.loggedPoints.length - LOG_LIST_PREVIEW_LIMIT} kolejnych punktów w eksporcie.`;
                    logList.appendChild(rest);
                }
            }
        }

        if (logExport) {
            logExport.textContent = state.loggedPoints.length > 0 ? JSON.stringify(state.loggedPoints, null, 2) : '[]';
        }

        const hasEntries = state.loggedPoints.length > 0;
        if (logCopyBtn) {
            logCopyBtn.disabled = !hasEntries;
        }
        if (logClearBtn) {
            logClearBtn.disabled = !hasEntries;
        }
    }

    function refreshLogCursor() {
        if (!sourceStage) {
            return;
        }
        const active = Boolean(state.logEnabled && hasSourceImage());
        sourceStage.classList.toggle('log-mode', active);
    }

    function setLogEnabled(enabled) {
        const nextValue = Boolean(enabled);
        state.logEnabled = nextValue;
        if (logToggle && logToggle.checked !== nextValue) {
            logToggle.checked = nextValue;
        }
        refreshLogCursor();
        if (!nextValue) {
            state.suppressClick = false;
            setLogFeedback('Rejestracja wyłączona.', 'success', 1600);
        } else if (hasSourceImage()) {
            setLogFeedback('Kliknij, aby dodać punkt. Shift + przeciągnięcie przesuwa widok, Ctrl + kółko powiększa.', 'success', 3600);
        } else {
            setLogFeedback('Wczytaj obraz, aby rejestrować punkty.', 'error', 2800);
        }
    }

    function copyLogToClipboard() {
        if (state.loggedPoints.length === 0) {
            return Promise.resolve(false);
        }
        const payload = JSON.stringify(state.loggedPoints, null, 2);
        if (!payload) {
            return Promise.resolve(false);
        }
        if (navigator.clipboard && window.isSecureContext) {
            return navigator.clipboard.writeText(payload).then(() => true).catch(() => false);
        }
        return new Promise((resolve) => {
            const textarea = document.createElement('textarea');
            textarea.value = payload;
            textarea.setAttribute('readonly', 'readonly');
            textarea.style.position = 'absolute';
            textarea.style.left = '-9999px';
            document.body.appendChild(textarea);
            textarea.select();
            try {
                const success = document.execCommand('copy');
                resolve(success);
            } catch (error) {
                resolve(false);
            } finally {
                document.body.removeChild(textarea);
            }
        });
    }

    function clearLog() {
        state.loggedPoints = [];
        state.logSequence = 0;
        setActiveLogEntry(null);
        updateLogUI();
        setLogFeedback('Log wyczyszczony.', 'success', 2000);
        if (logNoteInput) {
            logNoteInput.value = '';
        }
        if (logCategory) {
            logCategory.value = defaultLogCategoryValue;
        }
    }

    function handleStageClick(event) {
        if (!state.logEnabled || !state.offsetReady || !hasSourceImage()) {
            return;
        }
        if (event.button !== 0) {
            return;
        }
        if (event.shiftKey || event.altKey || event.ctrlKey || event.metaKey) {
            return;
        }
        if (state.suppressClick) {
            state.suppressClick = false;
            return;
        }
        if (state.isPanning || state.panMoved) {
            return;
        }
    if (event.target.closest('.overlay-legend-panel')) {
            return;
        }
        if (event.detail > 1) {
            return;
        }

        const stagePoint = getStagePointFromEvent(event);
        const imagePoint = stagePointToImage(stagePoint);
        if (!stagePoint || !imagePoint) {
            setLogFeedback('Nie udało się obliczyć współrzędnych.', 'error', 2600);
            return;
        }

        const entry = {
            id: state.logSequence = (state.logSequence || 0) + 1,
            x: toRounded(imagePoint.x, 2),
            y: toRounded(imagePoint.y, 2),
            stageX: toRounded(stagePoint.x, 2),
            stageY: toRounded(stagePoint.y, 2),
            zoom: toRounded(state.zoomLevel, 3),
            pan: {
                x: toRounded(state.pan.x, 2),
                y: toRounded(state.pan.y, 2),
            },
            source: state.sourceOrigin || null,
            timestamp: new Date().toISOString(),
        };

        if (state.sourceEntry) {
            entry.sample = state.sourceEntry.label || state.sourceEntry.url || null;
        }
        if (state.activeFixtureId) {
            entry.fixtureId = state.activeFixtureId;
        }
        if (sourceImage) {
            entry.imageWidth = sourceImage.naturalWidth || null;
            entry.imageHeight = sourceImage.naturalHeight || null;
        }

        if (logCategory) {
            const rawTag = (logCategory.value ?? '').trim();
            if (rawTag) {
                entry.tag = rawTag;
            }
        }
        if (logNoteInput) {
            const note = logNoteInput.value.trim();
            if (note.length > 0) {
                entry.note = note;
            }
        }

        state.loggedPoints.unshift(entry);
        if (state.loggedPoints.length > LOG_STORAGE_LIMIT) {
            state.loggedPoints.splice(LOG_STORAGE_LIMIT);
        }
        setActiveLogEntry(entry.id);
        updateLogUI();
        setLogFeedback(`Zapisano punkt #${entry.id}. Uzupełnij tag/notatkę poniżej.`, 'success', 2600);

        if (logCategory && entry.tag) {
            logCategory.value = entry.tag;
        }
        if (logNoteInput) {
            logNoteInput.focus();
            if (entry.note) {
                logNoteInput.select();
            } else {
                logNoteInput.value = '';
            }
        }

        event.preventDefault();
        event.stopPropagation();
    }

    function setNetlistStatus(message) {
        if (netlistStatus) {
            netlistStatus.textContent = message;
            console.debug('[lineSeg] setNetlistStatus ->', message);
        } else {
            // Defensive fallback: try to set the element directly if mapping was missed
            console.debug('[lineSeg] setNetlistStatus called but `netlistStatus` not mapped. Falling back to querySelector. message=', message);
            const el = document.getElementById('lineSegNetlistStatus');
            if (el) {
                el.textContent = message;
                console.debug('[lineSeg] setNetlistStatus fallback succeeded.');
            }
        }
    }

    function setSpiceStatus(message, tone = 'muted') {
        if (!spiceStatus) {
            return;
        }
        spiceStatus.textContent = message;
        const baseClass = 'small';
        let toneClass = 'text-muted';
        if (tone === 'success') {
            toneClass = 'text-success';
        } else if (tone === 'error') {
            toneClass = 'text-danger';
        }
        spiceStatus.className = `${baseClass} ${toneClass}`;
    }

    function renderSpice(spicePayload = null) {
        if (spicePre) {
            if (spicePayload && typeof spicePayload.spice === 'string' && spicePayload.spice.trim()) {
                spicePre.textContent = spicePayload.spice.trimEnd();
            } else {
                spicePre.textContent = '* Brak eksportu SPICE.';
            }
        }

        if (spiceDownloadLink) {
            if (spicePayload && spicePayload.historyEntry && spicePayload.historyEntry.url) {
                spiceDownloadLink.href = spicePayload.historyEntry.url;
                spiceDownloadLink.classList.remove('hidden');
                state.spiceDownloadUrl = spicePayload.historyEntry.url;
            } else {
                spiceDownloadLink.href = '#';
                spiceDownloadLink.classList.add('hidden');
                state.spiceDownloadUrl = null;
            }
        }

        state.lastSpice = spicePayload;
    }

    function renderNetlist(netlist = null) {
        state.componentAssignments = [];
        if (!netlist) {
            if (netlistSummaryNodes) netlistSummaryNodes.textContent = '--';
            if (netlistSummaryEdges) netlistSummaryEdges.textContent = '--';
            if (netlistSummaryEssential) netlistSummaryEssential.textContent = '--';
            if (netlistSummaryNonEssential) netlistSummaryNonEssential.textContent = '--';
            if (netlistSummaryEndpoints) netlistSummaryEndpoints.textContent = '--';
            if (netlistSummaryComponents) netlistSummaryComponents.textContent = '--';
            if (netlistSummaryCycles) netlistSummaryCycles.textContent = '--';
            if (netlistPre) netlistPre.textContent = '[]';
            setNetlistStatus('Brak danych.');
            state.lastNetlist = null;
            if (netlistExportBtn) {
                netlistExportBtn.disabled = true;
            }
            renderSpice(null);
            setSpiceStatus('Brak eksportu SPICE.');
            renderComponentAssignments([]);
            renderSymbolMetadata(null);
            resetConnectorPanel({ preserveFingerprint: true });
            return;
        }

        const metadata = netlist.metadata || {};
        const nodesCount = toFiniteNumber(metadata.node_count) ?? toFiniteNumber(metadata.nodes) ?? null;
        const edgesCount = toFiniteNumber(metadata.edge_count) ?? toFiniteNumber(metadata.lines) ?? null;
        const components = Array.isArray(metadata.connected_components) ? metadata.connected_components.length : null;
        const cycles = Array.isArray(metadata.cycles) ? metadata.cycles.length : null;
        if (netlistSummaryNodes) netlistSummaryNodes.textContent = nodesCount !== null ? nodesCount.toLocaleString('pl-PL') : '--';
        if (netlistSummaryEdges) netlistSummaryEdges.textContent = edgesCount !== null ? edgesCount.toLocaleString('pl-PL') : '--';
        const classification = metadata.node_classification || metadata.nodeClassification || {};
        let essentialCount = toFiniteNumber(classification.essential);
        if (essentialCount === null && Array.isArray(metadata.essential_node_labels)) {
            essentialCount = metadata.essential_node_labels.length;
        }
        let nonEssentialCount = toFiniteNumber(classification.non_essential ?? classification.nonEssential);
        if (nonEssentialCount === null && Array.isArray(metadata.non_essential_node_labels)) {
            nonEssentialCount = metadata.non_essential_node_labels.length;
        }
        let endpointsCount = toFiniteNumber(classification.endpoint ?? classification.endpoints);
        if (endpointsCount === null && Array.isArray(metadata.endpoint_node_labels)) {
            endpointsCount = metadata.endpoint_node_labels.length;
        }
        if (netlistSummaryEssential) netlistSummaryEssential.textContent = essentialCount !== null ? essentialCount.toLocaleString('pl-PL') : '--';
        if (netlistSummaryNonEssential) netlistSummaryNonEssential.textContent = nonEssentialCount !== null ? nonEssentialCount.toLocaleString('pl-PL') : '--';
        if (netlistSummaryEndpoints) netlistSummaryEndpoints.textContent = endpointsCount !== null ? endpointsCount.toLocaleString('pl-PL') : '--';
        if (netlistSummaryComponents) netlistSummaryComponents.textContent = components !== null ? components.toLocaleString('pl-PL') : '--';
        if (netlistSummaryCycles) netlistSummaryCycles.textContent = cycles !== null ? cycles.toLocaleString('pl-PL') : '--';

        if (netlistPre) {
            const wires = Array.isArray(metadata.netlist) ? metadata.netlist : null;
            if (wires && wires.length > 0) {
                netlistPre.textContent = wires.join('\n');
            } else {
                netlistPre.textContent = JSON.stringify(netlist, null, 2);
            }
        }
        // Set status and defensively re-assert shortly after to catch race overwrites.
        console.debug('[lineSeg] renderNetlist -> setting status "Netlista gotowa."');
        setNetlistStatus('Netlista gotowa.');
        // Record timestamp for diagnostic checks
        state.lastNetlistRenderAt = Date.now();
        // Micro-check: if some other code overwrites the status immediately after render, log and restore
        setTimeout(() => {
            try {
                const current = netlistStatus ? netlistStatus.textContent : (document.getElementById('lineSegNetlistStatus')?.textContent || '');
                if (current !== 'Netlista gotowa.') {
                    console.warn('[lineSeg] renderNetlist: status was overwritten after render. Expected "Netlista gotowa.", got=', current);
                    setNetlistStatus('Netlista gotowa.');
                }
            } catch (e) {
                console.debug('[lineSeg] renderNetlist: micro-check failed', e);
            }
        }, 120);
        state.lastNetlist = netlist;
        if (netlistExportBtn) {
            netlistExportBtn.disabled = false;
        }
        setSpiceStatus('Kliknij „Eksportuj do SPICE”, aby wygenerować plik.');
        consumeEdgeConnectorMetadata(netlist.metadata?.edgeConnectors || null);
        renderSymbolMetadata(netlist.metadata?.symbols || null, netlist);
        buildComponentAssignments();
    }

    function setConnectorStatus(message, tone = 'muted') {
        if (!connectorStatus) {
            return;
        }
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
        connectorStatus.className = `small ${toneClass}`;
        connectorStatus.textContent = message || '';
    }

    function renderConnectorMatches(entries = [], { fingerprint = null } = {}) {
        if (!connectorTableBody || !connectorTableWrapper || !connectorTableEmpty) {
            return;
        }
        const list = Array.isArray(entries) ? entries : [];
        connectorTableBody.innerHTML = '';
        if (!list.length) {
            connectorTableWrapper.classList.add('hidden');
            connectorTableEmpty.classList.remove('hidden');
        } else {
            connectorTableWrapper.classList.remove('hidden');
            connectorTableEmpty.classList.add('hidden');
            const fragment = document.createDocumentFragment();
            list.forEach((entry) => {
                const row = document.createElement('tr');

                const edgeCell = document.createElement('td');
                edgeCell.textContent = entry.edgeId || '—';
                row.append(edgeCell);

                const pageCell = document.createElement('td');
                pageCell.textContent = entry.page || '—';
                row.append(pageCell);

                const netCell = document.createElement('td');
                netCell.textContent = entry.netName || '—';
                row.append(netCell);

                const noteCell = document.createElement('td');
                if (entry.label) {
                    const labelSpan = document.createElement('span');
                    labelSpan.className = 'fw-semibold';
                    labelSpan.textContent = entry.label;
                    noteCell.append(labelSpan);
                    if (entry.note) {
                        const noteLine = document.createElement('div');
                        noteLine.className = 'text-muted small';
                        noteLine.textContent = entry.note;
                        noteCell.append(noteLine);
                    }
                } else {
                    noteCell.textContent = entry.note || '—';
                }
                row.append(noteCell);

                const timestampCell = document.createElement('td');
                timestampCell.textContent = entry.updatedAt ? formatTimestamp(entry.updatedAt) : '—';
                row.append(timestampCell);

                fragment.append(row);
            });
            connectorTableBody.append(fragment);
        }
        if (connectorHint) {
            const hasFingerprint = Boolean(fingerprint && Array.isArray(fingerprint.candidates) && fingerprint.candidates.length);
            const shouldShowHint = !list.length && !hasFingerprint;
            connectorHint.classList.toggle('hidden', !shouldShowHint);
        }
    }

    function normalizeRoi(candidate) {
        const toNumber = (value) => (Number.isFinite(Number(value)) ? Number(value) : null);
        if (!candidate) {
            return null;
        }
        if (Array.isArray(candidate) && candidate.length === 4) {
            const [x1, y1, x2, y2] = candidate.map(toNumber);
            if ([x1, y1, x2, y2].every((v) => v !== null)) {
                const width = x2 - x1;
                const height = y2 - y1;
                if (width > 0 && height > 0) {
                    return { x: x1, y: y1, width, height };
                }
            }
        }
        if (typeof candidate !== 'object') {
            return null;
        }
        const x = toNumber(candidate.x ?? candidate.left ?? candidate.x1);
        const y = toNumber(candidate.y ?? candidate.top ?? candidate.y1);
        const width = toNumber(
            candidate.width
            ?? (candidate.x2 !== undefined && x !== null ? candidate.x2 - x : null)
            ?? (candidate.right !== undefined && x !== null ? candidate.right - x : null)
        );
        const height = toNumber(
            candidate.height
            ?? (candidate.y2 !== undefined && y !== null ? candidate.y2 - y : null)
            ?? (candidate.bottom !== undefined && y !== null ? candidate.bottom - y : null)
        );
        if ([x, y, width, height].every((v) => v !== null) && width > 0 && height > 0) {
            return { x, y, width, height };
        }
        return null;
    }

    function normalizeEdgeConnectorEntry(entry) {
        if (!entry || typeof entry !== 'object') {
            return null;
        }
        const computeGeometryRoi = (geom) => {
            if (!geom || typeof geom !== 'object' || !Array.isArray(geom.points) || geom.points.length < 2) {
                return null;
            }
            const xs = [];
            const ys = [];
            geom.points.forEach((pt) => {
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
                width: Math.max(maxX - minX, 1),
                height: Math.max(maxY - minY, 1),
            };
        };
        const historyId = entry.historyId || entry?.metadata?.historyId || null;
        const roiAbs = normalizeRoi(
            entry.roiAbs
            || entry.roi
            || entry?.metadata?.roi_abs
            || entry?.metadata?.roi
            || entry?.metadata?.geometry?.roi
            || computeGeometryRoi(entry.geometry || entry.payload?.geometry)
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

    function deriveEdgeConnectorFingerprint(additionalCandidates = []) {
        const collected = new Set();
        const push = (value) => {
            if (typeof value === 'string') {
                const trimmed = value.trim();
                if (trimmed) {
                    collected.add(trimmed);
                }
            }
        };

        if (Array.isArray(additionalCandidates)) {
            additionalCandidates.forEach(push);
        }
        const sourceEntry = state.sourceEntry;
        if (sourceEntry) {
            push(sourceEntry.historyId);
            push(sourceEntry.history_id);
            push(sourceEntry.id);
            if (sourceEntry.meta && typeof sourceEntry.meta === 'object') {
                push(sourceEntry.meta.historyId);
                push(sourceEntry.meta.history_id);
                if (sourceEntry.meta.source && typeof sourceEntry.meta.source === 'object') {
                    push(sourceEntry.meta.source.historyId);
                    push(sourceEntry.meta.source.id);
                }
            }
            if (sourceEntry.payload && typeof sourceEntry.payload === 'object') {
                push(sourceEntry.payload.historyId);
                push(sourceEntry.payload.history_id);
            }
        }
        const netlistSource = state.lastNetlist?.metadata?.source;
        if (netlistSource && typeof netlistSource === 'object') {
            push(netlistSource.historyId);
            push(netlistSource.id);
        }
        if (Array.isArray(state.edgeConnectorMatches) && state.edgeConnectorMatches.length > 0) {
            push(state.edgeConnectorMatches[0].historyId);
        }

        const items = Array.from(collected);
        return {
            candidates: items,
            preferred: items.length ? items[0] : null,
        };
    }

    function resolveSourceHistoryId(entry = state.sourceEntry) {
        const collected = new Set();
        const push = (value) => {
            if (typeof value === 'string') {
                const trimmed = value.trim();
                if (trimmed) {
                    collected.add(trimmed);
                }
            }
        };
        if (entry && typeof entry === 'object') {
            push(entry.historyId || entry.history_id);
            push(entry.id);
            if (entry.meta && typeof entry.meta === 'object') {
                push(entry.meta.historyId || entry.meta.history_id);
                if (entry.meta.source && typeof entry.meta.source === 'object') {
                    push(entry.meta.source.historyId);
                    push(entry.meta.source.id);
                }
            }
            if (entry.payload && typeof entry.payload === 'object') {
                push(entry.payload.historyId || entry.payload.history_id);
                if (entry.payload.source && typeof entry.payload.source === 'object') {
                    push(entry.payload.source.historyId);
                    push(entry.payload.source.id);
                }
            }
        }
        const items = Array.from(collected);
        return items.length ? items[0] : null;
    }

    function updateHistoryIdLabel() {
        if (!historyIdLabel) {
            return;
        }
        const sourceId = resolveSourceHistoryId();
        const fingerprintId = state.edgeConnectorFingerprint?.preferred || null;
        const historyId = sourceId || fingerprintId;
        if (historyId) {
            const hint = sourceId ? '' : ' (dopasowanie)' ;
            historyIdLabel.textContent = `History ID: ${historyId}${hint}`;
            historyIdLabel.className = 'text-success small mb-0';
        } else {
            historyIdLabel.textContent = 'History ID: brak (wczytaj materiał lub odśwież konektory)';
            historyIdLabel.className = 'text-muted small mb-0';
        }
    }

    function deriveEdgeConnectorRoi(matches = state.edgeConnectorMatches) {
        const list = Array.isArray(matches) ? matches : [];
        if (!list.length) {
            return null;
        }
        const sourcePage = state.sourceEntry?.meta?.page
            || state.sourceEntry?.payload?.page
            || state.sourceEntry?.page
            || null;
        const normalizedSourcePage = sourcePage !== null ? String(sourcePage) : null;
        const pick = (predicate) => list.find((item) => item && item.roiAbs && (!predicate || predicate(item)));
        let candidate = null;
        if (normalizedSourcePage) {
            candidate = pick((item) => item.page !== null && String(item.page) === normalizedSourcePage);
        }
        if (!candidate) {
            candidate = pick();
        }
        if (candidate && candidate.roiAbs) {
            return { ...candidate.roiAbs, page: candidate.page || null };
        }
        return null;
    }

    function updateRoiAvailability() {
        const roi = deriveEdgeConnectorRoi();
        state.edgeConnectorRoi = roi;
        const hasRoi = Boolean(roi);
        if (useConnectorRoiCheckbox) {
            useConnectorRoiCheckbox.disabled = !hasRoi;
            if (!hasRoi) {
                useConnectorRoiCheckbox.checked = false;
                try {
                    sessionStorage.setItem('app:lineSegUseConnectorRoi', 'false');
                } catch (err) {
                    console.warn('[lineSeg] Nie udało się zapisać stanu useConnectorRoi w sessionStorage', err);
                }
            }
        }
        if (roiStatusLabel) {
            if (hasRoi) {
                const pageLabel = roi.page ? ` (strona ${roi.page})` : '';
                roiStatusLabel.textContent = `Ramka schematu dostępna${pageLabel}.`;
                roiStatusLabel.className = 'text-success small';
            } else {
                roiStatusLabel.textContent = 'Brak ramki schematu z konektorów.';
                roiStatusLabel.className = 'text-muted small';
            }
        }
        if (hasRoi !== state.edgeConnectorRoiAvailable) {
            state.edgeConnectorRoiAvailable = hasRoi;
            if (hasRoi) {
                setStatus('ROI dostępne z konektorów — zaznacz checkbox, aby użyć przy segmentacji.');
            } else {
                setStatus('Brak ROI z konektorów — segmentacja użyje pełnego obrazu.');
            }
        }
    }

    function consumeEdgeConnectorMetadata(metadata) {
        if (!metadata || typeof metadata !== 'object') {
            resetConnectorPanel({ preserveFingerprint: false });
            return;
        }
        const historyCandidates = Array.isArray(metadata.historyCandidates) ? metadata.historyCandidates : [];
        const fingerprint = deriveEdgeConnectorFingerprint(historyCandidates);
        state.edgeConnectorFingerprint = fingerprint;
        const normalizedItems = Array.isArray(metadata.items)
            ? metadata.items.map((item) => normalizeEdgeConnectorEntry(item)).filter(Boolean)
            : [];
        state.edgeConnectorMatches = normalizedItems;
        renderConnectorMatches(normalizedItems, { fingerprint });
        updateRoiAvailability();
        const countValue = Number.isFinite(Number(metadata.count)) ? Number(metadata.count) : normalizedItems.length;
        if (countValue > 0) {
            const pageSet = new Set(normalizedItems.map((item) => item.page).filter(Boolean));
            const pagesLabel = pageSet.size ? ` (strony: ${Array.from(pageSet).join(', ')})` : '';
            setConnectorStatus(`Powiązano ${countValue} konektorów${pagesLabel}.`, 'success');
        } else if (fingerprint.candidates.length) {
            // Show which historyId candidates were used and hint to the user
            const cand = fingerprint.candidates.join(', ');
            setConnectorStatus(`Brak konektorów dla historyId: ${cand}. Kliknij „Odśwież”, aby spróbować ponownie.`, 'warning');
            console.debug('[lineSeg] consumeEdgeConnectorMetadata: no matches for fingerprint', fingerprint);
        } else {
            setConnectorStatus('Brak danych o konektorach.', 'muted');
        }
    }

    function resolveEdgeConnectorHistoryId() {
        const fingerprint = state.edgeConnectorFingerprint || deriveEdgeConnectorFingerprint();
        return fingerprint && fingerprint.preferred ? fingerprint.preferred : null;
    }

    async function fetchEdgeConnectorEntries(force = false) {
        if (!force && state.edgeConnectorEntries.length && Date.now() - state.edgeConnectorLastFetch < 30000) {
            return state.edgeConnectorEntries;
        }
        if (state.edgeConnectorLoading) {
            return state.edgeConnectorEntries;
        }
        state.edgeConnectorLoading = true;
        try {
            const response = await fetch(`${EDGE_CONNECTORS_ENDPOINT}?includePayload=1`, {
                method: 'GET',
                headers: { Accept: 'application/json' },
            });
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const payload = await response.json();
            const items = Array.isArray(payload?.items) ? payload.items : [];
            state.edgeConnectorEntries = items;
            state.edgeConnectorLastFetch = Date.now();
            return items;
        } finally {
            state.edgeConnectorLoading = false;
        }
    }

    async function syncEdgeConnectorMatches({ force = false, fingerprint = null } = {}) {
        const effectiveFingerprint = fingerprint || deriveEdgeConnectorFingerprint();
        state.edgeConnectorFingerprint = effectiveFingerprint;
        if (!effectiveFingerprint.candidates.length) {
            renderConnectorMatches([], { fingerprint: effectiveFingerprint });
            setConnectorStatus('Brak przypisanego historyId.', 'warning');
            return [];
        }
        if (connectorRefreshBtn) {
            connectorRefreshBtn.disabled = true;
        }
        setConnectorStatus('Ładowanie konektorów...', 'info');
        try {
            const entries = await fetchEdgeConnectorEntries(force);
            console.debug('[lineSeg] syncEdgeConnectorMatches: fetched entries count=', entries.length, 'fingerprint=', effectiveFingerprint);
            const normalizedCandidates = new Set(
                effectiveFingerprint.candidates.map((candidate) => candidate.toLowerCase())
            );
            const matches = entries
                .map((entry) => normalizeEdgeConnectorEntry(entry))
                .filter((entry) => entry && entry.historyIdNormalized && normalizedCandidates.has(entry.historyIdNormalized));
            state.edgeConnectorMatches = matches;
            renderConnectorMatches(matches, { fingerprint: effectiveFingerprint });
            if (matches.length) {
                setConnectorStatus(`Powiązano ${matches.length} konektorów.`, 'success');
            } else {
                const cand = effectiveFingerprint.candidates.join(', ');
                setConnectorStatus(`Brak konektorów dla historyId: ${cand}. Kliknij „Odśwież”, aby spróbować ponownie.`, 'warning');
                console.debug('[lineSeg] syncEdgeConnectorMatches: no matches for fingerprint', effectiveFingerprint, 'entriesCount=', entries.length);
            }
            updateRoiAvailability();
            return matches;
        } catch (error) {
            console.error('Nie udało się pobrać konektorów', error);
            setConnectorStatus('Nie udało się pobrać konektorów.', 'error');
            return [];
        } finally {
            if (connectorRefreshBtn) {
                connectorRefreshBtn.disabled = false;
            }
        }
    }

    function resetConnectorPanel({ preserveFingerprint = false, fallbackToSource = true } = {}) {
        state.edgeConnectorMatches = [];
        state.edgeConnectorRoi = null;
        if (!preserveFingerprint) {
            state.edgeConnectorFingerprint = fallbackToSource ? deriveEdgeConnectorFingerprint() : null;
        }
        renderConnectorMatches([], { fingerprint: state.edgeConnectorFingerprint });
        if (state.edgeConnectorFingerprint && state.edgeConnectorFingerprint.candidates.length) {
            setConnectorStatus('Brak wygenerowanej netlisty. Kliknij „Odśwież”, aby sprawdzić konektory.', 'info');
        } else {
            setConnectorStatus('Brak danych o konektorach.', 'muted');
        }
        updateRoiAvailability();
    }

    function setSymbolSummaryStatus(message, tone = 'muted') {
        if (!netlistSymbolStatus) {
            return;
        }
        let toneClass = 'text-muted';
        if (tone === 'success') {
            toneClass = 'text-success';
        } else if (tone === 'error') {
            toneClass = 'text-danger';
        } else if (tone === 'info') {
            toneClass = 'text-primary';
        }
        netlistSymbolStatus.className = `${toneClass} small mb-0`;
        netlistSymbolStatus.textContent = message || '';
    }

    function updateSymbolHistoryLink(historyId) {
        if (!symbolHistoryLink) {
            return;
        }
        if (!historyId) {
            symbolHistoryLink.classList.add('hidden');
            symbolHistoryLink.removeAttribute('href');
            return;
        }
        const entry = findSymbolHistoryEntry(historyId);
        if (entry && entry.url) {
            symbolHistoryLink.href = entry.url;
            symbolHistoryLink.classList.remove('hidden');
            return;
        }
        symbolHistoryLink.classList.add('hidden');
        symbolHistoryLink.removeAttribute('href');
        void fetchSymbolDetectionEntries().then(() => {
            const refreshedEntry = findSymbolHistoryEntry(historyId);
            if (refreshedEntry && refreshedEntry.url) {
                symbolHistoryLink.href = refreshedEntry.url;
                symbolHistoryLink.classList.remove('hidden');
            }
        }).catch(() => {
            /* no-op */
        });
    }

    function findSymbolHistoryEntry(historyId) {
        if (!historyId) {
            return null;
        }
        const normalizedId = String(historyId);
        const entries = Array.isArray(state.symbolDetectionIndex) ? state.symbolDetectionIndex : [];
        return entries.find((entry) => entry && String(entry.id) === normalizedId) || null;
    }

    function renderSymbolTable(entries) {
        if (!symbolTableBody || !symbolTableWrapper || !symbolTableEmpty) {
            return;
        }
        if (!entries || entries.length === 0) {
            symbolTableBody.innerHTML = '';
            symbolTableWrapper.classList.add('hidden');
            symbolTableEmpty.classList.remove('hidden');
            return;
        }
        symbolTableEmpty.classList.add('hidden');
        symbolTableWrapper.classList.remove('hidden');
        symbolTableBody.innerHTML = '';
        entries.forEach((entry) => {
            const row = document.createElement('tr');
            row.dataset.symbolKey = entry.key;
            row.tabIndex = 0;
            row.setAttribute('role', 'button');

            const indexCell = document.createElement('th');
            indexCell.scope = 'row';
            indexCell.textContent = String(entry.index + 1);
            row.append(indexCell);

            const labelCell = document.createElement('td');
            labelCell.textContent = entry.label || '—';
            row.append(labelCell);

            const confidenceCell = document.createElement('td');
            confidenceCell.textContent = entry.confidenceLabel || '—';
            row.append(confidenceCell);

            const bboxCell = document.createElement('td');
            bboxCell.textContent = entry.bboxLabel || '—';
            row.append(bboxCell);

            const originCell = document.createElement('td');
            originCell.textContent = entry.origin || '—';
            row.append(originCell);

            row.addEventListener('click', () => {
                focusSymbolByKey(entry.key);
            });
            row.addEventListener('keydown', (event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    focusSymbolByKey(entry.key);
                }
            });

            symbolTableBody.append(row);
        });
        updateSymbolTableSelection();
    }

    function renderSymbolMetadata(symbolsMeta = null, netlist = state.lastNetlist) {
        console.debug('[lineSeg] renderSymbolMetadata called ->', { symbolsMeta, netlistSummary: !!netlist });
        state.netlistSymbols = [];
        state.symbolSummary = null;
        state.symbolListActiveKey = null;
        state.symbolOverlayActiveKey = null;
        updateSymbolTableSelection();

        if (symbolCount) symbolCount.textContent = '--';
        if (symbolDetector) symbolDetector.textContent = '--';
        if (symbolLatency) symbolLatency.textContent = '--';
        if (symbolCapturedAt) symbolCapturedAt.textContent = '--';
        updateSymbolHistoryLink(null);

        if (!symbolsMeta) {
            setSymbolSummaryStatus('Brak powiązanych detekcji symboli.', 'muted');
            if (symbolTableWrapper) symbolTableWrapper.classList.add('hidden');
            if (symbolTableEmpty) symbolTableEmpty.classList.remove('hidden');
            if (symbolTableBody) symbolTableBody.innerHTML = '';
            return;
        }

        const summary = symbolsMeta.summary && typeof symbolsMeta.summary === 'object' ? symbolsMeta.summary : {};
        const detectorInfo = symbolsMeta.detector && typeof symbolsMeta.detector === 'object'
            ? symbolsMeta.detector
            : null;
        const detectorLabel = detectorInfo?.name || detectorInfo?.id || (typeof symbolsMeta.detector === 'string' ? symbolsMeta.detector : null);
        const latencyLabel = summary.latencyMs ?? summary.latency ?? summary.elapsedMs;
        const capturedAt = summary.capturedAt || summary.timestamp || summary.finishedAt || symbolsMeta.createdAt;
        const detections = Array.isArray(symbolsMeta.detections) ? symbolsMeta.detections : [];
        const normalizedEntries = detections
            .map((detection, index) => buildNetlistSymbolEntry(detection, index))
            .filter(Boolean);

        const countValue = toFiniteNumber(symbolsMeta.count) ?? normalizedEntries.length;
        if (symbolCount) {
            symbolCount.textContent = countValue ? countValue.toString() : '0';
        }
        if (symbolDetector) {
            symbolDetector.textContent = detectorLabel || '—';
        }
        if (symbolLatency) {
            const latencyNumber = Number(latencyLabel);
            symbolLatency.textContent = Number.isFinite(latencyNumber) ? `${latencyNumber.toFixed(1)} ms` : '—';
        }
        if (symbolCapturedAt) {
            symbolCapturedAt.textContent = formatTimestamp(capturedAt);
        }
        function formatSymbolCount(n) {
            const num = Number(n) || 0;
            if (!num) return `0 symboli`;
            if (num === 1) return `1 symbol`;
            if (num >= 2 && num <= 4) return `${num} symbole`;
            return `${num} symboli`;
        }
        const countLabelText = formatSymbolCount(countValue);
        setSymbolSummaryStatus(
            countValue
                ? `Powiązano ${countLabelText}. Kliknij wiersz, aby podświetlić.`
                : 'Brak dopasowanych symboli.',
            countValue ? 'info' : 'muted',
        );
        const historyId = symbolsMeta.historyId || symbolsMeta.history_id;
        const normalizedHistoryId = historyId ? String(historyId) : null;
        state.netlistSymbols = normalizedEntries;
        state.symbolSummary = {
            count: countValue,
            detector: detectorLabel,
            historyId: normalizedHistoryId,
            capturedAt,
        };
        updateSymbolHistoryLink(normalizedHistoryId);
        renderSymbolTable(normalizedEntries);

        if ((!Array.isArray(state.symbolDetections) || state.symbolDetections.length === 0) && normalizedEntries.length > 0) {
            state.symbolDetections = normalizedEntries.map((entry) => entry.detection).filter(Boolean);
            if (!state.symbolOverlaySource) {
                state.symbolOverlaySource = symbolsMeta.source || netlist?.metadata?.source || null;
            }
            if (state.symbolOverlayEnabled) {
                drawSymbolOverlay();
            }
        }
    }

    function updateSymbolTableSelection() {
        if (!symbolTableBody) {
            return;
        }
        const activeKey = state.symbolListActiveKey;
        symbolTableBody.querySelectorAll('tr[data-symbol-key]').forEach((row) => {
            if (activeKey && row.dataset.symbolKey === activeKey) {
                row.classList.add('table-active');
            } else {
                row.classList.remove('table-active');
            }
        });
    }

    function ensureSymbolDetectionPresent(detection) {
        if (!detection) {
            return;
        }
        const key = detection.__key || symbolDetectionKey(detection, null);
        if (!key) {
            return;
        }
        if (!Array.isArray(state.symbolDetections)) {
            state.symbolDetections = [];
        }
        const existingIndex = state.symbolDetections.findIndex((entry, index) => {
            const entryKey = entry?.__key || symbolDetectionKey(entry, index);
            return entryKey === key;
        });
        if (existingIndex === -1) {
            state.symbolDetections.push(detection);
        } else {
            state.symbolDetections[existingIndex] = detection;
        }
    }

    function focusSymbolByKey(key) {
        if (!key) {
            return;
        }
        const entry = state.netlistSymbols.find((item) => item && item.key === key);
        if (!entry) {
            return;
        }
        state.symbolListActiveKey = key;
        state.symbolOverlayActiveKey = key;
        ensureSymbolDetectionPresent(entry.detection);
        if (!state.symbolOverlayEnabled) {
            if (symbolOverlayToggle) {
                symbolOverlayToggle.checked = true;
            }
            setSymbolOverlayEnabled(true);
        }
        drawSymbolOverlay();
        updateSymbolTableSelection();
        setSymbolSummaryStatus(`Podświetlono symbol #${entry.index + 1} (${entry.label}).`, 'success');
    }

    function renderComponentAssignments(assignments = state.componentAssignments) {
        if (!componentSummaryTableWrapper || !componentSummaryTableBody || !componentSummaryEmpty) {
            return;
        }
        const hasAssignments = Array.isArray(assignments) && assignments.length > 0;
        if (componentSummary) {
            componentSummary.dataset.count = hasAssignments ? String(assignments.length) : '0';
        }
        if (!hasAssignments) {
            componentSummaryEmpty.classList.remove('hidden');
            componentSummaryTableWrapper.classList.add('hidden');
            componentSummaryTableBody.innerHTML = '';
            return;
        }

        componentSummaryEmpty.classList.add('hidden');
        componentSummaryTableWrapper.classList.remove('hidden');
        componentSummaryTableBody.innerHTML = '';

        assignments.forEach((component, index) => {
            if (!component || !Array.isArray(component.nodes)) {
                return;
            }
            const parameters = component.parameters && typeof component.parameters === 'object' ? component.parameters : {};

            const row = document.createElement('tr');

            const indexCell = document.createElement('th');
            indexCell.scope = 'row';
            indexCell.textContent = String(index + 1);
            row.append(indexCell);

            const kindCell = document.createElement('td');
            kindCell.textContent = component.kind || '—';
            row.append(kindCell);

            const nodesCell = document.createElement('td');
            nodesCell.textContent = component.nodes.length ? component.nodes.join(', ') : '—';
            row.append(nodesCell);

            const detectionCell = document.createElement('td');
            const detectionParts = [];
            if (typeof parameters.det === 'string' && parameters.det.trim()) {
                detectionParts.push(parameters.det.trim());
            }
            if (typeof parameters.pins === 'number' && Number.isFinite(parameters.pins)) {
                detectionParts.push(`${parameters.pins} pin`);
            }
            if (typeof parameters.hist === 'string' && parameters.hist.trim()) {
                detectionCell.title = `Historia: ${parameters.hist.trim()}`;
            }
            detectionCell.textContent = detectionParts.length ? detectionParts.join(' • ') : '—';
            row.append(detectionCell);

            const confidenceCell = document.createElement('td');
            const confNumeric = Number(parameters.conf);
            if (Number.isFinite(confNumeric)) {
                confidenceCell.textContent = confNumeric.toFixed(2);
            } else if (typeof parameters.conf === 'string' && parameters.conf.trim()) {
                confidenceCell.textContent = parameters.conf.trim();
            } else {
                confidenceCell.textContent = '—';
            }
            row.append(confidenceCell);

            componentSummaryTableBody.append(row);
        });
    }

    const COMPONENT_KIND_ALIASES = {
        resistor: 'resistor',
        resist: 'resistor',
        res: 'resistor',
        r: 'resistor',
        capacitor: 'capacitor',
        cap: 'capacitor',
        c: 'capacitor',
        inductor: 'inductor',
        ind: 'inductor',
        l: 'inductor',
        diode: 'diode',
        led: 'diode',
        d: 'diode',
        transistor: 'transistor',
        bjt: 'transistor',
        mosfet: 'transistor',
        fet: 'transistor',
        op_amp: 'op_amp',
        opamp: 'op_amp',
        amplifier: 'op_amp',
        connector: 'connector',
        terminal: 'connector',
        header: 'connector',
        port: 'connector',
        power: 'power_rail',
        power_rail: 'power_rail',
        vcc: 'power_rail',
        vdd: 'power_rail',
        vss: 'ground',
        ground: 'ground',
        gnd: 'ground',
        earth: 'ground',
        ic_pin: 'ic_pin',
        pin: 'ic_pin',
        net_label: 'net_label',
        label: 'net_label',
        tag: 'net_label',
        measurement_point: 'measurement_point',
        measurement: 'measurement_point',
        probe: 'measurement_point',
        testpoint: 'measurement_point',
        misc_symbol: 'misc_symbol',
        symbol: 'misc_symbol',
        component: 'misc_symbol',
    };

    const COMPONENT_PIN_COUNTS = {
        resistor: 2,
        capacitor: 2,
        inductor: 2,
        diode: 2,
        transistor: 3,
        op_amp: 5,
        connector: 2,
        power_rail: 1,
        ground: 1,
        ic_pin: 1,
        net_label: 1,
        measurement_point: 1,
        misc_symbol: 2,
    };

    const COMPONENT_CONFIDENCE_THRESHOLD = 0.2;

    function normalizeComponentKind(rawLabel) {
        if (typeof rawLabel !== 'string' || !rawLabel) {
            return null;
        }
        const sanitized = rawLabel
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '_')
            .replace(/^_+|_+$/g, '');
        if (!sanitized) {
            return null;
        }
        if (COMPONENT_KIND_ALIASES[sanitized]) {
            return COMPONENT_KIND_ALIASES[sanitized];
        }
        const trimmed = sanitized.replace(/_symbol$/, '');
        return COMPONENT_KIND_ALIASES[trimmed] || null;
    }

    function expectedPinCount(kind) {
        return COMPONENT_PIN_COUNTS[kind] ?? 2;
    }

    function resolveNetIdentifier(node, netLabelMap) {
        if (!node || typeof node !== 'object') {
            return null;
        }
        const netLabel = typeof node.net_label === 'string' && node.net_label.trim()
            ? node.net_label.trim()
            : typeof node.netLabel === 'string' && node.netLabel.trim()
                ? node.netLabel.trim()
                : null;
        if (netLabel) {
            return netLabel;
        }
        if (node.id && netLabelMap && typeof netLabelMap === 'object') {
            const mapped = netLabelMap[node.id];
            if (typeof mapped === 'string' && mapped.trim()) {
                return mapped.trim();
            }
        }
        if (typeof node.label === 'string' && node.label.trim()) {
            return node.label.trim();
        }
        if (typeof node.id === 'string' && node.id.trim()) {
            return node.id.trim();
        }
        return null;
    }

    function detectionMeetsConfidence(detection) {
        const score = detection && typeof detection.score === 'number' ? detection.score : null;
        if (score === null) {
            return true;
        }
        return score >= COMPONENT_CONFIDENCE_THRESHOLD;
    }

    function computeCandidateMetrics(position, box) {
        const centerX = box.x + box.width / 2;
        const centerY = box.y + box.height / 2;
        const dx = position.x - centerX;
        const dy = position.y - centerY;
        const distance = Math.hypot(dx, dy);
        const insideX = position.x >= box.x && position.x <= box.x + box.width;
        const insideY = position.y >= box.y && position.y <= box.y + box.height;
        let edgeDistance;
        if (insideX && insideY) {
            edgeDistance = Math.min(
                Math.abs(position.x - box.x),
                Math.abs(position.x - (box.x + box.width)),
                Math.abs(position.y - box.y),
                Math.abs(position.y - (box.y + box.height)),
            );
        } else {
            const dxOutside = insideX ? 0 : Math.min(
                Math.abs(position.x - box.x),
                Math.abs(position.x - (box.x + box.width)),
            );
            const dyOutside = insideY ? 0 : Math.min(
                Math.abs(position.y - box.y),
                Math.abs(position.y - (box.y + box.height)),
            );
            edgeDistance = Math.hypot(dxOutside, dyOutside);
        }
        return {
            distance,
            edgeDistance,
            dx,
            dy,
            insideX,
            insideY,
        };
    }

    function candidateWithinLimits(metrics, box, depth = 0) {
        if (!metrics) {
            return false;
        }
        const diag = Math.hypot(box.width, box.height) || 1;
        const maxDistance = diag * (1.2 + depth * 0.4) + 12;
        if (metrics.distance > maxDistance) {
            return false;
        }
        if (!metrics.insideX || !metrics.insideY) {
            const maxEdge = Math.max(box.width, box.height) * (0.7 + depth * 0.45) + 18;
            if (metrics.edgeDistance > maxEdge) {
                return false;
            }
        }
        return true;
    }

    function collectNodesNearBox(box, nodes, netLabelMap) {
        if (!box || !nodes || nodes.length === 0) {
            return [];
        }
        const paddingX = Math.max(6, box.width * 0.35);
        const paddingY = Math.max(6, box.height * 0.35);
        const minX = box.x - paddingX;
        const maxX = box.x + box.width + paddingX;
        const minY = box.y - paddingY;
        const maxY = box.y + box.height + paddingY;

        const results = [];
        nodes.forEach((node) => {
            const position = normalizePosition(node?.position);
            if (!position) {
                return;
            }
            if (position.x < minX || position.x > maxX || position.y < minY || position.y > maxY) {
                return;
            }
            const net = resolveNetIdentifier(node, netLabelMap);
            if (!net) {
                return;
            }
            const metrics = computeCandidateMetrics(position, box);
            if (!candidateWithinLimits(metrics, box, 0)) {
                return;
            }
            results.push({
                node,
                nodeId: node?.id,
                net,
                position,
                distance: metrics.distance,
                edgeDistance: metrics.edgeDistance,
                dx: metrics.dx,
                dy: metrics.dy,
                depth: 0,
            });
        });
        return results;
    }

    function candidateScore(candidate) {
        if (!candidate) {
            return Number.POSITIVE_INFINITY;
        }
        const depthPenalty = (candidate.depth || 0) * 24;
        const edge = Number.isFinite(candidate.edgeDistance) ? candidate.edgeDistance : 10_000;
        const dist = Number.isFinite(candidate.distance) ? candidate.distance : 10_000;
        return edge * 6 + dist + depthPenalty;
    }

    function rankCandidates(candidates) {
        return candidates.slice().sort((a, b) => {
            const scoreDelta = candidateScore(a) - candidateScore(b);
            if (Math.abs(scoreDelta) > 0.0001) {
                return scoreDelta;
            }
            return (a.distance || 0) - (b.distance || 0);
        });
    }

    function expandCandidatesWithNeighbors(baseCandidates, nodeLookup, netLabelMap, box, expectedPins) {
        if (!baseCandidates || baseCandidates.length === 0) {
            return [];
        }
        const lookupFn = nodeLookup && typeof nodeLookup.get === 'function'
            ? (id) => nodeLookup.get(id)
            : (id) => (nodeLookup ? nodeLookup[id] : undefined);
        if (!lookupFn) {
            return baseCandidates.slice();
        }
        const results = baseCandidates.slice();
        const visited = new Set(results.map((entry) => entry.nodeId).filter(Boolean));
        const queue = baseCandidates.slice();
        const maxDepth = expectedPins >= 4 ? 2 : 1;
        let depth = 0;
        while (queue.length && depth < maxDepth && results.length < expectedPins + 6) {
            const nextQueue = [];
            depth += 1;
            queue.forEach((candidate) => {
                const sourceNode = lookupFn(candidate.nodeId);
                if (!sourceNode || !Array.isArray(sourceNode.neighbors)) {
                    return;
                }
                sourceNode.neighbors.forEach((neighborId) => {
                    if (!neighborId || visited.has(neighborId)) {
                        return;
                    }
                    const neighborNode = lookupFn(neighborId);
                    if (!neighborNode) {
                        visited.add(neighborId);
                        return;
                    }
                    const position = normalizePosition(neighborNode.position);
                    if (!position) {
                        visited.add(neighborId);
                        return;
                    }
                    const net = resolveNetIdentifier(neighborNode, netLabelMap);
                    if (!net) {
                        visited.add(neighborId);
                        return;
                    }
                    const metrics = computeCandidateMetrics(position, box);
                    if (!candidateWithinLimits(metrics, box, depth)) {
                        visited.add(neighborId);
                        return;
                    }
                    const expanded = {
                        node: neighborNode,
                        nodeId: neighborNode.id,
                        net,
                        position,
                        distance: metrics.distance + depth * 4,
                        edgeDistance: metrics.edgeDistance + depth * 4,
                        dx: metrics.dx,
                        dy: metrics.dy,
                        depth,
                    };
                    results.push(expanded);
                    nextQueue.push(expanded);
                    visited.add(neighborId);
                });
            });
            queue.length = 0;
            Array.prototype.push.apply(queue, nextQueue);
        }
        return results;
    }

    function selectNodesForPins(candidates, expectedPins) {
        if (!Array.isArray(candidates) || candidates.length === 0) {
            return [];
        }
        const pinTarget = Math.max(1, expectedPins || 1);
        const ranked = rankCandidates(candidates);
        const selection = [];
        const usedNodes = new Set();

        for (const candidate of ranked) {
            if (!candidate.net || usedNodes.has(candidate.nodeId)) {
                continue;
            }
            selection.push(candidate);
            usedNodes.add(candidate.nodeId);
            if (selection.length >= pinTarget) {
                break;
            }
        }

        if (selection.length < pinTarget) {
            for (const candidate of ranked) {
                if (!candidate.net || usedNodes.has(candidate.nodeId)) {
                    continue;
                }
                selection.push(candidate);
                usedNodes.add(candidate.nodeId);
                if (selection.length >= pinTarget) {
                    break;
                }
            }
        }

        return selection.slice(0, pinTarget);
    }

    function ensureMinimumUniqueNets(selection, rankedPool, minUnique) {
        if (!Array.isArray(selection) || selection.length === 0) {
            return selection;
        }
        let uniqueCount = new Set(selection.map((entry) => entry.net)).size;
        if (uniqueCount >= minUnique) {
            return selection;
        }
        const netOccurrences = new Map();
        selection.forEach((entry) => {
            netOccurrences.set(entry.net, (netOccurrences.get(entry.net) || 0) + 1);
        });

        for (const candidate of rankedPool) {
            if (!candidate.net) {
                continue;
            }
            const alreadySelected = selection.some((entry) => entry.nodeId === candidate.nodeId);
            if (alreadySelected) {
                continue;
            }
            if (selection.some((entry) => entry.net === candidate.net)) {
                continue;
            }
            const duplicateIndex = selection.findIndex((entry) => (netOccurrences.get(entry.net) || 0) > 1);
            if (duplicateIndex === -1) {
                continue;
            }
            const removed = selection[duplicateIndex];
            netOccurrences.set(removed.net, (netOccurrences.get(removed.net) || 0) - 1);
            selection.splice(duplicateIndex, 1, candidate);
            netOccurrences.set(candidate.net, 1);
            uniqueCount = new Set(selection.map((entry) => entry.net)).size;
            if (uniqueCount >= minUnique) {
                break;
            }
        }

        return selection;
    }

    function sourcesAlignedWithDetections(netlist) {
        if (!netlist || typeof netlist !== 'object') {
            return true;
        }
        const sourceMeta = netlist.metadata && typeof netlist.metadata === 'object' ? netlist.metadata.source : null;
        if (!sourceMeta || typeof sourceMeta !== 'object') {
            return true;
        }
        const netDescriptor = {
            url: sourceMeta.url || sourceMeta.imageUrl || null,
            imageUrl: sourceMeta.imageUrl,
            filename: sourceMeta.filename || sourceMeta.label,
            historyId: sourceMeta.historyId || sourceMeta.id,
            payload: { source: sourceMeta },
        };
        const netFingerprint = buildSourceFingerprint(netDescriptor);

        let detectionDescriptor = null;
        if (state.symbolOverlayEntry) {
            detectionDescriptor = state.symbolOverlayEntry;
        } else if (state.symbolOverlaySource) {
            detectionDescriptor = {
                url: state.symbolOverlaySource.url || state.symbolOverlaySource.imageUrl || null,
                imageUrl: state.symbolOverlaySource.imageUrl,
                filename: state.symbolOverlaySource.filename,
                historyId: state.symbolOverlaySource.historyId || state.symbolOverlaySource.id,
                payload: { source: state.symbolOverlaySource },
            };
        }
        if (!detectionDescriptor) {
            return true;
        }
        const detectionFingerprint = buildSourceFingerprint(detectionDescriptor);

        if (
            netFingerprint.historyId
            && detectionFingerprint.historyId
            && netFingerprint.historyId !== detectionFingerprint.historyId
        ) {
            return false;
        }
        if (
            netFingerprint.filename
            && detectionFingerprint.filename
            && netFingerprint.filename !== detectionFingerprint.filename
        ) {
            return false;
        }
        if (
            netFingerprint.normalizedUrl
            && detectionFingerprint.normalizedUrl
            && netFingerprint.normalizedUrl !== detectionFingerprint.normalizedUrl
        ) {
            return false;
        }
        return true;
    }

    function mapDetectionToComponent(detection, nodes, netLabelMap, nodeLookup, detectionIndex) {
        if (!detection || typeof detection !== 'object') {
            return null;
        }
        if (!detectionMeetsConfidence(detection)) {
            console.debug('[lineSeg] mapDetectionToComponent: skipping detection due to low confidence', detection);
            return null;
        }
        const kind = normalizeComponentKind(detection.label);
        if (!kind) {
            console.debug('[lineSeg] mapDetectionToComponent: unknown/unsupported symbol kind for label', detection.label, detection);
            return null;
        }
        const box = normalizeDetectionBox(detection);
        if (!box) {
            console.debug('[lineSeg] mapDetectionToComponent: could not normalize bbox for detection', detection);
            return null;
        }
        const baseCandidates = collectNodesNearBox(box, nodes, netLabelMap);
        if (!baseCandidates.length) {
            console.debug('[lineSeg] mapDetectionToComponent: no base candidates found near detection box', box, 'detection', detection);
            return null;
        }
        const expectedPins = expectedPinCount(kind);
        const expandedCandidates = expandCandidatesWithNeighbors(baseCandidates, nodeLookup, netLabelMap, box, expectedPins);
        const rankedPool = rankCandidates(expandedCandidates);
        const selected = selectNodesForPins(expandedCandidates, expectedPins);
        const requiredPins = Math.max(1, expectedPins || 1);
        if (selected.length < requiredPins) {
            console.debug('[lineSeg] mapDetectionToComponent: insufficient nodes selected for expected pins', { requiredPins, selectedLength: selected.length, selected, detection });
            return null;
        }

        const minUniquePins = requiredPins >= 2 ? Math.min(2, requiredPins) : 1;
        ensureMinimumUniqueNets(selected, rankedPool, minUniquePins);
        const uniqueCount = new Set(selected.map((entry) => entry.net)).size;
        if (uniqueCount < minUniquePins) {
            console.debug('[lineSeg] mapDetectionToComponent: insufficient unique nets for symbol (need', minUniquePins, 'got', uniqueCount, ')', { detection, orderedCandidates, rankedPool });
            return null;
        }

        const trimmedSelection = selected.slice(0, requiredPins);
        const orderedCandidates = trimmedSelection.slice();
        const centerX = box.x + box.width / 2;
        const centerY = box.y + box.height / 2;
        if (orderedCandidates.length === 2) {
            const spanX = Math.abs(orderedCandidates[0].position.x - orderedCandidates[1].position.x);
            const spanY = Math.abs(orderedCandidates[0].position.y - orderedCandidates[1].position.y);
            if (spanX >= spanY) {
                orderedCandidates.sort((a, b) => a.position.x - b.position.x);
            } else {
                orderedCandidates.sort((a, b) => a.position.y - b.position.y);
            }
        } else if (orderedCandidates.length > 2) {
            orderedCandidates.sort((a, b) => {
                const angleA = Math.atan2(a.position.y - centerY, a.position.x - centerX);
                const angleB = Math.atan2(b.position.y - centerY, b.position.x - centerX);
                if (angleA === angleB) {
                    return a.distance - b.distance;
                }
                return angleA - angleB;
            });
        }

        const nodeSequence = orderedCandidates.map((entry) => entry.net);

        const parameters = {};
        if (typeof detection.score === 'number' && Number.isFinite(detection.score)) {
            parameters.conf = detection.score.toFixed(3);
        }
        if (detection.id) {
            parameters.det = String(detection.id);
        } else if (Number.isFinite(detectionIndex)) {
            parameters.det = `det-${detectionIndex + 1}`;
        }
        if (state.symbolOverlayEntry && state.symbolOverlayEntry.id) {
            parameters.hist = String(state.symbolOverlayEntry.id);
        }
        parameters.pins = nodeSequence.length;

        return {
            kind,
            nodes: nodeSequence,
            parameters,
        };
    }

    function buildComponentAssignments() {
        if (!state.lastNetlist || !Array.isArray(state.lastNetlist.nodes)) {
            state.componentAssignments = [];
            renderComponentAssignments([]);
            state.lastComponentAssignmentError = 'Brak netlisty. Najpierw wygeneruj netlistę.';
            setSpiceStatus(state.lastComponentAssignmentError, 'error');
            console.debug('[lineSeg] buildComponentAssignments ->', state.lastComponentAssignmentError);
            return [];
        }
        if (!Array.isArray(state.symbolDetections) || state.symbolDetections.length === 0) {
            state.componentAssignments = [];
            renderComponentAssignments([]);
            state.lastComponentAssignmentError = 'Brak wykrytych symboli. Wykonaj detekcję symboli lub załaduj historię symboli.';
            setSpiceStatus(state.lastComponentAssignmentError, 'warning');
            console.debug('[lineSeg] buildComponentAssignments ->', state.lastComponentAssignmentError);
            return [];
        }
        if (!sourcesAlignedWithDetections(state.lastNetlist)) {
            const msg = 'Historia detekcji symboli nie pasuje do źródła netlisty; brak przypisań komponentów.';
            console.warn('[lineSeg] buildComponentAssignments ->', msg);
            state.componentAssignments = [];
            renderComponentAssignments([]);
            state.lastComponentAssignmentError = msg;
            setSpiceStatus(msg, 'warning');
            return [];
        }

        const netLabelMap = state.lastNetlist.metadata && typeof state.lastNetlist.metadata === 'object'
            ? state.lastNetlist.metadata.net_labels || state.lastNetlist.metadata.netLabels || {}
            : {};
        const nodeLookup = new Map();
        state.lastNetlist.nodes.forEach((node) => {
            if (node && node.id) {
                nodeLookup.set(node.id, node);
            }
        });

        const assignments = [];
        state.symbolDetections.forEach((detection, index) => {
            const component = mapDetectionToComponent(
                detection,
                state.lastNetlist.nodes,
                netLabelMap,
                nodeLookup,
                index,
            );
            if (component) {
                assignments.push(component);
            }
        });

    state.componentAssignments = assignments;
    renderComponentAssignments(assignments);
    if (assignments.length === 0) {
        const msg = 'Nie znaleziono dopasowań detekcji do netlisty. Sprawdź poziomy confidence i reguły mapowania etykiet.';
        state.lastComponentAssignmentError = msg;
        setSpiceStatus(msg, 'warning');
        console.debug('[lineSeg] buildComponentAssignments -> no assignments. Detections:', state.symbolDetections, 'netlist nodes count:', state.lastNetlist?.nodes?.length);
    }
        return assignments;
    }

    async function exportSpice() {
        if (!state.lastNetlist) {
            setSpiceStatus('Najpierw wygeneruj netlistę.', 'error');
            return;
        }

        if (netlistExportBtn) {
            netlistExportBtn.disabled = true;
        }
        const assignments = buildComponentAssignments();
        if (!assignments.length) {
            const reason = state.lastComponentAssignmentError || 'Brak przypisań komponentów.';
            setSpiceStatus(`Eksportuję do SPICE (komponenty: 0). Powód: ${reason}`, 'warning');
        } else {
            setSpiceStatus(`Eksportuję do SPICE (komponenty: ${assignments.length})...`);
        }

        const payload = {
            netlist: state.lastNetlist,
            components: assignments,
            storeHistory: !!storeHistoryCheckbox?.checked,
        };

        try {
            const response = await fetch(SEGMENT_SPICE_ENDPOINT, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });

            if (!response.ok) {
                const errorPayload = await response.json().catch(() => ({}));
                const message = errorPayload?.error || `HTTP ${response.status}`;
                setSpiceStatus(`Błąd eksportu: ${message}`, 'error');
                return;
            }

            const data = await response.json();
            renderSpice(data);
            const rawComponentCount = data?.metadata?.componentCount;
            const numericCount = Number(rawComponentCount);
            const componentCount = Number.isFinite(numericCount) ? numericCount : null;
            if (componentCount !== null) {
                if (componentCount === 0) {
                    const reason = state.lastComponentAssignmentError || 'Brak przypisań komponentów.';
                    setSpiceStatus(`Eksport SPICE zakończony (komponenty: ${componentCount}). Powód: ${reason}`, 'warning');
                } else {
                    setSpiceStatus(`Eksport SPICE zakończony (komponenty: ${componentCount}).`, 'success');
                }
            } else {
                setSpiceStatus('Eksport SPICE zakończony.', 'success');
            }
            if (data.historyEntry) {
                upsertHistoryEntry(data.historyEntry);
            } else if (storeHistoryCheckbox?.checked) {
                void fetchHistoryEntries();
            }
        } catch (error) {
            console.error('Błąd eksportu SPICE', error);
            setSpiceStatus('Błąd eksportu SPICE.', 'error');
        } finally {
            if (netlistExportBtn) {
                netlistExportBtn.disabled = !state.lastNetlist;
            }
        }
    }

    function setFixtureInfo(message) {
        if (fixtureInfo) {
            fixtureInfo.textContent = message;
        }
    }

    function getFixtureById(id) {
        if (!id) {
            return null;
        }
        return state.fixtures.find((item) => item.id === id) || null;
    }

    function renderFixtureInfo(fixture, { loaded = false, pendingLoad = false } = {}) {
        if (!fixture) {
            setFixtureInfo('Brak wybranej próbki.');
            return;
        }
        const expectedSegments = fixture?.expected?.segments;
        const expectedNodes = fixture?.expected?.nodes;
        const expectedSummary = `Oczekiwane odcinki: ${Number.isFinite(expectedSegments) ? expectedSegments : '—'}, węzły: ${Number.isFinite(expectedNodes) ? expectedNodes : '—'}.`;
        if (loaded) {
            setFixtureInfo(`Załadowano „${fixture.name}”. ${expectedSummary}`);
        } else if (pendingLoad) {
            setFixtureInfo(`Wybrano „${fixture.name}”. ${expectedSummary} Kliknij „Załaduj próbkę”.`);
        } else {
            setFixtureInfo(expectedSummary);
        }
    }

    function populateFixtureSelect(fixtures) {
        if (!fixtureSelect) {
            return;
        }
        const currentValue = fixtureSelect.value;
        fixtureSelect.innerHTML = '';
        const defaultOption = document.createElement('option');
        defaultOption.value = '';
        defaultOption.textContent = 'Brak (wybierz, aby wczytać wzorzec)';
        fixtureSelect.append(defaultOption);
        fixtures.forEach((fixture) => {
            const option = document.createElement('option');
            option.value = fixture.id;
            option.textContent = fixture.name;
            fixtureSelect.append(option);
        });
        if (fixtures.some((fixture) => fixture.id === currentValue)) {
            fixtureSelect.value = currentValue;
            state.selectedFixtureId = currentValue;
            const selected = getFixtureById(currentValue);
            renderFixtureInfo(selected, {
                loaded: state.activeFixtureId === currentValue,
                pendingLoad: state.activeFixtureId !== currentValue,
            });
        } else {
            fixtureSelect.value = '';
            state.selectedFixtureId = null;
            if (fixtures.length === 0) {
                setFixtureInfo('Brak próbek do wyświetlenia.');
            } else {
                setFixtureInfo('Brak wybranej próbki.');
            }
        }
    }

    async function loadFixtureIndex() {
        if (state.fixturesLoaded || state.fixturesLoading) {
            return;
        }
        state.fixturesLoading = true;
        try {
            const response = await fetch(FIXTURES_INDEX_URL, {
                method: 'GET',
                headers: { Accept: 'application/json' },
            });
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const payload = await response.json();
            const fixtures = Array.isArray(payload?.fixtures) ? payload.fixtures : [];
            state.fixtures = fixtures;
            state.fixturesLoaded = true;
            populateFixtureSelect(fixtures);
            if (fixtures.length === 0) {
                setFixtureInfo('Brak dostępnych próbek testowych.');
            }
        } catch (error) {
            console.error('Nie udało się pobrać próbek testowych', error);
            state.fixturesError = true;
            setFixtureInfo('Nie udało się pobrać próbek testowych.');
        } finally {
            state.fixturesLoading = false;
        }
    }

    function resetResultView(options = {}) {
        const { resetDiagnostic = true } = options;
        setSummary();
        setDebugList(debugList, []);
        if (resultPre) {
            resultPre.textContent = '{}';
        }
        state.segmentIndex = new Map();
        clearHighlightedSegment({ silent: true, redraw: false, syncDiagnostic: resetDiagnostic });
        updateHighlightControls();
        clearOverlay();
        renderNetlist(null);
        renderSpice(null);
    state.componentAssignments = [];
        setSpiceStatus('Brak eksportu SPICE.');
        if (netlistBtn) {
            netlistBtn.disabled = true;
        }
        if (netlistExportBtn) {
            netlistExportBtn.disabled = true;
        }
        state.lastResult = null;
        if (resetDiagnostic && diagnosticChat && typeof diagnosticChat.reset === 'function') {
            diagnosticChat.reset();
        }
    }

    function resetSource() {
        if (state.localFileUrl) {
            URL.revokeObjectURL(state.localFileUrl);
            state.localFileUrl = null;
        }
        state.pendingLocalFile = null;
        state.sourceEntry = null;
        state.sourceOrigin = null;
        state.activeFixtureId = null;
        state.lastResult = null;
        state.lastNetlist = null;
        state.segmentIndex = new Map();
    state.componentAssignments = [];
        clearHighlightedSegment({ silent: true, redraw: false, syncDiagnostic: true });
        updateHighlightControls();
        setStatus('Wczytaj źródło segmentacji.');
        if (runBtn) {
            runBtn.disabled = true;
        }
        if (netlistBtn) {
            netlistBtn.disabled = true;
        }
        if (sourceImage) {
            sourceImage.src = '';
        }
        clearOverlay();
        clearSymbolOverlay();
        resetSymbolOverlayState();
        setSymbolStatus(SYMBOL_STATUS_DEFAULT, 'muted');
        toggleVisibility(sourceImage, sourcePlaceholder, false);
        markSourceStageEmpty(true);
        state.baseOffset = { x: 0, y: 0 };
        state.offsetReady = false;
    state.suppressClick = false;
    state.panMoved = false;
        resetViewTransform();
        const selected = getFixtureById(state.selectedFixtureId);
        if (selected) {
            renderFixtureInfo(selected, { pendingLoad: true });
        }
        notifySourceObservers(null);
        resetConnectorPanel({ preserveFingerprint: false, fallbackToSource: false });
        updateHistoryIdLabel();
    }

    function updateSource(entry, origin) {
        if (!entry || !entry.url) {
            resetSource();
            return;
        }
        const fixtureUrl = pickFixtureUrl(entry);
        const serverUrl = [
            fixtureUrl,
            entry.originalUrl,
            entry.meta?.originalUrl,
            entry.meta?.source?.url,
            entry.meta?.source?.imageUrl,
            entry.url,
            entry.imageUrl,
            entry.previewUrl,
            entry.objectUrl,
        ].find((candidate) => candidate && typeof candidate === 'string' && !/^data:/i.test(candidate)) || null;
        const normalizedEntry = {
            ...entry,
            fixtureUrl: fixtureUrl || entry.fixtureUrl || null,
            serverUrl: serverUrl || entry.serverUrl || null,
        };
        if (fixtureUrl && !normalizedEntry.originalUrl) {
            normalizedEntry.originalUrl = fixtureUrl;
        }
        // Jeśli brakuje historyId/id, spróbuj wyciągnąć token z URL jako fallback
        if (!normalizedEntry.historyId && !normalizedEntry.history_id && !normalizedEntry.id) {
            const token = extractTokenFromUrl(normalizedEntry.url || normalizedEntry.imageUrl || normalizedEntry.serverUrl);
            if (token) {
                normalizedEntry.historyId = token;
            }
        }
        clearOverlay();
        clearSymbolOverlay();
        resetSymbolOverlayState();
        state.sourceEntry = normalizedEntry;
        state.sourceOrigin = origin || null;
        if (origin !== 'local') {
            state.pendingLocalFile = null;
        }
        if (origin !== 'fixture') {
            state.activeFixtureId = null;
            const selected = getFixtureById(state.selectedFixtureId);
            if (selected) {
                renderFixtureInfo(selected, { pendingLoad: true });
            }
        }
        if (sourceImage) {
            const displayUrl = cacheBustUrl(normalizedEntry.url);
            console.debug('[lineSeg] updateSource setting src ->', displayUrl, 'origin=', origin);
            sourceImage.onload = () => {
                console.debug('[lineSeg] sourceImage loaded ->', displayUrl);
                measureBaseOffset();
            };
            sourceImage.onerror = (err) => {
                console.warn('[lineSeg] sourceImage failed to load ->', displayUrl, err);
            };
            sourceImage.src = displayUrl;
        }
        toggleVisibility(sourceImage, sourcePlaceholder, true);
        markSourceStageEmpty(false);
        state.offsetReady = Boolean(sourceImage && sourceImage.complete);
        if (sourceImage && sourceImage.complete) {
            measureBaseOffset();
        }
        state.suppressClick = false;
        state.panMoved = false;
        resetViewTransform();
        if (runBtn) {
            runBtn.disabled = false;
        }
        setStatus(`Źródło: ${entry.label || entry.url}`);
        if (state.sourceOrigin === 'local') {
            setSymbolStatus('Wyślij obraz na serwer, aby wczytać obrysy symboli.', 'muted');
        } else {
            void refreshSymbolOverlayForSource();
        }
        notifySourceObservers();
        state.edgeConnectorFingerprint = deriveEdgeConnectorFingerprint();
        if (!state.lastNetlist) {
            renderConnectorMatches([], { fingerprint: state.edgeConnectorFingerprint });
            if (state.edgeConnectorFingerprint && state.edgeConnectorFingerprint.candidates.length) {
                setConnectorStatus('Źródło ma przypisany historyId – kliknij „Odśwież”, aby zobaczyć konektory.', 'info');
            } else {
                setConnectorStatus('Brak przypisanego historyId dla bieżącego źródła.', 'muted');
            }
        }
        updateHistoryIdLabel();
        updateRoiAvailability();
    }

    function resolvePayloadImageUrl(entry) {
        if (!entry) return null;
        const meta = entry.meta && typeof entry.meta === 'object' ? entry.meta : {};
        const sourceSrc = sourceImage?.src || null;
        const sourceCurrentSrc = sourceImage?.currentSrc || null;
        // Prefer serwerowe URL-e (fixtures/uploads) zamiast data URI, żeby payload był kompatybilny z backendem
        const ordered = [
            entry.fixtureUrl,
            entry.serverUrl,
            entry.originalUrl,
            meta.originalUrl,
            meta.source?.url,
            meta.source?.imageUrl,
            entry.imageUrl,
            meta.imageUrl,
            entry.previewUrl,
            sourceCurrentSrc,
            sourceSrc,
            entry.url,
            entry.objectUrl,
        ];
        for (const candidate of ordered) {
            if (candidate && typeof candidate === 'string' && !/^data:/i.test(candidate)) {
                return candidate;
            }
        }
        return entry.serverUrl || entry.url || entry.objectUrl || entry.originalUrl || entry.previewUrl || sourceCurrentSrc || sourceSrc || null;
    }

    async function loadFromLocalFile(file) {
        if (!file) {
            return;
        }
        if (state.localFileUrl) {
            URL.revokeObjectURL(state.localFileUrl);
        }
        const objectUrl = URL.createObjectURL(file);
        state.localFileUrl = objectUrl;
        state.pendingLocalFile = file;
        state.selectedFixtureId = null;
        state.activeFixtureId = null;
        if (fixtureSelect) {
            fixtureSelect.value = '';
        }
        renderFixtureInfo(null);
        const entry = {
            url: objectUrl,
            label: file.name,
        };
        const nameToken = extractTokenFromName(file.name);
        if (nameToken) {
            entry.historyId = nameToken;
        }
        updateSource(entry, 'local');

        // Jeśli użytkownik chce automatycznie zapisać kopię przy wczytaniu, zrób upload natychmiast
        // Wymuszamy upload od razu, żeby mieć token i historyId
        const autoSave = true;

        if (autoSave) {
            setStatus(`💾 Wysyłam plik na serwer: ${file.name}...`);
            try {
                const uploadedEntry = await uploadLocalFile(file);
                updateSource(uploadedEntry, 'upload');
                setStatus(`✅ Załadowano obraz: ${uploadedEntry.label || uploadedEntry.url}.`);
            } catch (err) {
                console.error('Upload failed during loadFromLocalFile', err);
                setStatus('⚠ Nie udało się przesłać pliku na serwer — zostanie wysłany przed segmentacją.');
            }
        } else {
            setStatus(`Załadowano obraz z dysku: ${file.name}. Zostanie przesłany przed segmentacją.`);
        }
    }

    async function uploadLocalFile(file) {
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch(IMPORT_FRAGMENT_ENDPOINT, {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const payload = await response.json();
        const entry = payload?.entry || payload;
        if (!entry?.url) {
            throw new Error('Brak adresu URL w odpowiedzi importu.');
        }
        return entry;
    }

    async function ensureRemoteSource() {
        if (state.sourceOrigin !== 'local') {
            return true;
        }
        if (!state.pendingLocalFile) {
            setStatus('Brak pliku do przesłania. Wczytaj ponownie obraz z dysku.');
            return false;
        }

        try {
            setStatus('Przesyłanie obrazu na serwer...');
            const uploadedEntry = await uploadLocalFile(state.pendingLocalFile);
            if (state.localFileUrl) {
                URL.revokeObjectURL(state.localFileUrl);
                state.localFileUrl = null;
            }
            state.pendingLocalFile = null;
            updateSource(uploadedEntry, 'upload');
            setStatus(`Załadowano obraz: ${uploadedEntry.label || uploadedEntry.url}.`);
            return true;
        } catch (error) {
            console.error('Nie udało się przesłać pliku na serwer', error);
            setStatus('Nie udało się przesłać pliku na serwer. Spróbuj ponownie.');
            return false;
        }
    }

    async function loadFromRetouchBuffer(options = {}) {
        const skipIfSourcePresent = Boolean(options.skipIfSourcePresent);
        if (skipIfSourcePresent && state.sourceEntry) {
            return false;
        }
        try {
            setStatus('Pobieranie materiału z „Automatyczny retusz”...');
            const response = await fetch(RETOUCH_BUFFER_ENDPOINT, {
                method: 'GET',
                headers: {
                    Accept: 'application/json',
                    'Cache-Control': 'no-cache',
                },
                cache: 'no-store',
            });
            if (response.status === 404) {
                if (state.sourceOrigin !== 'tools') {
                    resetSource();
                }
                setStatus('Brak materiału w buforze retuszu.');
                return false;
            }
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const payload = await response.json();
            const entry = payload?.entry || payload;
            if (!entry?.url) {
                if (state.sourceOrigin !== 'tools') {
                    resetSource();
                }
                setStatus('Odpowiedź nie zawiera adresu obrazu.');
                return false;
            }
            if (skipIfSourcePresent && state.sourceEntry) {
                return false;
            }
            updateSource(entry, 'retouch');
            return true;
        } catch (error) {
            console.error('Nie udało się pobrać bufora retuszu', error);
            if (state.sourceOrigin === 'retouch') {
                resetSource();
            }
            setStatus('Nie można pobrać materiału.');
            return false;
        }
    }

    async function loadFromToolsSource({ showStatus = true } = {}) {
        if (typeof getCanvasRetouchImage !== 'function') {
            if (showStatus) {
                setStatus('Moduł „Narzędzia retuszu” nie jest dostępny.');
            }
            return false;
        }

        if (showStatus) {
            setStatus('Pobieranie obrazu z narzędzi retuszu...');
        }

        const entry = await getCanvasRetouchImage();
        if (!entry || !entry.url) {
            if (showStatus) {
                setStatus('Brak aktywnego obrazu w zakładce „Narzędzia retuszu” lub kanwa jest pusta.');
            }
            return false;
        }
        const targetEntry = {
            url: entry.url,
            objectUrl: entry.objectUrl || entry.url,
            label: entry.label || 'Obraz z „Narzędzi retuszu”',
            id: entry.id || null,
            historyId: entry.historyId || entry.id || null,
            previewUrl: entry.previewUrl || null,
            originalUrl: entry.originalUrl || null,
            meta: entry.meta ? { ...entry.meta } : undefined,
        };

        // Jeśli kanwa zwróciła blob, wyślij go na serwer, aby segmentacja miała dostępny URL
        if (entry.blob instanceof Blob) {
            try {
                const filename = entry.filename || 'canvas-retouch.png';
                const file = new File([entry.blob], filename, { type: entry.blob.type || 'image/png' });
                const uploaded = await uploadLocalFile(file);
                const merged = {
                    ...uploaded,
                    objectUrl: targetEntry.objectUrl,
                    label: targetEntry.label || uploaded.label,
                };
                updateSource(merged, 'canvas-tools');
                if (showStatus) {
                    setStatus('Załadowano obraz z narzędzi retuszu.');
                }
                return true;
            } catch (error) {
                console.error('Nie udało się przesłać obrazu z narzędzi retuszu', error);
                if (showStatus) {
                    setStatus('Nie udało się przesłać obrazu z „Narzędzi retuszu”.');
                }
                return false;
            }
        }

        updateSource(targetEntry, 'canvas-tools');
        if (showStatus) {
            setStatus('Załadowano obraz z narzędzi retuszu.');
        }
        return true;
    }

    function applyFixture(fixture) {
        if (!fixture) {
            setStatus('Najpierw wybierz wzorcową próbkę.');
            return;
        }
        state.activeFixtureId = fixture.id;
        state.selectedFixtureId = fixture.id;
        if (fixtureSelect) {
            fixtureSelect.value = fixture.id;
        }
        if (binaryCheckbox) {
            binaryCheckbox.checked = Boolean(fixture.binary);
        }
        const entry = {
            url: fixture.image,
            originalUrl: fixture.image,
            label: fixture.name,
        };
        updateSource(entry, 'fixture');
        renderFixtureInfo(fixture, { loaded: true });
        const expectedSegments = fixture?.expected?.segments;
        const expectedNodes = fixture?.expected?.nodes;
        const expectationText = [];
        if (Number.isFinite(expectedSegments)) {
            expectationText.push(`odcinki=${expectedSegments}`);
        }
        if (Number.isFinite(expectedNodes)) {
            expectationText.push(`węzły=${expectedNodes}`);
        }
        const expectationSummary = expectationText.length > 0 ? ` (oczekiwane ${expectationText.join(', ')})` : '';
        setStatus(`Załadowano próbkę „${fixture.name}”${expectationSummary}.`);
    }

    function evaluateFixtureComparison(result) {
        if (!state.activeFixtureId) {
            return null;
        }
        const fixture = getFixtureById(state.activeFixtureId);
        if (!fixture || !fixture.expected) {
            return null;
        }
        const expectedSegments = fixture.expected.segments;
        const expectedNodes = fixture.expected.nodes;
        const actualSegments = result.metadata?.merged_segments ?? result.lines?.length ?? 0;
        const actualNodes = result.metadata?.nodes ?? result.nodes?.length ?? 0;

        const checks = [];
        let matches = true;

        if (Number.isFinite(expectedSegments)) {
            if (actualSegments === expectedSegments) {
                checks.push('odcinki ✔️');
            } else {
                checks.push(`odcinki ${actualSegments} (oczekiwano ${expectedSegments})`);
                matches = false;
            }
        }

        if (Number.isFinite(expectedNodes)) {
            if (actualNodes === expectedNodes) {
                checks.push('węzły ✔️');
            } else {
                checks.push(`węzły ${actualNodes} (oczekiwano ${expectedNodes})`);
                matches = false;
            }
        }

        if (!checks.length) {
            return null;
        }

        if (matches) {
            return `Wynik zgodny z próbką „${fixture.name}” (${checks.join(', ')}).`;
        }
        return `Rozbieżność względem „${fixture.name}”: ${checks.join(', ')}.`;
    }

    async function runSegmentation() {
        if (!state.sourceEntry || !state.sourceEntry.url) {
            const visibleFallback = sourceImage?.currentSrc || sourceImage?.src || null;
            if (visibleFallback && typeof visibleFallback === 'string' && !/^data:/i.test(visibleFallback)) {
                state.sourceEntry = {
                    url: visibleFallback,
                    serverUrl: visibleFallback,
                    originalUrl: visibleFallback,
                    fixtureUrl: pickFixtureUrl({ url: visibleFallback }),
                };
                state.sourceOrigin = state.sourceOrigin || 'dom';
                if (runBtn) {
                    runBtn.disabled = false;
                }
            } else {
                alert('Najpierw wczytaj materiał źródłowy.');
                return;
            }
        }

        // Jeśli aktualnie wyświetlany obraz różni się od zapisanego kontekstu, zaktualizuj źródło do widocznego URL
        const visibleUrl = sourceImage?.currentSrc || sourceImage?.src || null;
        if (visibleUrl && typeof visibleUrl === 'string' && !/^data:/i.test(visibleUrl)) {
            const visibleToken = extractTokenFromUrl(visibleUrl);
            const entryToken = extractTokenFromUrl(state.sourceEntry?.serverUrl || state.sourceEntry?.url);
            if (!entryToken || (visibleToken && entryToken && visibleToken !== entryToken)) {
                state.sourceEntry = {
                    ...(state.sourceEntry || {}),
                    url: visibleUrl,
                    serverUrl: visibleUrl,
                    originalUrl: state.sourceEntry?.originalUrl || visibleUrl,
                };
                state.sourceOrigin = state.sourceOrigin || 'dom';
            }
        }

        const ensured = await ensureRemoteSource();
        if (!ensured) {
            return;
        }

        const payload = {
            imageUrl: resolvePayloadImageUrl(state.sourceEntry),
            storeHistory: !!storeHistoryCheckbox?.checked,
            debug: !!debugCheckbox?.checked,
            binary: !!binaryCheckbox?.checked,
        };

        const fixtureUrl = pickFixtureUrl(state.sourceEntry);
        if (fixtureUrl && typeof fixtureUrl === 'string' && !/^data:/i.test(fixtureUrl)) {
            payload.imageUrl = fixtureUrl;
            state.sourceEntry = {
                ...(state.sourceEntry || {}),
                fixtureUrl,
                serverUrl: fixtureUrl,
                originalUrl: state.sourceEntry?.originalUrl || fixtureUrl,
            };
        }

        if (!payload.imageUrl && state.sourceEntry?.url) {
            payload.imageUrl = state.sourceEntry.url;
        }

        // Jeśli mimo wszystko trafiliśmy na data URI, spróbuj jeszcze raz znaleźć serwerowy URL zamiast kanwy
        if (payload.imageUrl && /^data:/i.test(payload.imageUrl)) {
            const nonDataFallbacks = [
                fixtureUrl,
                state.sourceEntry?.serverUrl,
                state.sourceEntry?.originalUrl,
                state.sourceEntry?.meta?.originalUrl,
                state.sourceEntry?.meta?.source?.originalUrl,
                state.sourceEntry?.meta?.source?.url,
                state.sourceEntry?.meta?.source?.imageUrl,
                state.sourceEntry?.imageUrl,
                state.sourceEntry?.previewUrl,
                state.sourceEntry?.url,
                sourceImage?.currentSrc,
                sourceImage?.src,
                state.sourceEntry?.objectUrl,
            ];
            const bestNonData = nonDataFallbacks.find((candidate) => candidate && typeof candidate === 'string' && !/^data:/i.test(candidate));
            if (bestNonData) {
                payload.imageUrl = bestNonData;
            }
        }

        // Dopasuj payload do aktualnie wyświetlanego obrazka (np. gdy testy ustawiły src ręcznie bez zmiany state)
        const displayedUrl = sourceImage?.currentSrc || sourceImage?.src || null;
        if (displayedUrl && typeof displayedUrl === 'string' && !/^data:/i.test(displayedUrl)) {
            const displayToken = extractTokenFromUrl(displayedUrl);
            const payloadToken = extractTokenFromUrl(payload.imageUrl);
            const tokensMismatch = displayToken && payloadToken && displayToken !== payloadToken;
            if (!payload.imageUrl || tokensMismatch || (!payloadToken && payload.imageUrl !== displayedUrl)) {
                payload.imageUrl = displayedUrl;
            }
        }

        // If checkbox is checked, prefer applying an injected ROI directly from sessionStorage into the payload (test helper)
        if (useConnectorRoiCheckbox?.checked) {
            try {
                const rawRoi = sessionStorage.getItem('app:lineSegEdgeConnectorRoi');
                if (rawRoi) {
                    const parsed = JSON.parse(rawRoi);
                    const normalized = normalizeRoi(parsed);
                    if (normalized) {
                        payload.roi = {
                            x: normalized.x,
                            y: normalized.y,
                            width: normalized.width,
                            height: normalized.height,
                        };
                        if (normalized.page !== null && normalized.page !== undefined) {
                            payload.page = normalized.page;
                        }
                    }
                }
            } catch (err) {
                console.warn('[lineSeg] Nie udało się odczytać lub sparsować app:lineSegEdgeConnectorRoi', err);
            }
        }

        // If checkbox is checked but ROI wasn't populated by connector sync, allow sessionStorage-injected ROI (fallback to state)
        if (useConnectorRoiCheckbox?.checked && !payload.roi && !state.edgeConnectorRoi) {
            try {
                const rawRoi = sessionStorage.getItem('app:lineSegEdgeConnectorRoi');
                if (rawRoi) {
                    const parsed = JSON.parse(rawRoi);
                    const normalized = normalizeRoi(parsed);
                    if (normalized) {
                        state.edgeConnectorRoi = normalized;
                        updateRoiAvailability();
                    }
                }
            } catch (err) {
                console.warn('[lineSeg] Nie udało się odczytać lub sparsować app:lineSegEdgeConnectorRoi', err);
            }
        }

        if (useConnectorRoiCheckbox?.checked && state.edgeConnectorRoi && !payload.roi) {
            payload.roi = {
                x: state.edgeConnectorRoi.x,
                y: state.edgeConnectorRoi.y,
                width: state.edgeConnectorRoi.width,
                height: state.edgeConnectorRoi.height,
            };
            if (state.edgeConnectorRoi.page !== null && state.edgeConnectorRoi.page !== undefined) {
                payload.page = state.edgeConnectorRoi.page;
            }
        }

        try {
            setStatus('Segmentacja w toku...');
            clearOverlay();
            clearHighlightedSegment({ silent: true, redraw: false, syncDiagnostic: false });
            state.segmentIndex = new Map();
            updateHighlightControls();
            if (runBtn) runBtn.disabled = true;
            if (diagnosticChat && typeof diagnosticChat.setPending === 'function') {
                diagnosticChat.setPending('Analiza segmentów...');
            }
            const response = await fetch(SEGMENT_LINES_ENDPOINT, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const resultPayload = await response.json();
            const result = resultPayload?.result;
            if (!result) {
                setStatus('Brak danych w odpowiedzi segmentacji.');
                if (diagnosticChat && typeof diagnosticChat.handleError === 'function') {
                    diagnosticChat.handleError('Brak wyników segmentacji.');
                }
                resetResultView({ resetDiagnostic: false });
                return;
            }
            if (resultPayload.historyEntry) {
                upsertHistoryEntry(resultPayload.historyEntry);
            } else if (storeHistoryCheckbox?.checked) {
                void fetchHistoryEntries();
            }
            if (resultPayload.historyEntry?.id && state.sourceEntry && !state.sourceEntry.historyId) {
                state.sourceEntry = {
                    ...state.sourceEntry,
                    historyId: resultPayload.historyEntry.id,
                };
                state.edgeConnectorFingerprint = deriveEdgeConnectorFingerprint();
                updateHistoryIdLabel();
                // Powiadom obserwatorów (np. formularz konektorów) o nowym historyId z segmentacji
                notifySourceObservers();
            }
            state.lastResult = result;
            buildSegmentIndex(result.lines);
            updateHighlightControls();
            if (netlistBtn) {
                netlistBtn.disabled = false;
            }
            drawNodeOverlay(result);
            const metadata = result.metadata || {};
            const skeletonMeta = metadata.skeleton_metadata || {};
            let shape = '--';
            if (Array.isArray(metadata.input_shape) && metadata.input_shape.length >= 2) {
                shape = `${metadata.input_shape[1]}×${metadata.input_shape[0]}`;
            } else if (metadata.input_shape && typeof metadata.input_shape === 'object') {
                const width = toFiniteNumber(metadata.input_shape.width);
                const height = toFiniteNumber(metadata.input_shape.height);
                if (width !== null && height !== null) {
                    shape = `${width}×${height}`;
                }
            } else if (typeof metadata.input_shape === 'string' && metadata.input_shape.trim() !== '') {
                shape = metadata.input_shape;
            }
            const skeletonPixels = formatCount(metadata.skeleton_pixels) || formatCount(skeletonMeta.skeleton_pixels) || '--';
            const binaryBefore = formatCount(skeletonMeta.binary_pixels_before);
            const binaryAfter = formatCount(skeletonMeta.binary_pixels_after);
            let binaryStats = '--';
            if (binaryBefore && binaryAfter) {
                binaryStats = `${binaryBefore} → ${binaryAfter}`;
            }
            if (typeof metadata.binary === 'boolean') {
                const modeLabel = metadata.binary ? 'tryb binarny' : 'skalowanie szarości';
                binaryStats = binaryStats === '--' ? modeLabel : `${binaryStats} (${modeLabel})`;
            }
            const flaggedSegments = extractFlaggedSegments(metadata);
            let flaggedLabel = '--';
            if (flaggedSegments.length > 0) {
                flaggedLabel = String(flaggedSegments.length);
            } else if (Array.isArray(metadata.flagged_segments)) {
                flaggedLabel = String(metadata.flagged_segments.length);
            } else if (metadata.confidence && typeof metadata.confidence === 'object') {
                flaggedLabel = '0';
            }
            setSummary(
                metadata.merged_segments ?? result.lines?.length ?? '--',
                metadata.nodes ?? result.nodes?.length ?? '--',
                metadata.elapsed_ms ? `${metadata.elapsed_ms.toFixed(1)} ms` : '--',
                shape,
                binaryStats,
                skeletonPixels,
                flaggedLabel
            );
            if (diagnosticChat && typeof diagnosticChat.updateContext === 'function') {
                diagnosticChat.updateContext({
                    flaggedSegments,
                    confidenceSummary: metadata.confidence,
                    metadata,
                    sourceEntry: state.sourceEntry,
                    result,
                });
            }
            setDebugList(debugList, result.debugArtifacts || result.debug_artifacts || []);
            if (resultPre) {
                resultPre.textContent = JSON.stringify(result, null, 2);
            }
            const fixtureStatus = evaluateFixtureComparison(result);
            if (fixtureStatus) {
                setStatus(`Segmentacja zakończona. ${fixtureStatus}`);
            } else {
                setStatus('Segmentacja zakończona.');
            }
        } catch (error) {
            console.error('Błąd segmentacji linii', error);
            setStatus('Błąd segmentacji. Sprawdź konsolę.');
            if (diagnosticChat && typeof diagnosticChat.handleError === 'function') {
                diagnosticChat.handleError('Nie udało się przeprowadzić segmentacji.');
            }
            clearHighlightedSegment({ silent: true, redraw: true, syncDiagnostic: false });
        } finally {
            if (runBtn) {
                runBtn.disabled = !(state.sourceEntry && state.sourceEntry.url);
            }
            updateHighlightControls();
        }
    }

    async function runNetlist() {
        if (!state.lastResult) {
            setNetlistStatus('Najpierw uruchom segmentację.');
            return;
        }

        if (netlistBtn) {
            netlistBtn.disabled = true;
        }
        if (netlistExportBtn) {
            netlistExportBtn.disabled = true;
        }
        setNetlistStatus('Generowanie...');
        renderSpice(null);
        setSpiceStatus('Oczekiwanie na wynik netlisty.');

        try {
            const payload = {
                lines: state.lastResult,
                storeHistory: !!storeHistoryCheckbox?.checked,
            };
            // Attach connector history id when available
            const connectorHistoryId = resolveEdgeConnectorHistoryId();
            if (connectorHistoryId) {
                payload.edgeConnectorHistoryId = connectorHistoryId;
            }

            // Prefer sending a server-side symbol history id; fall back to current detections
            const symbolHistoryId = state.symbolSummary?.historyId || null;
            if (symbolHistoryId) {
                payload.symbolHistoryId = symbolHistoryId;
            } else if (Array.isArray(state.symbolDetections) && state.symbolDetections.length) {
                // Send lightweight symbol objects to help server associate symbols with netlist
                payload.symbols = state.symbolDetections.map((d) => ({
                    class: d.class || d.label || null,
                    score: d.score ?? d.confidence ?? null,
                    bbox: d.bbox || null,
                    mask: d.mask || null,
                    meta: d.meta || null,
                }));
            }

            console.debug('[lineSeg] runNetlist payload ->', payload);

            const response = await fetch(SEGMENT_NETLIST_ENDPOINT, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });

            if (!response.ok) {
                const errorPayload = await response.json().catch(() => ({}));
                const message = errorPayload?.error || `HTTP ${response.status}`;
                setNetlistStatus(`Błąd: ${message}`);
                return;
            }

            const data = await response.json();
            console.debug('[lineSeg] runNetlist response ->', data);
            const netlist = data?.netlist;
            if (!netlist) {
                setNetlistStatus('Brak danych netlisty w odpowiedzi.');
                return;
            }

            renderNetlist(netlist);

            // If we sent symbol info but server did not attach symbols to netlist metadata, show warning and use payload as fallback
            try {
                if ((payload && (payload.symbolHistoryId || payload.symbols)) && (!netlist.metadata || !netlist.metadata.symbols || (Array.isArray(netlist.metadata.symbols) && netlist.metadata.symbols.length === 0))) {
                    console.warn('[lineSeg] runNetlist: server did not attach symbol metadata to netlist. Falling back to sent symbols if any.');
                    setSymbolSummaryStatus('Serwer nie powiązał symboli z netlistą. Używam symboli z wysłanego payloadu.', 'warning');

                    // Fallback: if client sent lightweight `symbols` in payload, display them in UI
                    if (payload && Array.isArray(payload.symbols) && payload.symbols.length) {
                        const sentSymbols = payload.symbols;
                        const synthetic = {
                            summary: { count: sentSymbols.length },
                            detector: { name: 'lokalny (payload)' },
                            detections: sentSymbols,
                            historyId: payload.symbolHistoryId || null,
                            source: { label: 'wysłane symbole (fallback)' },
                        };
                        console.debug('[lineSeg] runNetlist: rendering synthetic symbol metadata from payload ->', synthetic);
                        renderSymbolMetadata(synthetic, netlist);
                        // Use same pluralization as main renderer
                        const payloadCountText = (function (n) {
                            const num = Number(n) || 0;
                            if (!num) return `0 symboli`;
                            if (num === 1) return `1 symbol`;
                            if (num >= 2 && num <= 4) return `${num} symbole`;
                            return `${num} symboli`;
                        })(sentSymbols.length);
                        setSymbolSummaryStatus(`Powiązano ${payloadCountText} (z payloadu).`, 'info');
                    }
                }
            } catch (e) {
                console.debug('[lineSeg] runNetlist: warning check failed', e);
            }

            // If netlist lacks edgeConnectors metadata, try to fetch matches using existing fingerprint (if any)
            try {
                if (!netlist.metadata || !Array.isArray(netlist.metadata.edgeConnectors) || netlist.metadata.edgeConnectors.length === 0) {
                    const fingerprint = state.edgeConnectorFingerprint || deriveEdgeConnectorFingerprint();
                    if (fingerprint && fingerprint.candidates && fingerprint.candidates.length) {
                        console.debug('[lineSeg] runNetlist: fetching edge connectors with fingerprint', fingerprint);
                        void syncEdgeConnectorMatches({ force: true, fingerprint });
                    }
                }
            } catch (e) {
                console.debug('[lineSeg] runNetlist: edge connector re-check failed', e);
            }

            if (data.historyEntry) {
                setStatus('Netlista zapisana w historii.');
                upsertHistoryEntry(data.historyEntry);
            } else if (storeHistoryCheckbox?.checked) {
                void fetchHistoryEntries();
            }
        } catch (error) {
            console.error('Błąd generowania netlisty', error);
            setNetlistStatus('Błąd generowania netlisty.');
        } finally {
            if (netlistBtn) {
                netlistBtn.disabled = !state.lastResult;
            }
        }
    }

    if (diagnosticHighlightClearBtn) {
        diagnosticHighlightClearBtn.addEventListener('click', () => {
            clearHighlightedSegment({ silent: false, syncDiagnostic: true });
        });
    }

    if (diagnosticHighlightIsolate) {
        diagnosticHighlightIsolate.addEventListener('change', (event) => {
            if (!state.highlightedSegmentId) {
                event.target.checked = false;
                state.isolateHighlight = false;
                updateHighlightControls();
                return;
            }
            state.isolateHighlight = Boolean(event.target.checked);
            updateHighlightControls();
            if (state.lastResult) {
                drawNodeOverlay(state.lastResult);
            }
            if (diagnosticChat && typeof diagnosticChat.setStatus === 'function') {
                diagnosticChat.setStatus(state.isolateHighlight ? 'Wyświetlam wyłącznie podświetlony odcinek.' : 'Podświetlam odcinek oraz sąsiednie węzły.');
            }
        });
    }

    if (loadRetouchBtn) {
        loadRetouchBtn.addEventListener('click', () => {
            void loadFromRetouchBuffer();
        });
    }

    if (loadToolsBtn) {
        loadToolsBtn.addEventListener('click', () => {
            loadFromToolsSource({ showStatus: true });
        });
    }

    if (loadFileBtn && loadFileInput) {
        loadFileBtn.addEventListener('click', () => {
            loadFileInput.click();
        });
        loadFileInput.addEventListener('change', (event) => {
            const file = event.target.files?.[0];
            if (!file) {
                return;
            }
            void loadFromLocalFile(file);
            loadFileInput.value = '';
        });
    }

    if (historyRefreshBtn) {
        historyRefreshBtn.addEventListener('click', () => {
            void fetchHistoryEntries();
        });
    }

    if (fixtureSelect) {
        fixtureSelect.addEventListener('change', (event) => {
            const selectedId = event.target.value || null;
            state.selectedFixtureId = selectedId;
            const fixture = getFixtureById(selectedId);
            if (fixture) {
                const loaded = state.activeFixtureId === fixture.id;
                renderFixtureInfo(fixture, { loaded, pendingLoad: !loaded });
            } else {
                setFixtureInfo('Brak wybranej próbki.');
            }
        });
    }

    if (loadFixtureBtn) {
        loadFixtureBtn.addEventListener('click', () => {
            const fixture = getFixtureById(state.selectedFixtureId);
            if (!fixture) {
                setStatus('Wybierz najpierw próbkowy obraz z listy.');
                return;
            }
            applyFixture(fixture);
        });
    }

    // Inicjalizacja checkboxa "Użyj ramki schematu (ROI)" — wartość przechowywana w sessionStorage oraz opcjonalny, testowalny wstrzyknięty ROI
    if (useConnectorRoiCheckbox) {
        try {
            const raw = sessionStorage.getItem('app:lineSegUseConnectorRoi');
            if (raw !== null) {
                useConnectorRoiCheckbox.checked = raw === 'true';
            }
            // Test helper: allow injecting an ROI via sessionStorage for deterministic E2E tests
            const rawRoi = sessionStorage.getItem('app:lineSegEdgeConnectorRoi');
            if (rawRoi) {
                try {
                    const parsed = JSON.parse(rawRoi);
                    const normalized = normalizeRoi(parsed);
                    if (normalized) {
                        state.edgeConnectorRoi = normalized;
                        // If checkbox wasn't explicitly set, prefer enabling it when an ROI is injected
                        if (typeof raw === 'undefined' || raw === null) {
                            useConnectorRoiCheckbox.checked = true;
                        }
                        updateRoiAvailability();
                    }
                } catch (err) {
                    console.warn('[lineSeg] Nie udało się sparsować app:lineSegEdgeConnectorRoi', err);
                }
            }
        } catch (err) {
            console.warn('[lineSeg] Nie udało się odczytać sessionStorage dla useConnectorRoi', err);
        }
        useConnectorRoiCheckbox.addEventListener('change', (e) => {
            const val = Boolean(e.target.checked);
            try {
                sessionStorage.setItem('app:lineSegUseConnectorRoi', val ? 'true' : 'false');
            } catch (err) {
                console.warn('[lineSeg] Nie udało się zapisać stanu useConnectorRoi w sessionStorage', err);
            }
            console.debug('[lineSeg] useConnectorRoi set to', val);
            if (val) {
                setStatus(state.edgeConnectorRoiAvailable
                    ? 'ROI włączone – żądania segmentacji będą przycinać do ramki konektora.'
                    : 'ROI zaznaczone, ale brak ramki konektora — użyty zostanie pełny obraz.');
            } else {
                setStatus('ROI wyłączone — segmentacja działa na pełnym obrazie.');
            }
        });
    }

    if (runBtn) {
        runBtn.addEventListener('click', () => {
            void runSegmentation();
        });
    }

    if (netlistBtn) {
        netlistBtn.addEventListener('click', () => {
            void runNetlist();
        });
    }

    if (netlistExportBtn) {
        netlistExportBtn.addEventListener('click', () => {
            void exportSpice();
        });
    }

    if (connectorRefreshBtn) {
        connectorRefreshBtn.addEventListener('click', () => {
            void syncEdgeConnectorMatches({
                force: true,
                fingerprint: state.edgeConnectorFingerprint || deriveEdgeConnectorFingerprint(),
            });
        });
    }


    updateHighlightControls();

    wireZoomControls();

    resetSource();
    resetResultView();
    void loadFixtureIndex();

    return {
        registerSourceObserver,
        getSourceContext,
        ensureSourceUploaded,
        handleRetouchUpdate(entry) {
            if (!entry) {
                if (state.sourceOrigin === 'retouch') {
                    resetSource();
                }
                return;
            }
            const prevOriginal = state.sourceEntry?.originalUrl
                || (state.sourceEntry?.url && !/^data:/i.test(state.sourceEntry.url) ? state.sourceEntry.url : null);
            const derivedOriginal = [
                entry.originalUrl,
                entry.meta?.originalUrl,
                !/^data:/i.test(entry.url || '') ? entry.url : null,
                entry.previewUrl,
                prevOriginal,
            ]
                .find((candidate) => candidate && typeof candidate === 'string' && !/^data:/i.test(candidate))
                || null;
            const fixtureUrl = pickFixtureUrl(entry) || derivedOriginal;
            const targetEntry = {
                url: entry.url,
                objectUrl: entry.objectUrl || entry.url,
                // Zachowaj oryginalny URL (np. fixture), żeby payload nie spadał do data-URL z kanwy
                originalUrl: derivedOriginal || (!/^data:/i.test(entry.url) ? entry.url : null),
                fixtureUrl,
                label: entry.label,
            };
        },
        // Test helpers (E2E): allow tests to inject state or trigger internal renderers
        test__renderNetlist(netlist) {
            try {
                renderNetlist(netlist);
                console.debug('[lineSeg][test] renderNetlist invoked');
            } catch (e) {
                console.error('[lineSeg][test] renderNetlist failed', e);
            }
        },
        test__setSymbolDetections(detections) {
            try {
                state.symbolDetections = Array.isArray(detections) ? detections : [];
                console.debug('[lineSeg][test] setSymbolDetections -> length=', state.symbolDetections.length);
            } catch (e) {
                console.error('[lineSeg][test] setSymbolDetections failed', e);
            }
        },
        test__setSymbolSummary(symbolsMeta) {
            try {
                renderSymbolMetadata(symbolsMeta || null, state.lastNetlist || null);
                console.debug('[lineSeg][test] setSymbolSummary ->', symbolsMeta);
            } catch (e) {
                console.error('[lineSeg][test] setSymbolSummary failed', e);
            }
        },
        test__setLastResult(result) {
            try {
                state.lastResult = result || null;
                console.debug('[lineSeg][test] setLastResult ->', Boolean(state.lastResult));
            } catch (e) {
                console.error('[lineSeg][test] setLastResult failed', e);
            }
        },
        test__runNetlist: async () => {
            try {
                await runNetlist();
                console.debug('[lineSeg][test] runNetlist invoked');
            } catch (e) {
                console.error('[lineSeg][test] runNetlist failed', e);
            }
        },
        test__forceOverwriteStatus(text) {
            try {
                const el = netlistStatus || document.getElementById('lineSegNetlistStatus');
                if (el) el.textContent = text;
                console.debug('[lineSeg][test] forceOverwriteStatus ->', text);
            } catch (e) {
                console.error('[lineSeg][test] forceOverwriteStatus failed', e);
            }
        },
        test__getLastComponentAssignmentError() {
            return state.lastComponentAssignmentError || null;
        },
        test__setSymbolIndex(entries) {
            try {
                state.symbolDetectionIndex = Array.isArray(entries) ? entries : [];
                console.debug('[lineSeg][test] setSymbolIndex -> length=', state.symbolDetectionIndex.length);
            } catch (e) {
                console.error('[lineSeg][test] setSymbolIndex failed', e);
            }
        },
        highlightSegment(segmentId, options = {}) {
            setHighlightedSegment(segmentId, {
                segmentData: options.segmentData ?? null,
                isolate: typeof options.isolate === 'boolean' ? options.isolate : state.isolateHighlight,
                silent: Boolean(options.silent),
                syncDiagnostic: Boolean(options.syncDiagnostic),
            });
        },
        clearHighlight(options = {}) {
            clearHighlightedSegment({
                silent: Boolean(options.silent),
                syncDiagnostic: Boolean(options.syncDiagnostic),
            });
        },
        setHighlightIsolation(enabled) {
            state.isolateHighlight = Boolean(enabled);
            updateHighlightControls();
            if (state.lastResult) {
                drawNodeOverlay(state.lastResult);
            }
        },
        refreshSymbolOverlay(options = {}) {
            return refreshSymbolOverlayForSource(options);
        },
        ingestSymbolDetectionHistory(entry) {
            if (!entry || typeof entry !== 'object') {
                return;
            }
            upsertSymbolDetectionEntry(entry);

            const canOverwrite = !state.sourceEntry
                || state.sourceOrigin === 'fixture'
                || state.sourceOrigin === 'history-auto'
                || state.sourceOrigin === 'symbol-history'
                || state.sourceOrigin === 'symbol-history-fallback';

            if (canOverwrite && !state.pendingLocalFile) {
                let normalized = normalizeSymbolHistoryEntry(entry);
                if (normalized) {
                    updateSource(normalized, 'symbol-history');
                } else {
                    // Fallback: look for payload.source or top-level image fields
                    const payloadSource = entry.payload && typeof entry.payload === 'object' ? entry.payload.source : null;
                    const candidates = [
                        payloadSource?.imageUrl,
                        payloadSource?.url,
                        entry.imageUrl,
                        entry.previewUrl,
                        entry.url,
                    ];
                    const resolved = candidates.find((c) => (isImageUrl(c) || /^data:image\//i.test(c)) && typeof c === 'string');
                    if (resolved) {
                        console.debug('[lineSeg] ingestSymbolDetectionHistory fallback resolved ->', resolved, 'entryId=', entry?.id);
                        normalized = {
                            url: resolved,
                            imageUrl: payloadSource?.imageUrl || entry.imageUrl || resolved,
                            previewUrl: payloadSource?.previewUrl || entry.previewUrl || null,
                            originalUrl: payloadSource?.originalUrl || entry.url || resolved,
                            historyId: payloadSource?.historyId || entry.id || null,
                            label: payloadSource?.label || entry.label || 'Ostatni wynik detekcji',
                            meta: entry.meta ? { ...entry.meta } : undefined,
                        };
                        updateSource(normalized, 'symbol-history-fallback');
                    } else {
                        console.debug('[lineSeg] ingestSymbolDetectionHistory no usable source found for entry', entry?.id);
                    }
                }
            }
            if (state.sourceEntry) {
                void refreshSymbolOverlayForSource({ preferredEntry: entry });
            }
        },
        onTabVisible() {
            state.tabVisible = true;
            void loadFixtureIndex();
            measureBaseOffset();
            applyTransforms();
            updateZoomUI();
            if (state.sourceEntry && state.sourceOrigin !== 'local') {
                void refreshSymbolOverlayForSource();
            }
            void (async () => {
                if (!state.historyLoaded) {
                    await fetchHistoryEntries();
                }

                // Priorytet 1: Spróbuj załadować aktywny obraz z kontekstu globalnego (Detekcja/Upload),
                // jeśli obecne źródło jest "tymczasowe" (fixture, historia automatyczna).
                const canOverride = !state.sourceEntry
                    || state.sourceOrigin === 'fixture'
                    || state.sourceOrigin === 'history-auto';

                if (canOverride) {
                    const processingLoaded = loadFromProcessingOriginal();
                    if (processingLoaded) {
                        return; // Załadowano obraz z detekcji - sukces.
                    }
                }

                // Priorytet 2: Jeśli brak obrazu z detekcji, spróbuj przywrócić ostatnią sesję segmentacji.
                if (!state.sourceEntry || state.sourceOrigin === 'fixture') {
                    autoSelectLatestHistorySource({ allowWhenFixture: true });
                }

                if (state.sourceEntry) {
                    return;
                }

                // Fallbacki
                const retouchLoaded = await loadFromRetouchBuffer({ skipIfSourcePresent: true });
                if (retouchLoaded) {
                    return;
                }
                const toolsLoaded = await loadFromToolsSource({ showStatus: false });
                if (!toolsLoaded) {
                    setStatus('Wczytaj źródło segmentacji przy użyciu jednego z przycisków.');
                }
            })();
        },
        onTabHidden() {
            state.tabVisible = false;
        },
        getHighlightedSegmentId() {
            return state.highlightedSegmentId;
        },
    };
}

function extractTokenFromName(name) {
    if (!name || typeof name !== 'string') {
        return null;
    }
    const base = name.split('/').pop() || name;
    const dotTrimmed = base.replace(/\.[^.]+$/, '');
    const match = dotTrimmed.match(/^([a-zA-Z0-9]+)/);
    if (match && match[1]) {
        return match[1];
    }
    return dotTrimmed || null;
}
