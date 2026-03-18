export function parseTimestamp(value) {
    if (value instanceof Date) return Number.isFinite(value.getTime()) ? value : null;
    if (typeof value === 'number' && Number.isFinite(value)) return new Date(value);
    if (typeof value === 'string' && value.trim()) {
        const parsed = Date.parse(value);
        if (Number.isFinite(parsed)) return new Date(parsed);
    }
    return null;
}

export function formatTimestamp(value, opts = {}) {
    const empty = opts.empty !== undefined ? opts.empty : '—';
    const date = parseTimestamp(value);
    if (!date) return empty;
    try {
        const pad = (n) => String(n).padStart(2, '0');
        const tzParts = date.toLocaleTimeString([], { timeZoneName: 'short' }).split(' ');
        const tz = tzParts[tzParts.length - 1] || '';
        return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())} ${tz}`.trim();
    } catch (err) {
        // Fallback to ISO if locale formatting fails
        return date.toISOString();
    }
}
