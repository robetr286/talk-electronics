/* ignoreZones.js - prosty moduł do rysowania stref ignorowanych
 * - tryby: rect, poly, brush
 * - zapis/odczyt do localStorage
 * - eksport JSON (widoczny w UI)
 * - nie integruje jeszcze z backendem (stub: use localStorage)
 */

export function initIgnoreZones(dom = {}, opts = {}) {
    const canvas = document.getElementById('ignoreCanvas');
    const wrapper = document.getElementById('ignoreCanvasWrapper');
    if (!canvas) return { enabled: false };

    const ctx = canvas.getContext('2d');
    canvas.style.cursor = 'crosshair';
    const modeRectBtn = document.getElementById('ignoreModeRect');
    const modePolyBtn = document.getElementById('ignoreModePoly');
    const modeBrushBtn = document.getElementById('ignoreModeBrush');
    const brushSizeInput = document.getElementById('ignoreBrushSize');
    const saveBtn = document.getElementById('ignoreSaveBtn');
    const loadBtn = document.getElementById('ignoreLoadBtn');
    const clearBtn = document.getElementById('ignoreClearBtn');
    const undoBtn = document.getElementById('ignoreUndoBtn');
    const historyList = document.getElementById('ignoreHistoryList');
    const exportPre = document.getElementById('ignoreExport');
    const statusLabel = document.getElementById('ignoreStatus');

    const STORAGE_KEY = 'app:ignore_zones:v1';
    const HISTORY_KEY = 'app:ignore_zones:history:v1';

    let mode = 'rect';
    let drawing = false;
    let start = null;
    let tempPoly = [];
    let objects = []; // each object: {type: 'rect'|'poly'|'brush', points: [[x,y],...], brushSize}
    let bgImage = null; // { element: HTMLImageElement, src: string }
    // viewport: scale and offsets applied when drawing image and overlays
    let viewport = { scale: 1.0, offsetX: 0, offsetY: 0 };
    const MIN_SCALE = 0.1;
    const MAX_SCALE = 5.0;
    let isPanning = false;
    let panStart = null;
    let polyHover = null;
    let polySnapActive = false;
    const POLY_SNAP_PX = 12;
    const HANDLE_HIT_PX = 12;
    let hoverHandle = null;
    let activeHandle = null;
    let handleDragJustFinished = false;
    let handleClickBlockTimer = null;
    const perSourceSnapshots = new Map();
    let currentSourceKey = null;
    let currentSourceMeta = null;

    function setMode(m) {
        mode = m;
        modeRectBtn.classList.toggle('active', m === 'rect');
        modePolyBtn.classList.toggle('active', m === 'poly');
        modeBrushBtn.classList.toggle('active', m === 'brush');
        if (mode !== 'poly') {
            polyHover = null;
            polySnapActive = false;
        }
        setHoverHandle(null);
        applyCanvasCursor();
    }

    function applyCanvasCursor() {
        if (!canvas) return;
        if (isPanning || activeHandle) {
            canvas.style.cursor = 'grabbing';
            return;
        }
        if (hoverHandle) {
            canvas.style.cursor = hoverHandle.cursor || 'pointer';
            return;
        }
        canvas.style.cursor = 'crosshair';
    }

    function formatTimestamp(value) {
        if (!value) return '---';
        try {
            const date = new Date(value);
            if (Number.isNaN(date.getTime())) return value;
            const pad = (n) => String(n).padStart(2, '0');
            const tzParts = date.toLocaleTimeString([], { timeZoneName: 'short' }).split(' ');
            const tz = tzParts[tzParts.length - 1] || '';
            return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())} ${tz}`.trim();
        } catch (err) {
            return value || '---';
        }
    }

    function handlesEqual(a, b) {
        if (!a && !b) return true;
        if (!a || !b) return false;
        if (a.objectIndex !== b.objectIndex || a.type !== b.type) return false;
        if (a.type === 'rect') return a.corner === b.corner;
        if (a.type === 'poly') return a.vertexIndex === b.vertexIndex;
        return false;
    }

    function setHoverHandle(handle) {
        if (handlesEqual(hoverHandle, handle)) return;
        hoverHandle = handle;
        applyCanvasCursor();
    }

    function resetHandleState() {
        hoverHandle = null;
        activeHandle = null;
        handleDragJustFinished = false;
        if (handleClickBlockTimer) {
            clearTimeout(handleClickBlockTimer);
            handleClickBlockTimer = null;
        }
        applyCanvasCursor();
    }

    function cloneObjectsList(list = []) {
        return list.map((obj) => ({
            ...obj,
            points: Array.isArray(obj.points) ? obj.points.map((pt) => pt.slice()) : [],
        }));
    }

    function makeSourceKey(meta = {}) {
        const kind = meta.kind || meta.source || meta.type;
        if (!kind) return null;
        if (kind === 'pdf') {
            const token = meta.token || meta.documentToken || meta.filename || 'pdf';
            const page = meta.page ?? meta.currentPage ?? 0;
            return `pdf:${token}:${page}`;
        }
        if (kind === 'crop') {
            const ref = meta.id || meta.historyId || meta.label || meta.url || 'crop';
            return `crop:${ref}`;
        }
        if (kind === 'retouch') {
            const ref = meta.id || meta.bufferId || meta.label || 'canvas';
            return `retouch:${ref}`;
        }
        return `${kind}:${meta.id || meta.url || meta.label || 'default'}`;
    }

    function rememberCurrentSource() {
        if (!currentSourceKey) return;
        perSourceSnapshots.set(currentSourceKey, cloneObjectsList(objects));
    }

    function applySourceSnapshot(key) {
        if (!key) {
            objects = [];
            return;
        }
        const snapshot = perSourceSnapshots.get(key);
        objects = snapshot ? cloneObjectsList(snapshot) : [];
    }

    function switchToSource(meta) {
        const nextKey = makeSourceKey(meta) || null;
        if (currentSourceKey !== nextKey) {
            rememberCurrentSource();
            currentSourceKey = nextKey;
            currentSourceMeta = meta || null;
            applySourceSnapshot(nextKey);
            tempPoly = [];
            polyHover = null;
            polySnapActive = false;
            resetHandleState();
        } else {
            currentSourceMeta = meta || currentSourceMeta;
        }
        render();
        updateExportAndStatus();
    }

    function rectBounds(points) {
        const [a, b] = arrayRectPoints(points);
        if (!a || !b) return null;
        return {
            left: Math.min(a[0], b[0]),
            right: Math.max(a[0], b[0]),
            top: Math.min(a[1], b[1]),
            bottom: Math.max(a[1], b[1]),
        };
    }

    function normalizeBounds(bounds) {
        if (!bounds) return null;
        return {
            left: Math.min(bounds.left, bounds.right),
            right: Math.max(bounds.left, bounds.right),
            top: Math.min(bounds.top, bounds.bottom),
            bottom: Math.max(bounds.top, bounds.bottom),
        };
    }

    function rectCornerPositions(obj) {
        if (!obj || !obj.points) return null;
        const bounds = normalizeBounds(rectBounds(obj.points));
        if (!bounds) return null;
        return {
            tl: [bounds.left, bounds.top],
            tr: [bounds.right, bounds.top],
            br: [bounds.right, bounds.bottom],
            bl: [bounds.left, bounds.bottom],
        };
    }

    function rectHandlePoints(obj) {
        const corners = rectCornerPositions(obj);
        if (!corners) return [];
        return [corners.tl, corners.tr, corners.br, corners.bl];
    }

    function getHandlePosition(handle) {
        if (!handle) return null;
        const obj = objects[handle.objectIndex];
        if (!obj) return null;
        if (handle.type === 'rect') {
            const corners = rectCornerPositions(obj);
            return corners ? corners[handle.corner] : null;
        }
        if (handle.type === 'poly') {
            if (!Array.isArray(obj.points)) return null;
            return obj.points[handle.vertexIndex] || null;
        }
        return null;
    }

    function hitTestHandle(pos) {
        if (!pos) return null;
        const threshold = (HANDLE_HIT_PX / (viewport.scale || 1));
        let closest = null;
        let closestDist = Infinity;
        objects.forEach((obj, index) => {
            if (!obj || !obj.points) return;
            if (obj.type === 'rect') {
                const corners = rectCornerPositions(obj);
                if (!corners) return;
                ['tl', 'tr', 'br', 'bl'].forEach((corner) => {
                    const point = corners[corner];
                    if (!point) return;
                    const dist = Math.hypot(pos[0] - point[0], pos[1] - point[1]);
                    if (dist <= threshold && dist < closestDist) {
                        closestDist = dist;
                        closest = {
                            objectIndex: index,
                            type: 'rect',
                            corner,
                            cursor: (corner === 'tl' || corner === 'br') ? 'nwse-resize' : 'nesw-resize',
                        };
                    }
                });
            } else if (obj.type === 'poly') {
                obj.points.forEach((point, vertexIndex) => {
                    if (!point) return;
                    const dist = Math.hypot(pos[0] - point[0], pos[1] - point[1]);
                    if (dist <= threshold && dist < closestDist) {
                        closestDist = dist;
                        closest = {
                            objectIndex: index,
                            type: 'poly',
                            vertexIndex,
                            cursor: 'move',
                        };
                    }
                });
            }
        });
        return closest;
    }

    function applyHandleDrag(handle, pos) {
        if (!handle) return;
        const obj = objects[handle.objectIndex];
        if (!obj) return;
        if (handle.type === 'rect') {
            const bounds = rectBounds(obj.points);
            if (!bounds) return;
            if (handle.corner === 'tl' || handle.corner === 'bl') bounds.left = pos[0];
            if (handle.corner === 'tr' || handle.corner === 'br') bounds.right = pos[0];
            if (handle.corner === 'tl' || handle.corner === 'tr') bounds.top = pos[1];
            if (handle.corner === 'bl' || handle.corner === 'br') bounds.bottom = pos[1];
            const normalized = normalizeBounds(bounds);
            if (normalized) {
                obj.points = [[normalized.left, normalized.top], [normalized.right, normalized.bottom]];
            }
        } else if (handle.type === 'poly') {
            if (!Array.isArray(obj.points) || obj.points.length <= handle.vertexIndex) return;
            obj.points[handle.vertexIndex] = pos.slice();
        }
    }

    function startHandleDrag(handle) {
        if (!handle) return;
        activeHandle = handle;
        handleDragJustFinished = false;
        if (handleClickBlockTimer) {
            clearTimeout(handleClickBlockTimer);
            handleClickBlockTimer = null;
        }
        setHoverHandle(null);
        applyCanvasCursor();
    }

    function stopHandleDrag() {
        if (!activeHandle) return;
        activeHandle = null;
        handleDragJustFinished = true;
        if (handleClickBlockTimer) clearTimeout(handleClickBlockTimer);
        handleClickBlockTimer = setTimeout(() => {
            handleDragJustFinished = false;
            handleClickBlockTimer = null;
        }, 0);
        applyCanvasCursor();
        render();
        updateExportAndStatus();
    }

    function updateHandleHover(pos) {
        if (!pos) return;
        if (activeHandle || isPanning || drawing) return;
        if (mode === 'poly' && tempPoly.length > 0) {
            setHoverHandle(null);
            return;
        }
        const hit = hitTestHandle(pos);
        if (hit) setHoverHandle(hit);
        else setHoverHandle(null);
    }

    function undoLast() {
        if (tempPoly.length > 0) {
            tempPoly.pop();
            if (tempPoly.length === 0) {
                polyHover = null;
                polySnapActive = false;
            }
            render();
            return;
        }
        if (objects.length === 0) {
            statusLabel.textContent = 'Brak stref do cofnięcia.';
            return;
        }
        const removed = objects.pop();
        resetHandleState();
        render();
        updateExportAndStatus();
        statusLabel.textContent = `Cofnięto ostatnią strefę (${removed.type}).`;
    }

    function clearCanvas() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
    }

    function render() {
        clearCanvas();
        // background: either white or image
        ctx.save();
        if (bgImage && bgImage.element && bgImage.element.complete) {
            try {
                // draw image with viewport transform
                ctx.save();
                const dpr = window.devicePixelRatio || 1;
                const t = viewport.scale * dpr;
                ctx.setTransform(t, 0, 0, t, viewport.offsetX * dpr, viewport.offsetY * dpr);
                const iw = bgImage.element.naturalWidth || bgImage.element.width;
                const ih = bgImage.element.naturalHeight || bgImage.element.height;
                ctx.drawImage(bgImage.element, 0, 0, iw, ih);
                ctx.restore();
            } catch (err) {
                // fallback to fill
                ctx.fillStyle = '#fff';
                ctx.fillRect(0, 0, canvas.width, canvas.height);
            }
        } else {
            ctx.fillStyle = '#fff';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
        }
        ctx.restore();

        function drawVertexHandles(points, color = '#0d6efd', radiusPx = 4) {
            if (!points || points.length === 0) return;
            ctx.save();
            const handleRadius = Math.max(2, radiusPx / (viewport.scale || 1));
            ctx.fillStyle = '#fff';
            ctx.strokeStyle = color;
            for (const [hx, hy] of points) {
                ctx.beginPath();
                ctx.arc(hx, hy, handleRadius, 0, Math.PI * 2);
                ctx.fill();
                ctx.stroke();
            }
            ctx.restore();
        }

        function drawHandleHighlight(handle, color = '#ffc107') {
            const pos = getHandlePosition(handle);
            if (!pos) return;
            ctx.save();
            ctx.lineWidth = Math.max(1, 2 / (viewport.scale || 1));
            ctx.strokeStyle = color;
            ctx.beginPath();
            ctx.arc(pos[0], pos[1], Math.max(4, 6 / (viewport.scale || 1)), 0, Math.PI * 2);
            ctx.stroke();
            ctx.restore();
        }

        // draw objects using the same viewport transform
        ctx.save();
        const dpr = window.devicePixelRatio || 1;
        const t = viewport.scale * dpr;
        ctx.setTransform(t, 0, 0, t, viewport.offsetX * dpr, viewport.offsetY * dpr);
        // keep stroke visible regardless of zoom by scaling the line width inversely
        const overlayStroke = Math.max(1, 2 / (viewport.scale || 1));
        ctx.lineWidth = overlayStroke;
        // draw objects
        ctx.strokeStyle = '#d9534f';
        ctx.lineWidth = 2;
        ctx.fillStyle = 'rgba(217,83,79,0.12)';

        for (const obj of objects) {
            if (obj.type === 'rect') {
                const [[x1, y1], [x2, y2]] = arrayRectPoints(obj.points);
                const x = Math.min(x1, x2);
                const y = Math.min(y1, y2);
                const w = Math.abs(x2 - x1);
                const h = Math.abs(y2 - y1);
                ctx.fillRect(x, y, w, h);
                ctx.strokeRect(x + 0.5, y + 0.5, w, h);
                drawVertexHandles(rectHandlePoints(obj), '#d9534f');
            } else if (obj.type === 'poly' || obj.type === 'brush') {
                if (!obj.points || obj.points.length === 0) continue;
                ctx.beginPath();
                ctx.moveTo(obj.points[0][0], obj.points[0][1]);
                for (let i = 1; i < obj.points.length; i++) ctx.lineTo(obj.points[i][0], obj.points[i][1]);
                if (obj.type === 'poly') ctx.closePath();
                ctx.fill();
                ctx.stroke();
                if (obj.type === 'poly') drawVertexHandles(obj.points, '#d9534f');
            }
        }

        if (hoverHandle) drawHandleHighlight(hoverHandle, '#ffc107');
        if (activeHandle) drawHandleHighlight(activeHandle, '#0d6efd');

        // draw temp poly preview
        if (mode === 'poly' && tempPoly && tempPoly.length > 0) {
            ctx.save();
            const dpr = window.devicePixelRatio || 1;
            const t = viewport.scale * dpr;
            ctx.setTransform(t, 0, 0, t, viewport.offsetX * dpr, viewport.offsetY * dpr);
            ctx.lineWidth = Math.max(1, 2 / (viewport.scale || 1));
            ctx.strokeStyle = '#5bc0de';
            ctx.setLineDash([5, 3]);
            ctx.beginPath();
            ctx.moveTo(tempPoly[0][0], tempPoly[0][1]);
            for (let i = 1; i < tempPoly.length; i++) ctx.lineTo(tempPoly[i][0], tempPoly[i][1]);
            ctx.stroke();
            // show preview line to hovered position
            if (polyHover) {
                ctx.beginPath();
                const last = tempPoly[tempPoly.length - 1];
                ctx.moveTo(last[0], last[1]);
                ctx.lineTo(polyHover[0], polyHover[1]);
                ctx.strokeStyle = polySnapActive ? '#198754' : '#0d6efd';
                ctx.setLineDash([4, 2]);
                ctx.stroke();
            }
            // draw vertices (highlight first point)
            drawVertexHandles(tempPoly, '#0d6efd');
            if (tempPoly.length > 0) {
                const first = tempPoly[0];
                ctx.fillStyle = polySnapActive ? '#198754' : '#0d6efd';
                ctx.strokeStyle = '#ffffff';
                const r = Math.max(3, 5 / (viewport.scale || 1));
                ctx.beginPath();
                ctx.arc(first[0], first[1], r, 0, Math.PI * 2);
                ctx.fill();
                ctx.stroke();
            }
            ctx.restore();
        }

        ctx.restore();
    }

    function arrayRectPoints(points) {
        // normalize rect points to two corners
        if (!points || points.length === 0) return [[0, 0], [0, 0]];
        if (points.length >= 2) return [points[0], points[points.length - 1]];
        return [points[0], points[0]];
    }

    function pointerPos(e) {
        const rect = canvas.getBoundingClientRect();
        // account for canvas border (clientLeft/clientTop) so coordinates map to
        // the inner drawing area exactly — fixes small misalignments when canvas
        // has a border or the wrapper uses additional offsets
        const bx = canvas.clientLeft || 0;
        const by = canvas.clientTop || 0;
        const cx = e.clientX - rect.left - bx;
        const cy = e.clientY - rect.top - by;
        // convert screen coords to image space coords using inverse viewport transform
        const ix = (cx - viewport.offsetX) / viewport.scale;
        const iy = (cy - viewport.offsetY) / viewport.scale;
        return [ix, iy];
    }

    function finalizePoly() {
        if (tempPoly.length < 3) return false;
        objects.push({ type: 'poly', points: tempPoly.slice() });
        tempPoly = [];
        polyHover = null;
        polySnapActive = false;
        render();
        updateExportAndStatus();
        return true;
    }

    canvas.addEventListener('contextmenu', (e) => {
        e.preventDefault();
    });

    canvas.addEventListener('mousedown', (e) => {
        // allow panning via middle button, right button or holding space
        const usingSpace = !!window._spaceKeyDown;
        const isMiddle = e.button === 1;
        const isRight = e.button === 2;
        if (mode === 'poly' && isRight) {
            e.preventDefault();
            finalizePoly();
            return;
        }
        if (isMiddle || usingSpace || (isRight && mode !== 'poly')) {
            isPanning = true;
            panStart = { x: e.clientX, y: e.clientY };
            applyCanvasCursor();
            return;
        }
        const pos = pointerPos(e);
        if (e.button === 0 && !(mode === 'poly' && tempPoly.length > 0)) {
            const hit = hitTestHandle(pos);
            if (hit) {
                startHandleDrag(hit);
                return;
            }
        }
        if (mode === 'poly') return; // poly uses click-to-add
        drawing = true;
        start = pos;
        if (mode === 'brush') {
            objects.push({ type: 'brush', points: [start.slice()], brushSize: parseInt(brushSizeInput.value || 10, 10) });
        }
    });

    canvas.addEventListener('mousemove', (e) => {
        const pos = pointerPos(e);
        if (isPanning) {
            const dx = e.clientX - panStart.x;
            const dy = e.clientY - panStart.y;
            panStart = { x: e.clientX, y: e.clientY };
            viewport.offsetX += dx;
            viewport.offsetY += dy;
            render();
            return;
        }
        if (activeHandle) {
            applyHandleDrag(activeHandle, pos);
            render();
            return;
        }
        if (mode === 'poly' && tempPoly.length > 0) {
            polyHover = pos.slice();
            polySnapActive = false;
            if (polyHover) {
                const first = tempPoly[0];
                const dx = polyHover[0] - first[0];
                const dy = polyHover[1] - first[1];
                const threshold = (POLY_SNAP_PX / (viewport.scale || 1));
                if (Math.hypot(dx, dy) <= threshold) {
                    polyHover = first.slice();
                    polySnapActive = true;
                }
            }
            render();
        } else if (!drawing) {
            updateHandleHover(pos);
        }

        if (!drawing) return;
        setHoverHandle(null);
        if (mode === 'rect') {
            // preview using last temp object (draw in image-space via transform)
            render();
            ctx.save();
            const dpr = window.devicePixelRatio || 1;
            const t = viewport.scale * dpr;
            ctx.setTransform(t, 0, 0, t, viewport.offsetX * dpr, viewport.offsetY * dpr);
            ctx.setLineDash([6, 4]);
            ctx.strokeStyle = '#5bc0de';
            const x = Math.min(start[0], pos[0]);
            const y = Math.min(start[1], pos[1]);
            const w = Math.abs(pos[0] - start[0]);
            const h = Math.abs(pos[1] - start[1]);
            ctx.strokeRect(x + 0.5, y + 0.5, w, h);
            // draw a small grid inside preview rectangle to aid precision
            const GRID_COLS = 8;
            const GRID_ROWS = 8;
            // choose grid color with contrast so it is visible on light and dark areas
            ctx.strokeStyle = 'rgba(0,0,0,0.25)';
            ctx.lineWidth = Math.max(1, 1 / (viewport.scale || 1));
            for (let cx = 1; cx < GRID_COLS; cx++) {
                const gx = x + (w * cx) / GRID_COLS;
                ctx.beginPath();
                ctx.moveTo(gx, y);
                ctx.lineTo(gx, y + h);
                ctx.stroke();
            }
            for (let ry = 1; ry < GRID_ROWS; ry++) {
                const gy = y + (h * ry) / GRID_ROWS;
                ctx.beginPath();
                ctx.moveTo(x, gy);
                ctx.lineTo(x + w, gy);
                ctx.stroke();
            }
            ctx.restore();
        } else if (mode === 'brush') {
            // append points to last brush
            const last = objects[objects.length - 1];
            last.points.push(pos.slice());
            render();
        }
    });

    canvas.addEventListener('mouseup', (e) => {
        if (isPanning) {
            isPanning = false;
            panStart = null;
            applyCanvasCursor();
            return;
        }
        if (activeHandle) {
            stopHandleDrag();
            return;
        }
        if (!drawing) return;
        drawing = false;
        const pos = pointerPos(e);
        if (mode === 'rect') {
            objects.push({ type: 'rect', points: [start, pos] });
        }
        start = null;
        render();
        updateExportAndStatus();
    });

    // support loading background image from dependencies
    const loadFromCropBtn = document.getElementById('ignoreLoadFromCropBtn');
    const loadFromRetouchBtn = document.getElementById('ignoreLoadFromRetouchBtn');
    const loadFromPdfBtn = document.getElementById('ignoreLoadFromPdfBtn');

    async function loadImageFromUrl(src) {
        if (!src) return null;
        return new Promise((resolve, reject) => {
            try {
                const img = new Image();
                img.crossOrigin = 'anonymous';
                img.onload = () => resolve(img);
                img.onerror = (e) => reject(new Error('Nie można załadować obrazu: ' + src));
                img.src = src;
            } catch (err) {
                reject(err);
            }
        });
    }

    async function setBackgroundFromSource(obj, meta = null) {
        // obj can be {url, objectUrl} or an Image element
        if (!obj) {
            statusLabel.textContent = 'Brak obrazu źródłowego';
            return false;
        }
        let url = obj.objectUrl || obj.url || obj.previewUrl || obj.lastImageUrl || null;
        if (!url && obj.image && obj.image.src) url = obj.image.src;
        if (!url) {
            statusLabel.textContent = 'Brak URL obrazu w źródle';
            return false;
        }

        try {
            const img = await loadImageFromUrl(url);
            // compute a scale that fits image to wrapper width and available viewport height
            const imgW = img.naturalWidth || img.width || 0;
            const imgH = img.naturalHeight || img.height || 0;
            if (!imgW || !imgH) {
                statusLabel.textContent = 'Niepoprawne wymiary obrazu (0x0)';
                return false;
            }
            const wrapperRect = wrapper.getBoundingClientRect();
            const wrapperW = Math.max(200, wrapperRect.width || wrapper.clientWidth || 800);
            // compute a sensible max height for the preview area (leave margin for header/tabs)
            const maxAvailableHeight = Math.max(200, window.innerHeight - wrapperRect.top - 120);
            // Avoid upscaling small images — fit them into the wrapper without
            // growing them larger than their natural size. Compute width and
            // height fit factors then clamp to maximum 1 (no upscaling).
            const fitScaleWidth = wrapperW / imgW;
            const fitScaleHeight = maxAvailableHeight / imgH;
            let fitScale = Math.min(1, fitScaleWidth, fitScaleHeight);
            if (imgH * fitScale > maxAvailableHeight) {
                fitScale = maxAvailableHeight / imgH;
            }
            // device pixel ratio for crispness
            const dpr = window.devicePixelRatio || 1;
            // displayed size (CSS px)
            const displayW = Math.round(imgW * fitScale);
            const displayH = Math.round(imgH * fitScale);
            // internal canvas buffer size in device pixels
            canvas.width = Math.round(displayW * dpr);
            canvas.height = Math.round(displayH * dpr);
            // set CSS size so canvas displays at computed width/height while
            // preventing overflow of the wrapper
            canvas.style.width = displayW + 'px';
            canvas.style.height = displayH + 'px';
            // ensure wrapper uses the canvas size and centers the canvas
            wrapper.style.display = 'flex';
            wrapper.style.justifyContent = 'center';
            wrapper.style.alignItems = 'center';
            wrapper.style.maxHeight = Math.min(displayH, maxAvailableHeight) + 'px';
            wrapper.style.height = Math.min(displayH, maxAvailableHeight) + 'px';
            // viewport: show image at scaled size, start at 0,0
            // viewport.scale expresses how many CSS pixels correspond to one image pixel
            viewport.scale = fitScale; // CSS px per image pixel
            viewport.offsetX = 0;
            viewport.offsetY = 0;
            bgImage = { element: img, src: url };
            // hide placeholder if present
            const placeholder = document.getElementById('ignoreCanvasPlaceholder');
            if (placeholder) placeholder.classList.add('hidden');
            const sourceMeta = meta || { kind: 'ad-hoc', id: url || Date.now().toString() };
            switchToSource(sourceMeta);
            statusLabel.textContent = 'Załadowano obraz źródłowy';
            return true;
        } catch (err) {
            console.error('load bg failed', err);
            statusLabel.textContent = 'Błąd ładowania obrazu';
            return false;
        }
    }

    if (loadFromCropBtn) {
        loadFromCropBtn.addEventListener('click', async () => {
            statusLabel.textContent = 'Ładuję obraz z kadrowania...';
            const srcObj = opts.getProcessingOriginal ? opts.getProcessingOriginal() : null;
            if (!srcObj) {
                statusLabel.textContent = 'Brak obrazu w zakładce Kadrowanie.';
                return;
            }
            const meta = {
                kind: 'crop',
                id: srcObj.id || srcObj.historyId || srcObj.label || srcObj.url || srcObj.previewUrl || 'crop',
                label: srcObj.label || undefined,
            };
            await setBackgroundFromSource(srcObj, meta);
        });
    }

    if (loadFromRetouchBtn) {
        loadFromRetouchBtn.addEventListener('click', async () => {
            statusLabel.textContent = 'Ładuję obraz z narzędzia retuszu...';
            try {
                const p = opts.getCanvasRetouchImage ? opts.getCanvasRetouchImage() : null;
                const srcObj = p && typeof p.then === 'function' ? await p : p;
                if (!srcObj) {
                    statusLabel.textContent = 'Brak obrazu w narzędziu retuszu.';
                    return;
                }
                const meta = { kind: 'retouch', id: 'canvas-retouch' };
                await setBackgroundFromSource(srcObj, meta);
            } catch (err) {
                console.error(err);
                statusLabel.textContent = 'Błąd ładowania z retuszu';
            }
        });
    }

    if (loadFromPdfBtn) {
        loadFromPdfBtn.addEventListener('click', async () => {
            statusLabel.textContent = 'Ładuję obraz ze strony PDF...';
            try {
                const ctx = opts.getPdfContext ? opts.getPdfContext() : null;
                if (!ctx) {
                    statusLabel.textContent = 'Brak otwartego dokumentu PDF.';
                    return;
                }
                // ctx may include image, lastImageUrl, pageWidthPx/Height
                const meta = {
                    kind: 'pdf',
                    token: ctx.token || ctx.filename || 'pdf',
                    page: ctx.currentPage ?? ctx.page ?? 0,
                    filename: ctx.filename || undefined,
                };
                const ok = await setBackgroundFromSource(ctx, meta);
                if (!ok) statusLabel.textContent = 'Nie udało się załadować podglądu PDF.';
            } catch (err) {
                console.error(err);
                statusLabel.textContent = 'Błąd ładowania strony PDF';
            }
        });
    }

    // click for poly
    canvas.addEventListener('click', (e) => {
        if (mode !== 'poly') return;
        if (handleDragJustFinished) return;
        const pos = pointerPos(e);
        // left click adds point
        tempPoly.push(pos.slice());
        render();
    });

    // double click closes polygon
    canvas.addEventListener('dblclick', (e) => {
        if (mode !== 'poly') return;
        finalizePoly();
    });

    canvas.addEventListener('mouseleave', () => {
        let needsRender = false;
        if (mode === 'poly') {
            polyHover = null;
            polySnapActive = false;
            needsRender = true;
        }
        if (hoverHandle) {
            setHoverHandle(null);
            needsRender = true;
        } else {
            setHoverHandle(null);
        }
        if (needsRender) render();
    });

    // keyboard: Esc clears current poly; space toggles pan-mode while held
    window.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            tempPoly = [];
            polyHover = null;
            polySnapActive = false;
            render();
        }
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
            e.preventDefault();
            undoLast();
            return;
        }
        if (e.code === 'Space') {
            window._spaceKeyDown = true;
        }
    });
    window.addEventListener('keyup', (e) => {
        if (e.code === 'Space') {
            window._spaceKeyDown = false;
        }
    });

    window.addEventListener('mouseup', () => {
        if (isPanning) {
            isPanning = false;
            panStart = null;
            applyCanvasCursor();
        }
        if (activeHandle) {
            stopHandleDrag();
        }
    });

    // Wheel -> zoom (centered at mouse pointer)
    canvas.addEventListener('wheel', (e) => {
        if (!bgImage) return;
        e.preventDefault();
        const rect = canvas.getBoundingClientRect();
        const cx = e.clientX - rect.left;
        const cy = e.clientY - rect.top;
        const beforeX = (cx - viewport.offsetX) / viewport.scale;
        const beforeY = (cy - viewport.offsetY) / viewport.scale;
        // deltaY positive -> zoom out, negative -> zoom in
        const factor = e.deltaY < 0 ? 1.12 : 0.9;
        let newScale = viewport.scale * factor;
        newScale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, newScale));
        // recompute offsets so image point under cursor remains
        viewport.offsetX = cx - beforeX * newScale;
        viewport.offsetY = cy - beforeY * newScale;
        viewport.scale = newScale;
        render();
    }, { passive: false });

    modeRectBtn.addEventListener('click', () => setMode('rect'));
    modePolyBtn.addEventListener('click', () => setMode('poly'));
    modeBrushBtn.addEventListener('click', () => setMode('brush'));
    if (undoBtn) undoBtn.addEventListener('click', () => undoLast());

    clearBtn.addEventListener('click', () => {
        objects = [];
        tempPoly = [];
        polyHover = null;
        polySnapActive = false;
        resetHandleState();
        render();
        updateExportAndStatus();
    });

    saveBtn.addEventListener('click', () => {
        try {
            const payload = { createdAt: new Date().toISOString(), objects };
            // store as single JSON
            localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
            // append to history
            const history = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
            history.push({ id: Date.now(), createdAt: payload.createdAt, payload });
            localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
            statusLabel.textContent = `Zapisano (${payload.createdAt})`;
            updateHistoryList();
        } catch (err) {
            console.error('save ignore zones failed', err);
            statusLabel.textContent = 'Błąd zapisu';
        }
    });

    loadBtn.addEventListener('click', () => {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) {
                statusLabel.textContent = 'Brak zapisanych stref';
                return;
            }
            const parsed = JSON.parse(raw);
            objects = parsed.objects || [];
            resetHandleState();
            render();
            updateExportAndStatus();
            statusLabel.textContent = `Wczytano (${parsed.createdAt ? formatTimestamp(parsed.createdAt) : '---'})`;
        } catch (err) {
            console.error(err);
            statusLabel.textContent = 'Błąd odczytu';
        }
    });

    function updateExportAndStatus() {
        try {
            const out = JSON.stringify({ objects }, null, 2);
            exportPre.textContent = out;
            if (objects.length === 0) statusLabel.textContent = 'Brak stref.';
            if (currentSourceKey) {
                perSourceSnapshots.set(currentSourceKey, cloneObjectsList(objects));
            }
        } catch (err) {
            exportPre.textContent = 'Błąd serializacji';
        }
    }

    function updateHistoryList() {
        const history = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
        if (!history || history.length === 0) {
            historyList.innerHTML = '<li class="processing-history-empty small text-muted">Brak zapisanych stref.</li>';
            return;
        }
        historyList.innerHTML = '';
        history.slice().reverse().forEach((entry) => {
            const li = document.createElement('li');
            li.className = 'processing-history-item small';
            li.innerHTML = `<div class="d-flex justify-content-between align-items-center"><div><strong>${formatTimestamp(entry.createdAt)}</strong><div class="small text-muted">ID: ${entry.id}</div></div><div><button class="btn btn-sm btn-outline-secondary load-entry" data-id="${entry.id}">Wczytaj</button> <button class="btn btn-sm btn-outline-danger delete-entry" data-id="${entry.id}">Usuń</button></div></div>`;
            historyList.appendChild(li);
        });
        // attach handlers
        historyList.querySelectorAll('.load-entry').forEach((btn) => btn.addEventListener('click', (ev) => {
            const id = parseInt(ev.currentTarget.dataset.id, 10);
            const history = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
            const found = history.find((h) => h.id === id);
            if (!found) return;
            objects = found.payload.objects || [];
            resetHandleState();
            render();
            updateExportAndStatus();
            statusLabel.textContent = `Wczytano (${formatTimestamp(found.payload.createdAt)})`;
        }));
        historyList.querySelectorAll('.delete-entry').forEach((btn) => btn.addEventListener('click', (ev) => {
            const id = parseInt(ev.currentTarget.dataset.id, 10);
            let history = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
            history = history.filter((h) => h.id !== id);
            localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
            updateHistoryList();
        }));
    }

    // initial render / load
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (raw) {
            const parsed = JSON.parse(raw);
            objects = parsed.objects || [];
            resetHandleState();
            statusLabel.textContent = `Wczytano (${parsed.createdAt ? formatTimestamp(parsed.createdAt) : '---'})`;
        }
    } catch (err) {
        // ignore
    }
    updateExportAndStatus();
    updateHistoryList();
    render();
    applyCanvasCursor();

    // public API
    return {
        enabled: true,
        clear: () => {
            objects = [];
            tempPoly = [];
            polyHover = null;
            polySnapActive = false;
            resetHandleState();
            render();
            updateExportAndStatus();
        },
        toJSON: () => ({ objects }),
        loadFromJSON: (payload) => { objects = payload.objects || []; resetHandleState(); render(); updateExportAndStatus(); },
    };
}
