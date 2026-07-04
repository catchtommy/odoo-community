/** @odoo-module **/

// ─── Dependency-free date / timezone helpers (Intl-based, no luxon) ────────

export function getTodayStrInTz(tz) {
    return new Intl.DateTimeFormat("en-CA", { timeZone: tz }).format(new Date());
}

export function addDays(dateStr, days) {
    const [y, m, d] = dateStr.split("-").map(Number);
    return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10);
}

export function tzMidnightToUtcMs(dateStr, tz) {
    const [y, m, d] = dateStr.split("-").map(Number);
    const probe = new Date(Date.UTC(y, m - 1, d, 10, 0, 0));
    const parts = new Intl.DateTimeFormat("en-US", {
        timeZone: tz,
        year: "numeric", month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit", second: "2-digit",
        hour12: false,
    }).formatToParts(probe);
    const get = (type) => parseInt(parts.find((p) => p.type === type).value);
    const tzLocalMs = Date.UTC(get("year"), get("month") - 1, get("day"), get("hour"), get("minute"), get("second"));
    const offsetMs = tzLocalMs - probe.getTime();
    return Date.UTC(y, m - 1, d, 0, 0, 0) - offsetMs;
}

export function msToOdooStr(ms) {
    const d = new Date(ms);
    const p = (n) => String(n).padStart(2, "0");
    return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())}`;
}

/** Parse an Odoo "YYYY-MM-DD HH:mm:ss" (UTC, naive) datetime string into a JS Date. */
export function toJsDate(odooDatetimeStr) {
    if (!odooDatetimeStr) {
        return null;
    }
    return new Date(odooDatetimeStr.replace(" ", "T") + "Z");
}

/** Format an Odoo UTC datetime string as a locale time-of-day in `tz` (no hardcoded 12h/24h). */
export function fmtTimeInTz(odooDatetimeStr, tz) {
    const d = toJsDate(odooDatetimeStr);
    if (!d) {
        return "";
    }
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", timeZone: tz });
}

/** Format an Odoo UTC datetime string as a calendar date (YYYY-MM-DD) in `tz`. */
export function fmtDateInTz(odooDatetimeStr, tz) {
    const d = toJsDate(odooDatetimeStr);
    if (!d) {
        return "";
    }
    return new Intl.DateTimeFormat("en-CA", { timeZone: tz }).format(d);
}

export function fmtLongDateInTz(dateStr) {
    const [y, m, d] = dateStr.split("-").map(Number);
    const dt = new Date(Date.UTC(y, m - 1, d));
    return dt.toLocaleDateString(undefined, {
        weekday: "long", year: "numeric", month: "long", day: "numeric", timeZone: "UTC",
    });
}

export function fmtShortDateInTz(dateStr) {
    const [y, m, d] = dateStr.split("-").map(Number);
    const dt = new Date(Date.UTC(y, m - 1, d));
    return dt.toLocaleDateString(undefined, {
        weekday: "short", month: "short", day: "numeric", timeZone: "UTC",
    });
}

export function mondayOfDateStr(dateStr) {
    const [y, m, d] = dateStr.split("-").map(Number);
    const weekday = new Date(Date.UTC(y, m - 1, d)).getUTCDay(); // 0=Sun..6=Sat
    const diffToMonday = weekday === 0 ? -6 : 1 - weekday;
    return addDays(dateStr, diffToMonday);
}

export function getMondayStrInTz(tz) {
    return mondayOfDateStr(getTodayStrInTz(tz));
}

/** True if the local calendar day `dayStr` (in `tz`) overlaps [shift.start_datetime, shift.end_datetime]. */
export function dayContainsShift(dayStr, shift, tz) {
    const dayStartMs = tzMidnightToUtcMs(dayStr, tz);
    const dayEndMs = dayStartMs + 24 * 3600 * 1000;
    const shiftStartMs = toJsDate(shift.start_datetime).getTime();
    const shiftEndMs = toJsDate(shift.end_datetime).getTime();
    return shiftStartMs < dayEndMs && shiftEndMs > dayStartMs;
}
