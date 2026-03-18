// OCR panel with editable results table and correction saving

let _lastOcrResp = null; // store data from last run for correction payload

// ── Regex: reference designator (R219, C211, Q202, LED201, SW201, U1 …) ──
const _REF_RE = /^[A-Z]{1,4}\d{1,4}$/i;

// ── Regex: wygląda jak wartość elektroniczna (47, 104, 1K, 4K7, 100u/10, 0R1, 2.2K, >1K …) ──
const _VAL_LIKE_RE = /^[>]?\d[\d.,]*\s*[pnuUμmkKMRrΩ]?[\d\/]*[VvWw]?$/;

// ── Znane etykiety sygnałów / zasilania — NIE są wartościami komponentów ──
const _NET_LABEL_RE = /^[+-]?\d*\.?\d*[VvAa]$|^(VCC|VDD|VSS|VEE|GND|AGND|DGND|MCU|CLK|SDA|SCL|MOSI|MISO|CS|RST|EN|NC)([+-]\d+[VvAa]?)?$/i;

function _isRef(text) { return _REF_RE.test(text.trim()); }

function _looksLikeValue(text) {
    const t = text.trim();
    // Wartość elektroniczna: zaczyna się od cyfry (lub >) i zawiera cyfry + opcjonalne jednostki
    return _VAL_LIKE_RE.test(t);
}

function _isNetLabel(text) {
    const t = text.trim();
    // Czyste litery bez cyfr (IR, IN, VCC, GND) lub znane wzorce zasilania (MCU+5V)
    if (_NET_LABEL_RE.test(t)) return true;
    // Tekst złożony tylko z liter (2+ znaki) — prawdopodobnie etykieta sygnału
    if (/^[A-Z]{2,}$/i.test(t) && !_isRef(t)) return true;
    // Tekst z symbolami typowymi dla etykiet (+, spacja) np. "IR VCC", "MCU+5V"
    if (/[+\s]/.test(t) && /[A-Z]{2}/i.test(t)) return true;
    return false;
}

function _dist(a, b) {
    const dx = a.center[0] - b.center[0];
    const dy = a.center[1] - b.center[1];
    return Math.sqrt(dx * dx + dy * dy);
}

/**
 * Paruje tokeny OCR w pary {component, value}.
 *
 * Algorytm:
 * 1. Identyfikuj reference designatory (R219, C211, Q202, LED201 …)
 * 2. Pozostałe tokeny klasyfikuj: wartość elektroniczna vs etykieta sygnału
 * 3. Dla każdego ref szukaj najbliższej WARTOŚCI (nie etykiety) w promieniu 150px
 * 4. Jeśli nie ma wartości w pobliżu — ref dostaje pustą wartość
 * 5. Etykiety sygnałów (MCU+5V, IR, VCC) trafiają jako osobne wiersze z typem net_label
 */
function _tokensToPairs(tokens) {
    if (!tokens || tokens.length === 0) return [];

    const refs = [];
    const values = [];
    const labels = [];

    tokens.forEach(t => {
        let txt = t.text.trim();
        // Oczyszczanie artefaktów OCR: wiodący - lub spacje
        if (/^[-]/.test(txt) && _isRef(txt.replace(/^[-]/, ''))) {
            txt = txt.replace(/^[-]/, '');
            t = { ...t, text: txt };
        }
        if (_isRef(txt)) {
            refs.push(t);
        } else if (_looksLikeValue(txt)) {
            values.push(t);
        } else {
            // Filtruj szum: pojedynczy znak z niskim confidence
            if (txt.length <= 1 && t.confidence < 85) return;
            labels.push(t);
        }
    });

    const usedValues = new Set();
    const pairs = [];

    // Dla każdego ref designatora znajdź najbliższą WARTOŚĆ (nie etykietę)
    refs.forEach(ref => {
        let bestMatch = null;
        let bestDist = Infinity;
        values.forEach(v => {
            if (usedValues.has(v.id)) return;
            const d = _dist(ref, v);
            if (d < bestDist) {
                bestDist = d;
                bestMatch = v;
            }
        });
        if (bestMatch && bestDist < 150) {
            usedValues.add(bestMatch.id);
            pairs.push({ component: ref.text.trim(), value: bestMatch.text.trim() });
        } else {
            pairs.push({ component: ref.text.trim(), value: '' });
        }
    });

    // Niesparowane wartości jako osobne wiersze
    values.forEach(v => {
        if (!usedValues.has(v.id)) {
            pairs.push({ component: '', value: v.text.trim() });
        }
    });

    // Etykiety sygnałów jako osobne wiersze
    labels.forEach(lb => {
        pairs.push({ component: lb.text.trim(), value: '(net_label)' });
    });

    return pairs;
}

