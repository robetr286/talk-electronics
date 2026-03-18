const CHAT_SESSIONS_ENDPOINT = '/api/chat/sessions';

function isObject(value) {
    return value !== null && typeof value === 'object';
}

function toNumber(value) {
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

function extractPoint(value) {
    if (!Array.isArray(value) || value.length < 2) {
        return null;
    }
    const px = toNumber(value[0]);
    const py = toNumber(value[1]);
    if (px === null || py === null) {
        return null;
    }
    return [px, py];
}

function formatCoordinate(point) {
    if (!Array.isArray(point) || point.length < 2) {
        return '--';
    }
    const formatValue = (entry) => {
        if (typeof entry !== 'number' || !Number.isFinite(entry)) {
            return '--';
        }
        return Number.isInteger(entry) ? String(entry) : entry.toFixed(1);
    };
    return `${formatValue(point[0])}, ${formatValue(point[1])}`;
}

function formatLength(value) {
    const numeric = toNumber(value);
    return numeric === null ? '--' : (Number.isInteger(numeric) ? numeric.toString() : numeric.toFixed(1));
}

function formatScore(value) {
    const numeric = toNumber(value);
    return numeric === null ? '--' : numeric.toFixed(2);
}

import { formatTimestamp as tsFormatTimestamp, parseTimestamp } from './utils/timestamp.js';

function formatTimestamp(value) {
    // Delegate to shared util and keep empty-string behavior for falsy values
    if (!value) return '';
    return tsFormatTimestamp(value, { empty: '' });
}

function normalizeFlaggedSegment(segment) {
    if (!isObject(segment)) {
        return null;
    }
    const identifier = segment.id || segment.segment_id || segment.segmentId;
    if (!identifier) {
        return null;
    }
    const score = toNumber(segment.score);
    let label = segment.label || segment.confidence_label || segment.confidenceLabel || null;
    if (!label && score !== null) {
        if (score >= 0.65) {
            label = 'high';
        } else if (score >= 0.45) {
            label = 'medium';
        } else {
            label = 'low';
        }
    }
    return {
        id: String(identifier),
        score,
        label,
        length: toNumber(segment.length),
        reasons: Array.isArray(segment.reasons) ? segment.reasons.map((item) => String(item)) : [],
        start_position: extractPoint(segment.start_position || segment.startPosition),
        end_position: extractPoint(segment.end_position || segment.endPosition),
        start_node: segment.start_node || segment.startNode || null,
        end_node: segment.end_node || segment.endNode || null,
    };
}

function deriveFlaggedSegments(context) {
    const flaggedDirect = Array.isArray(context.flaggedSegments) ? context.flaggedSegments : null;
    if (flaggedDirect && flaggedDirect.length) {
        return flaggedDirect.map(normalizeFlaggedSegment).filter(Boolean);
    }
    const metadata = isObject(context.metadata) ? context.metadata : {};
    const confidence = isObject(context.confidenceSummary)
        ? context.confidenceSummary
        : (isObject(metadata.confidence) ? metadata.confidence : null);
    if (confidence && Array.isArray(confidence.flagged_segments) && confidence.flagged_segments.length) {
        return confidence.flagged_segments.map(normalizeFlaggedSegment).filter(Boolean);
    }
    const flaggedIds = Array.isArray(metadata.flagged_segments) ? metadata.flagged_segments : [];
    if (!flaggedIds.length || !confidence || !isObject(confidence.scores)) {
        return [];
    }
    return flaggedIds
        .map((identifier) => {
            const entry = confidence.scores[identifier];
            if (!isObject(entry)) {
                return normalizeFlaggedSegment({ id: identifier });
            }
            return normalizeFlaggedSegment({ id: identifier, ...entry });
        })
        .filter(Boolean);
}

function buildMessageElement(message) {
    const wrapper = document.createElement('div');
    wrapper.className = 'diagnostic-chat-message';
    wrapper.dataset.role = message.role || 'assistant';

    const content = document.createElement('p');
    content.textContent = message.content || '';
    wrapper.appendChild(content);

    const timestamp = formatTimestamp(message.createdAt);
    if (timestamp) {
        const meta = document.createElement('div');
        meta.className = 'diagnostic-chat-timestamp';
        meta.textContent = timestamp;
        wrapper.appendChild(meta);
    }

    return wrapper;
}

function serializeFlaggedSegments(segments) {
    return segments.map((segment) => ({
        id: segment.id,
        score: segment.score,
        label: segment.label,
        length: segment.length,
        reasons: segment.reasons,
        start_position: segment.start_position,
        end_position: segment.end_position,
        start_node: segment.start_node,
        end_node: segment.end_node,
    }));
}

export function initDiagnosticChat(dom = {}) {
    const {
        panel,
        status,
        flaggedList,
        startBtn,
        chatBox,
        chatLog,
        chatInput,
        sendBtn,
        closeBtn,
    } = dom;

    const state = {
        flaggedSegments: [],
        confidenceSummary: null,
        metadata: null,
        sourceEntry: null,
        session: null,
        loading: false,
        renderedMessageIds: new Set(),
        contextRevision: 0,
        chatOpen: false,
        selectedSegmentId: null,
    };

    const focusListeners = new Set();
    const clearListeners = new Set();

    function notifyFocus(segment, meta = {}) {
        focusListeners.forEach((listener) => {
            try {
                listener(segment, meta);
            } catch (error) {
                console.error('diagnosticChat focus listener error', error);
            }
        });
    }

    function notifyClear(meta = {}) {
        clearListeners.forEach((listener) => {
            try {
                listener(meta);
            } catch (error) {
                console.error('diagnosticChat clear listener error', error);
            }
        });
    }

    function getFlaggedSegment(segmentId) {
        if (!segmentId) {
            return null;
        }
        const key = String(segmentId);
        return state.flaggedSegments.find((segment) => segment && segment.id === key) || null;
    }

    function setStatusText(text) {
        if (status) {
            status.textContent = text;
        }
    }

    function setLoading(flag) {
        state.loading = flag;
        if (startBtn) {
            // Allow user to start diagnostics even if there are no flagged segments yet; disable only while loading
            startBtn.disabled = !!flag;
        }
        if (sendBtn) {
            sendBtn.disabled = flag || !state.session;
        }
        if (chatInput) {
            chatInput.disabled = flag || !state.session;
        }
        if (panel) {
            panel.dataset.loading = flag ? 'true' : 'false';
        }
    }

    function resetChatUi() {
        if (chatLog) {
            chatLog.innerHTML = '';
        }
        if (chatInput) {
            chatInput.value = '';
            chatInput.disabled = true;
        }
        if (sendBtn) {
            sendBtn.disabled = true;
        }
    }

    function toggleChatBox(visible) {
        if (!chatBox) {
            return;
        }
        if (visible) {
            chatBox.classList.remove('hidden');
            state.chatOpen = true;
        } else {
            chatBox.classList.add('hidden');
            state.chatOpen = false;
        }
    }

    function focusChatInput() {
        if (!chatInput) {
            return;
        }
        try {
            chatInput.focus({ preventScroll: true });
        } catch (error) {
            chatInput.focus();
        }
    }

    function selectSegment(segment, options = {}) {
        if (!segment) {
            clearSelection({ silent: options.silent, reason: options.reason });
            return;
        }
        const normalizedId = String(segment.id);
        const {
            silent = false,
            reason = 'user',
            toggle = true,
            force = false,
        } = options;
        if (!force && state.selectedSegmentId === normalizedId) {
            if (toggle) {
                clearSelection({ silent, reason });
            }
            return;
        }
        state.selectedSegmentId = normalizedId;
        renderFlaggedList(state.flaggedSegments);
        if (!silent) {
            notifyFocus(segment, { reason });
            setStatusText(`Podświetlam odcinek ${segment.id}.`);
        }
    }

    function clearSelection(options = {}) {
        const { silent = false, reason = 'user', skipRender = false } = options;
        if (!state.selectedSegmentId) {
            return;
        }
        state.selectedSegmentId = null;
        if (!skipRender) {
            renderFlaggedList(state.flaggedSegments);
        }
        if (!silent) {
            notifyClear({ reason });
            setStatusText('Podświetlenie wyłączone.');
        }
    }

    function setSelection(segmentId, options = {}) {
        if (!segmentId) {
            clearSelection({ silent: options.silent ?? true, reason: options.reason || 'external' });
            return;
        }
        const segment = getFlaggedSegment(segmentId);
        if (!segment) {
            clearSelection({ silent: options.silent ?? true, reason: options.reason || 'external' });
            return;
        }
        selectSegment(segment, {
            silent: options.silent ?? true,
            reason: options.reason || 'external',
            force: true,
            toggle: false,
        });
    }

    function registerSegmentFocus(listener) {
        if (typeof listener === 'function') {
            focusListeners.add(listener);
            return () => focusListeners.delete(listener);
        }
        return () => {};
    }

    function registerSelectionClear(listener) {
        if (typeof listener === 'function') {
            clearListeners.add(listener);
            return () => clearListeners.delete(listener);
        }
        return () => {};
    }

    function renderFlaggedList(segments) {
        if (!flaggedList) {
            return;
        }
        flaggedList.innerHTML = '';
        if (!segments.length) {
            const item = document.createElement('li');
            item.className = 'text-muted small';
            item.textContent = 'Brak oznaczonych odcinków.';
            flaggedList.appendChild(item);
            return;
        }
        const fragment = document.createDocumentFragment();
        segments.forEach((segment) => {
            const item = document.createElement('li');
            item.className = 'diagnostic-flagged-item';
            item.dataset.segmentId = segment.id;
            if (state.selectedSegmentId === segment.id) {
                item.dataset.active = 'true';
            } else if (item.dataset.active) {
                delete item.dataset.active;
            }
            item.tabIndex = 0;
            item.title = 'Kliknij, aby podświetlić w podglądzie.';

            const header = document.createElement('div');
            header.className = 'diagnostic-flagged-item-header';

            const label = document.createElement('span');
            label.className = 'fw-semibold';
            label.textContent = segment.id;
            header.appendChild(label);

            const scorePill = document.createElement('span');
            scorePill.className = 'diagnostic-score-pill';
            const labelValue = segment.label || 'unknown';
            scorePill.dataset.label = labelValue;
            scorePill.textContent = formatScore(segment.score);
            header.appendChild(scorePill);

            item.appendChild(header);

            const metaParts = [];
            if (segment.start_position) {
                metaParts.push(`start: ${formatCoordinate(segment.start_position)}`);
            }
            if (segment.end_position) {
                metaParts.push(`koniec: ${formatCoordinate(segment.end_position)}`);
            }
            if (segment.length !== null && segment.length !== undefined) {
                const lengthText = formatLength(segment.length);
                if (lengthText !== '--') {
                    metaParts.push(`dł.: ${lengthText}`);
                }
            }
            if (metaParts.length) {
                const metaLine = document.createElement('div');
                metaLine.className = 'diagnostic-flagged-item-meta small text-muted';
                metaLine.textContent = metaParts.join(' · ');
                item.appendChild(metaLine);
            }

            if (segment.reasons && segment.reasons.length) {
                const reasons = document.createElement('div');
                reasons.className = 'diagnostic-flagged-item-reasons small text-muted';
                reasons.textContent = `Powody: ${segment.reasons.join(', ')}`;
                item.appendChild(reasons);
            }

            item.addEventListener('click', (event) => {
                event.preventDefault();
                selectSegment(segment, { toggle: true });
            });
            item.addEventListener('keydown', (event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    selectSegment(segment, { toggle: true });
                }
            });

            fragment.appendChild(item);
        });
        flaggedList.appendChild(fragment);
    }

    function renderMessages(messages) {
        if (!Array.isArray(messages) || !chatLog) {
            return;
        }
        const fragment = document.createDocumentFragment();
        messages.forEach((message) => {
            if (!isObject(message)) {
                return;
            }
            const identifier = message.id || `${message.role || 'assistant'}-${message.createdAt || Math.random()}`;
            if (state.renderedMessageIds.has(identifier)) {
                return;
            }
            state.renderedMessageIds.add(identifier);
            fragment.appendChild(buildMessageElement(message));
        });
        if (fragment.childNodes.length > 0) {
            chatLog.appendChild(fragment);
            chatLog.scrollTop = chatLog.scrollHeight;
        }
    }

    async function ensureSession() {
        if (state.session && state.session.id) {
            return state.session;
        }
        if (!state.flaggedSegments.length && !isObject(state.confidenceSummary)) {
            setStatusText('Brak danych do uruchomienia czatu.');
            return null;
        }
        const revision = state.contextRevision;
        setLoading(true);
        try {
            const metadataPayload = state.metadata ? { ...state.metadata } : {};
            const payload = {
                elementId: state.metadata && state.metadata.id ? state.metadata.id : (state.sourceEntry && state.sourceEntry.id ? state.sourceEntry.id : null),
                title: state.sourceEntry && state.sourceEntry.label ? state.sourceEntry.label : 'Segmentacja linii',
                sourceUrl: state.sourceEntry && state.sourceEntry.url ? state.sourceEntry.url : null,
                metadata: metadataPayload,
                flaggedSegments: serializeFlaggedSegments(state.flaggedSegments),
                confidenceSummary: state.confidenceSummary || {},
            };
            if (state.selectedSegmentId) {
                payload.selectedSegmentId = state.selectedSegmentId;
                const selectedSegment = getFlaggedSegment(state.selectedSegmentId);
                if (selectedSegment) {
                    payload.selectedSegment = serializeFlaggedSegments([selectedSegment])[0];
                }
            }
            const response = await fetch(CHAT_SESSIONS_ENDPOINT, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
                const message = typeof data.error === 'string' ? data.error : `HTTP ${response.status}`;
                throw new Error(message);
            }
            if (revision !== state.contextRevision) {
                return state.session;
            }
            const session = isObject(data.session) ? data.session : null;
            state.session = session;
            state.renderedMessageIds.clear();
            if (session && Array.isArray(session.messages)) {
                renderMessages(session.messages);
            }
            setStatusText('Czat gotowy.');
            return state.session;
        } catch (error) {
            console.error('Nie udało się utworzyć sesji diagnostycznej', error);
            state.session = null;
            setStatusText('Nie udało się uruchomić czatu.');
            throw error;
        } finally {
            setLoading(false);
        }
    }

    async function startChat() {
        if (state.loading) {
            return;
        }
        if (!state.flaggedSegments.length) {
            setStatusText('Brak segmentów wymagających uwagi.');
            return;
        }
        toggleChatBox(true);
        setStatusText('Uruchamiam czat diagnostyczny...');
        try {
            const session = await ensureSession();
            if (!session) {
                toggleChatBox(false);
                return;
            }
            if (chatInput) {
                chatInput.disabled = false;
                focusChatInput();
            }
            if (sendBtn) {
                sendBtn.disabled = false;
            }
        } catch (error) {
            toggleChatBox(false);
        }
    }

    async function sendMessage() {
        if (state.loading || !chatInput) {
            return;
        }
        const content = chatInput.value.trim();
        if (!content) {
            setStatusText('Wpisz wiadomość dla czatu diagnostycznego.');
            return;
        }
        const session = await ensureSession().catch(() => null);
        if (!session || !session.id) {
            return;
        }
        const endpoint = `${CHAT_SESSIONS_ENDPOINT}/${encodeURIComponent(session.id)}/messages`;
        setLoading(true);
        try {
            const messagePayload = { content };
            if (state.selectedSegmentId) {
                messagePayload.selectedSegmentId = state.selectedSegmentId;
                const selectedSegment = getFlaggedSegment(state.selectedSegmentId);
                if (selectedSegment) {
                    messagePayload.selectedSegment = serializeFlaggedSegments([selectedSegment])[0];
                }
            }
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(messagePayload),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
                const message = typeof data.error === 'string' ? data.error : `HTTP ${response.status}`;
                throw new Error(message);
            }
            if (isObject(data.session)) {
                state.session = data.session;
            }
            if (Array.isArray(data.messages)) {
                renderMessages(data.messages);
            }
            chatInput.value = '';
            setStatusText('Odpowiedź zaktualizowana.');
        } catch (error) {
            console.error('Nie udało się wysłać wiadomości diagnostycznej', error);
            setStatusText('Nie udało się wysłać wiadomości.');
        } finally {
            setLoading(false);
            if (chatInput && state.session) {
                focusChatInput();
            }
        }
    }

    function closeChat() {
        toggleChatBox(false);
        setStatusText('Czat zamknięty. Możesz wznowić rozmowę w dowolnym momencie.');
    }

    function reset() {
        state.contextRevision += 1;
        state.flaggedSegments = [];
        state.confidenceSummary = null;
        state.metadata = null;
        state.sourceEntry = null;
        state.session = null;
        state.renderedMessageIds.clear();
        state.selectedSegmentId = null;
        notifyClear({ reason: 'reset' });
        resetChatUi();
        renderFlaggedList([]);
        toggleChatBox(false);
        setLoading(false);
        setStatusText('Brak danych.');
    }

    function setPending(message = 'Analiza w toku...') {
        state.contextRevision += 1;
        state.flaggedSegments = [];
        state.session = null;
        state.renderedMessageIds.clear();
        state.selectedSegmentId = null;
        notifyClear({ reason: 'pending' });
        resetChatUi();
        renderFlaggedList([]);
        toggleChatBox(false);
        setLoading(true);
        setStatusText(message);
    }

    function handleError(message = 'Nie udało się zaktualizować danych diagnostycznych.') {
        state.contextRevision += 1;
        state.flaggedSegments = [];
        state.session = null;
        state.renderedMessageIds.clear();
        state.selectedSegmentId = null;
        notifyClear({ reason: 'error' });
        resetChatUi();
        renderFlaggedList([]);
        toggleChatBox(false);
        setLoading(false);
        setStatusText(message);
    }

    function updateContext(context = {}) {
        state.contextRevision += 1;
        state.flaggedSegments = deriveFlaggedSegments(context);
        state.confidenceSummary = isObject(context.confidenceSummary)
            ? context.confidenceSummary
            : (isObject(context.metadata) && isObject(context.metadata.confidence) ? context.metadata.confidence : null);
        state.metadata = isObject(context.metadata) ? context.metadata : {};
        state.sourceEntry = context.sourceEntry || null;
        state.session = null;
        state.renderedMessageIds.clear();
        state.selectedSegmentId = state.flaggedSegments.length > 0 ? state.flaggedSegments[0].id : null;
        resetChatUi();
        renderFlaggedList(state.flaggedSegments);
        toggleChatBox(false);
        setLoading(false);
        if (state.flaggedSegments.length > 0) {
            const first = state.flaggedSegments[0];
            const scoreText = formatScore(first.score);
            setStatusText(`Najniższą pewność ma odcinek ${first.id}${scoreText !== '--' ? ` (ocena ${scoreText})` : ''}.`);
            notifyFocus(first, { reason: 'auto' });
        } else if (state.confidenceSummary) {
            setStatusText('Brak segmentów o niskiej pewności.');
            notifyClear({ reason: 'auto' });
        } else {
            setStatusText('Brak danych.');
            notifyClear({ reason: 'auto' });
        }
    }

    if (startBtn) {
        startBtn.addEventListener('click', () => {
            // UX: when starting diagnostics, enable useful options for line segmentation
            try {
                const storeHistory = document.getElementById('lineSegStoreHistory');
                const debugBox = document.getElementById('lineSegDebug');
                const useRoi = document.getElementById('lineSegUseConnectorRoi');
                if (storeHistory) storeHistory.checked = true;
                if (debugBox) debugBox.checked = true;
                if (useRoi && !useRoi.disabled) useRoi.checked = true;
                setStatusText('Diagnostyka uruchomiona — zaznaczono opcje: Zapis historii, Zachowaj pliki debug, Użyj ROI (jeśli dostępne).');
            } catch (e) {
                console.error('diagnostic start UX enhancement failed', e);
            }
            void startChat();
        });
    }

    // Large hero start button forwards to the small start button (keeps single start flow)
    const bigStart = document.getElementById('diagnosticStartBigBtn');
    if (bigStart) {
        bigStart.addEventListener('click', () => {
            const small = document.getElementById('diagnosticStartChatBtn');
            if (small && !small.disabled) {
                small.click();
                return;
            }
            // Fallback: if small button exists but disabled, call startChat directly
            try {
                void startChat();
            } catch (e) {
                console.error('diagnostic big start failed', e);
            }
        });
    }

    if (sendBtn) {
        sendBtn.addEventListener('click', () => {
            void sendMessage();
        });
    }

    if (closeBtn) {
        closeBtn.addEventListener('click', () => {
            closeChat();
        });
    }

    if (chatInput) {
        chatInput.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                void sendMessage();
            }
        });
    }

    async function refreshReadiness() {
        try {
            const res = await fetch('/api/diagnostics/readiness');
            if (!res.ok) {
                return;
            }
            const data = await res.json();
            // Update checkboxes
            const cbSymbols = document.getElementById('checkbox-symbols');
            const cbNetlist = document.getElementById('checkbox-netlist');
            const cbLabels = document.getElementById('checkbox-labels');
            const cbValues = document.getElementById('checkbox-values');
            const statusEl = document.getElementById('diagnostics-readiness');
            const startBtnSmall = document.getElementById('diagnosticStartBtn');

            if (cbSymbols) cbSymbols.checked = !!data.symbols_detected;
            if (cbNetlist) cbNetlist.checked = !!data.netlist_generated;
            if (cbLabels) {
                const pct = Number.isFinite(data.labels_coverage_pct) ? data.labels_coverage_pct : 0;
                cbLabels.checked = pct >= 80;
                const labelsText = document.getElementById('labels-coverage-pct');
                if (labelsText) labelsText.textContent = `${pct}%`;
            }
            if (cbValues) {
                const pct = Number.isFinite(data.values_coverage_pct) ? data.values_coverage_pct : 0;
                cbValues.checked = pct >= 80;
                const valuesText = document.getElementById('values-coverage-pct');
                if (valuesText) valuesText.textContent = `${pct}%`;
            }
            if (statusEl) statusEl.textContent = data.ready ? '✅ Gotowe do diagnostyki' : '⚠️ Brak wymaganych danych';
            if (startBtnSmall) startBtnSmall.disabled = !data.ready;
        } catch (e) {
            console.error('Failed to refresh readiness', e);
        }
    }

    // Call on reset to populate initial state
    void refreshReadiness();

    // Edit modal handlers
    const editBtn = document.getElementById('diagnosticEditBtn');
    const editModal = document.getElementById('diagnosticEditModal');
    const editTextarea = document.getElementById('diagnosticEditTextarea');
    const editCancel = document.getElementById('diagnosticEditCancel');
    const editSave = document.getElementById('diagnosticEditSave');

    function openEditModal() {
        if (!editModal) return;
        if (editTextarea) editTextarea.value = '';
        editModal.style.display = 'flex';
    }
    function closeEditModal() {
        if (!editModal) return;
        editModal.style.display = 'none';
    }

    if (editBtn) editBtn.addEventListener('click', openEditModal);
    if (editCancel) editCancel.addEventListener('click', closeEditModal);

    if (editSave) {
        editSave.addEventListener('click', async () => {
            if (!editTextarea) return;
            let parsed = null;
            try {
                parsed = JSON.parse(editTextarea.value);
            } catch (e) {
                alert('Niepoprawny JSON. Użyj formatu: {"R1":{"label":"R1","value":"10kΩ"}}');
                return;
            }
            try {
                const res = await fetch('/api/diagnostics/corrections', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ corrections: parsed }),
                });
                if (!res.ok) {
                    const text = await res.text();
                    alert('Błąd zapisu: ' + text);
                    return;
                }
                closeEditModal();
                // Refresh readiness after applying corrections
                await refreshReadiness();
                alert('Poprawki zapisane.');
            } catch (e) {
                console.error('Failed to save corrections', e);
                alert('Błąd sieci podczas zapisu korekt.');
            }
        });
    }

    reset();

    return {
        reset,
        setPending,
        handleError,
        updateContext,
        setSelection,
        clearSelection(options) {
            const payload = options ? { ...options } : {};
            if (!payload.reason) {
                payload.reason = 'external';
            }
            clearSelection(payload);
        },
        registerSegmentFocus,
        registerSelectionClear,
        setStatus: setStatusText,
        refreshReadiness,
    };
}