/**
 * Rysuje żółte bounding-boxy na overlay canvas.
 * Skaluje współrzędne z rozmiaru oryginału (imgW×imgH) do rozmiaru wyświetlanego.
 */
function _drawBoundingBoxes(tokens, imgW, imgH) {
    const ocrOverlay = document.getElementById('ocrOverlay');
    const ocrImage = document.getElementById('ocrImage');
    if (!ocrOverlay || !ocrImage) return;

    // Rozmiar wyświetlany
    const dispW = ocrImage.clientWidth || ocrImage.width;
    const dispH = ocrImage.clientHeight || ocrImage.height;
    ocrOverlay.width = dispW;
    ocrOverlay.height = dispH;
    ocrOverlay.style.display = 'block';

    const scaleX = dispW / (imgW || 1);
    const scaleY = dispH / (imgH || 1);

    const ctx = ocrOverlay.getContext('2d');
    if (!ctx) return;
    ctx.clearRect(0, 0, dispW, dispH);

    ctx.strokeStyle = '#FFD600';
    ctx.lineWidth = 2;
    ctx.font = `${Math.max(10, 12 * scaleX)}px sans-serif`;
    ctx.fillStyle = 'rgba(255, 214, 0, 0.75)';

    tokens.forEach(t => {
        const [bx, by, bw, bh] = t.bbox;
        const x = bx * scaleX;
        const y = by * scaleY;
        const w = bw * scaleX;
        const h = bh * scaleY;
        ctx.strokeRect(x, y, w, h);
        ctx.fillText(t.text, x, y - 3);
    });
}

function _renderTable(pairs = []) {
    const tbody = document.querySelector('#ocrTable tbody');
    if (!tbody) return;
    tbody.innerHTML = '';
    pairs.forEach((p) => {
        const row = document.createElement('tr');
        // store original values as data attributes for change detection
        row.setAttribute('data-original-component', p.component || '');
        row.setAttribute('data-original-value', p.value || '');
        row.innerHTML = `
            <td><input class="form-control form-control-sm comp-input" value="${p.component || ''}"></td>
            <td><input class="form-control form-control-sm val-input" value="${p.value || ''}"></td>
            <td class="text-center"><button class="btn btn-sm btn-danger delete-row-btn" type="button">×</button></td>
        `;
        tbody.appendChild(row);
    });
    _attachChangeListeners(tbody);
}

function _addEmptyRow() {
    const tbody = document.querySelector('#ocrTable tbody');
    if (!tbody) return;
    const row = document.createElement('tr');
    // mark new rows as manual by default
    row.classList.add('manual');
    row.innerHTML = `
        <td><input class="form-control form-control-sm comp-input"></td>
        <td><input class="form-control form-control-sm val-input"></td>
        <td class="text-center"><button class="btn btn-sm btn-danger delete-row-btn" type="button">×</button></td>
    `;
    tbody.appendChild(row);
    _attachChangeListeners(tbody);
}

function _collectCorrections() {
    const rows = document.querySelectorAll('#ocrTable tbody tr');
    const list = [];
    rows.forEach((r) => {
        const compEl = r.querySelector('.comp-input');
        const valEl = r.querySelector('.val-input');
        if (!compEl || !valEl) return;
        const comp = compEl.value.trim();
        const val = valEl.value.trim();
        if (comp || val) {
            list.push({ component: comp, value: val });
        }
    });
    return list;
}

function _updateRowManualState(row) {
    if (!row) return;
    const comp = row.querySelector('.comp-input')?.value || '';
    const val = row.querySelector('.val-input')?.value || '';
    const origComp = row.getAttribute('data-original-component') || '';
    const origVal = row.getAttribute('data-original-value') || '';
    if (comp !== origComp || val !== origVal) {
        row.classList.add('manual');
    } else {
        row.classList.remove('manual');
    }
}

function _attachChangeListeners(container) {
    if (!container) return;
    container.querySelectorAll('.comp-input, .val-input').forEach((input) => {
        input.addEventListener('input', (e) => {
            const row = e.target.closest('tr');
            _updateRowManualState(row);
        });
    });
}

export function initOcrPanel(dom = {}) {
    const {
        ocrRunBtn,
        ocrResultsJson,
        ocrResults,
        fileInput,
        ocrAddRowBtn,
        ocrSaveCorrectionsBtn,
    } = dom;
    const ocrImage = document.getElementById('ocrImage');

    // when the file input changes, preview the selected image if possible
    const ocrOverlay = document.getElementById('ocrOverlay');
    if (fileInput && ocrImage) {
        fileInput.addEventListener('change', () => {
            const f = fileInput.files[0];
            if (f && f.type.startsWith('image/')) {
                const url = URL.createObjectURL(f);
                ocrImage.src = url;
                ocrImage.style.display = 'block';
                // ensure overlay canvas matches image size once loaded
                ocrImage.onload = () => {
                    if (ocrOverlay) {
                        ocrOverlay.width = ocrImage.width;
                        ocrOverlay.height = ocrImage.height;
                        ocrOverlay.style.display = 'block';
                    }
                };
            }
        });
    }

    if (ocrRunBtn) {
        ocrRunBtn.addEventListener('click', async () => {
            if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
                if (ocrResultsJson) ocrResultsJson.textContent = 'Brak załadowanego pliku!';
                return;
            }
            if (ocrResultsJson) ocrResultsJson.textContent = 'Wykonywanie OCR...';
            const form = new FormData();
            form.append('file', fileInput.files[0]);
            try {
                const resp = await fetch('/ocr/paddle', {
                    method: 'POST',
                    body: form,
                });
                const data = await resp.json();
                _lastOcrResp = data;
                if (ocrResultsJson) {
                    ocrResultsJson.textContent = JSON.stringify(data, null, 2);
                }

                // Pobierz tokeny i wymiary obrazu
                const tokens = data.tokens || (data.pages && data.pages[0] && data.pages[0].tokens) || [];
                const page = (data.pages && data.pages[0]) || {};
                const imgW = page.width || 1;
                const imgH = page.height || 1;

                // Paruj tokeny w pary komponent↔wartość i wypełnij tabelę
                const pairs = _tokensToPairs(tokens);
                _renderTable(pairs);

                // Narysuj żółte bounding boxy na overlay canvas
                _drawBoundingBoxes(tokens, imgW, imgH);
            } catch (err) {
                if (ocrResultsJson) {
                    ocrResultsJson.textContent = 'Błąd: ' + err;
                }
            }
        });
    }

    if (ocrAddRowBtn) {
        ocrAddRowBtn.addEventListener('click', () => {
            // Zablokuj dodawanie, jeśli ostatni wiersz jest pusty
            const lastRow = document.querySelector('#ocrTable tbody tr:last-child');
            if (lastRow) {
                const lastComp = (lastRow.querySelector('.comp-input')?.value || '').trim();
                const lastVal  = (lastRow.querySelector('.val-input')?.value  || '').trim();
                if (!lastComp && !lastVal) {
                    lastRow.querySelector('.comp-input')?.focus();
                    lastRow.style.outline = '2px solid #dc3545';
                    setTimeout(() => { lastRow.style.outline = ''; }, 1500);
                    return;
                }
            }
            _addEmptyRow();
            // Auto-scroll w dół i ustaw fokus na nowym wierszu
            const wrap = document.getElementById('ocrTableWrap');
            if (wrap) wrap.scrollTop = wrap.scrollHeight;
            const newRow = document.querySelector('#ocrTable tbody tr:last-child');
            if (newRow) newRow.querySelector('.comp-input')?.focus();
        });
    }

    if (ocrSaveCorrectionsBtn) {
        ocrSaveCorrectionsBtn.addEventListener('click', async () => {
            if (!_lastOcrResp) return;
            const corrections = _collectCorrections();
            const payload = {
                request_id: _lastOcrResp.request_id,
                corrections,
            };
            try {
                const resp = await fetch('/ocr/paddle/corrections', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                const data = await resp.json();
                if (ocrResultsJson) {
                    ocrResultsJson.textContent = JSON.stringify(data, null, 2);
                }
            } catch (err) {
                if (ocrResultsJson) {
                    ocrResultsJson.textContent = 'Błąd zapisu: ' + err;
                }
            }
        });
    }

    // image click adds a new row tagged with coordinates and draws a box
    if (ocrImage) {
        ocrImage.addEventListener('click', (evt) => {
            const rect = ocrImage.getBoundingClientRect();
            const x = evt.clientX - rect.left;
            const y = evt.clientY - rect.top;
            _addEmptyRow();
            const rows = document.querySelectorAll('#ocrTable tbody tr');
            if (rows.length) {
                const last = rows[rows.length - 1];
                last.setAttribute('data-click-x', x.toFixed(1));
                last.setAttribute('data-click-y', y.toFixed(1));
            }
            if (ocrOverlay) {
                const ctx = ocrOverlay.getContext('2d');
                if (ctx) {
                    ctx.strokeStyle = 'red';
                    ctx.lineWidth = 2;
                    const boxSize = 40; // fixed small box
                    ctx.strokeRect(x - boxSize/2, y - boxSize/2, boxSize, boxSize);
                }
            }
        });
    }

    // delegate delete buttons
    document.addEventListener('click', (evt) => {
        if (evt.target && evt.target.matches('.delete-row-btn')) {
            const row = evt.target.closest('tr');
            if (row) row.remove();
        }
    });
}
