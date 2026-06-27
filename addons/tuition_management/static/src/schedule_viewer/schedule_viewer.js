/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { session } from "@web/session";

// ─── Date helpers ───────────────────────────────────────────────────────────

function getTodayStrInTz(tz) {
    return new Intl.DateTimeFormat("en-CA", { timeZone: tz }).format(new Date());
}

function getMondayStrInTz(tz) {
    const now = new Date();
    const dayName = new Intl.DateTimeFormat("en-US", { timeZone: tz, weekday: "short" }).format(now);
    const todayStr = new Intl.DateTimeFormat("en-CA", { timeZone: tz }).format(now);
    const [y, m, d] = todayStr.split("-").map(Number);
    const dayMap = { Mon: 0, Tue: 1, Wed: 2, Thu: 3, Fri: 4, Sat: 5, Sun: 6 };
    const daysBack = dayMap[dayName] ?? 0;
    return new Date(Date.UTC(y, m - 1, d - daysBack)).toISOString().slice(0, 10);
}

function getMonthStartStrInTz(tz) {
    return getTodayStrInTz(tz).slice(0, 8) + "01";
}

function addDays(dateStr, days) {
    const [y, m, d] = dateStr.split("-").map(Number);
    return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10);
}

function addMonths(dateStr, months) {
    const [y, m] = dateStr.split("-").map(Number);
    const nd = new Date(Date.UTC(y, m - 1 + months, 1));
    return `${nd.getUTCFullYear()}-${String(nd.getUTCMonth() + 1).padStart(2, "0")}-01`;
}

/**
 * Convert midnight in `tz` on `dateStr` to UTC milliseconds.
 * Probes at 10:00 UTC to determine the offset, then shifts midnight accordingly.
 */
function tzMidnightToUtcMs(dateStr, tz) {
    const [y, m, d] = dateStr.split("-").map(Number);
    const probe = new Date(Date.UTC(y, m - 1, d, 10, 0, 0));
    const parts = new Intl.DateTimeFormat("en-US", {
        timeZone: tz,
        year: "numeric", month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit", second: "2-digit",
        hour12: false,
    }).formatToParts(probe);
    const get = type => parseInt(parts.find(p => p.type === type).value);
    const tzLocalMs = Date.UTC(get("year"), get("month") - 1, get("day"), get("hour"), get("minute"), get("second"));
    const offsetMs = tzLocalMs - probe.getTime();
    return Date.UTC(y, m - 1, d, 0, 0, 0) - offsetMs;
}

function msToOdooStr(ms) {
    const d = new Date(ms);
    const p = n => String(n).padStart(2, "0");
    return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())}`;
}

function fmtTimeInTz(utcStr, tz) {
    return new Date(utcStr.replace(" ", "T") + "Z")
        .toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", timeZone: tz });
}

function fmtDateInTz(utcStr, tz) {
    return new Date(utcStr.replace(" ", "T") + "Z")
        .toLocaleDateString([], { weekday: "short", day: "numeric", month: "short", timeZone: tz });
}

// ─── Component ──────────────────────────────────────────────────────────────

class TmScheduleViewer extends Component {
    static template = "tuition_management.ScheduleViewer";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        // Use session tz as a quick initial default; overridden in onWillStart from res.users.tz
        const sessionTz = (session.user_context && session.user_context.tz) || "UTC";

        this.state = useState({
            tz: sessionTz,
            tzSearch: "",
            tzDropdownOpen: false,
            timezones: [],
            viewMode: "today",                      // "today" | "week" | "month"
            periodStart: getTodayStrInTz(sessionTz), // YYYY-MM-DD anchor for current period
            rows: [],
            tutor_id: "",
            student_name: "",
            tutors: [],
            loading: false,
        });

        onWillStart(async () => {
            // get_user_timezone uses self.env.user.tz — always the authenticated user,
            // no UID guessing required
            const [userTz, rawTzList] = await Promise.all([
                this.orm.call("class.schedule", "get_user_timezone", []),
                this.orm.call("class.schedule", "get_common_timezones", []),
            ]);

            this.state.timezones = rawTzList.map(([value, label]) => ({ value, label }));
            this.state.tz = userTz;
            this.state.periodStart = getTodayStrInTz(userTz);

            await Promise.all([this.loadTutors(), this.loadRows()]);
        });
    }

    // ── Computed properties ────────────────────────────────────────────────

    get selectedTzLabel() {
        const found = this.state.timezones.find(t => t.value === this.state.tz);
        return found ? found.label : this.state.tz;
    }

    get periodLabel() {
        const { periodStart, viewMode } = this.state;
        const [y, m, d] = periodStart.split("-").map(Number);
        if (viewMode === "today") {
            return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString(undefined, {
                weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC",
            });
        }
        if (viewMode === "week") {
            const endStr = addDays(periodStart, 6);
            const fmt = str => {
                const [sy, sm, sd] = str.split("-").map(Number);
                return new Date(Date.UTC(sy, sm - 1, sd)).toLocaleDateString(undefined, {
                    day: "numeric", month: "short", year: "numeric", timeZone: "UTC",
                });
            };
            return `${fmt(periodStart)} — ${fmt(endStr)}`;
        }
        // month
        return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString(undefined, {
            month: "long", year: "numeric", timeZone: "UTC",
        });
    }

    get filteredTimezones() {
        const q = this.state.tzSearch.trim().toLowerCase();
        const list = this.state.timezones;
        if (!q) return list;
        return list.filter(t =>
            t.value.toLowerCase().includes(q) || t.label.toLowerCase().includes(q)
        );
    }

    // ── Data loaders ───────────────────────────────────────────────────────

    async loadTutors() {
        const tutors = await this.orm.searchRead("tutor.profile", [], ["id", "name"], { order: "name asc" });
        this.state.tutors = tutors;
    }

    async loadRows() {
        this.state.loading = true;
        const { periodStart, tz, viewMode } = this.state;

        let startDateStr, endDateStr;
        if (viewMode === "today") {
            startDateStr = periodStart;
            endDateStr   = periodStart;
        } else if (viewMode === "week") {
            startDateStr = periodStart;
            endDateStr   = addDays(periodStart, 6);
        } else { // month
            const [y, m] = periodStart.split("-").map(Number);
            startDateStr = periodStart;
            const last = new Date(Date.UTC(y, m, 0)); // day-0 of next month = last day of this month
            endDateStr = `${last.getUTCFullYear()}-${String(last.getUTCMonth() + 1).padStart(2, "0")}-${String(last.getUTCDate()).padStart(2, "0")}`;
        }

        const startUtcMs = tzMidnightToUtcMs(startDateStr, tz);
        const endUtcMs   = tzMidnightToUtcMs(endDateStr,   tz) + 24 * 3600 * 1000 - 1000;

        const domain = [
            ["start_datetime", ">=", msToOdooStr(startUtcMs)],
            ["start_datetime", "<=", msToOdooStr(endUtcMs)],
        ];
        if (this.state.tutor_id) {
            domain.push(["tutor_id", "=", parseInt(this.state.tutor_id)]);
        }
        if (this.state.student_name.trim()) {
            domain.push(["course_id.enrollment_ids.student_id.name", "ilike", this.state.student_name.trim()]);
        }

        const rows = await this.orm.searchRead(
            "class.schedule.occurrence",
            domain,
            ["name", "course_id", "tutor_id", "start_datetime", "stop_datetime", "lesson_status", "attendance_marked"],
            { order: "start_datetime asc" }
        );

        for (const row of rows) {
            row.display_date  = fmtDateInTz(row.start_datetime, tz);
            row.display_start = fmtTimeInTz(row.start_datetime, tz);
            row.display_stop  = fmtTimeInTz(row.stop_datetime,  tz);
            row.course_name   = row.course_id ? row.course_id[1] : "";
            row.tutor_name    = row.tutor_id  ? row.tutor_id[1]  : "";
        }
        this.state.rows = rows;
        this.state.loading = false;
    }

    // ── Event handlers ─────────────────────────────────────────────────────

    async onViewModeClick(ev) {
        await this.switchViewMode(ev.currentTarget.dataset.mode);
    }

    onTzSearchInput(ev) { this.state.tzSearch = ev.target.value; }

    onTzFocus() {
        this.state.tzSearch = "";
        this.state.tzDropdownOpen = true;
    }

    onTzBlur() {
        this.state.tzDropdownOpen = false;
        this.state.tzSearch = "";
    }

    async onTzSelect(ev) {
        ev.preventDefault(); // prevent blur before mousedown completes
        const newTz = ev.currentTarget.dataset.value;
        this.state.tz = newTz;
        this.state.tzSearch = "";
        this.state.tzDropdownOpen = false;
        // Re-anchor period to current date in the new timezone
        const { viewMode } = this.state;
        if (viewMode === "today") {
            this.state.periodStart = getTodayStrInTz(newTz);
        } else if (viewMode === "week") {
            this.state.periodStart = getMondayStrInTz(newTz);
        } else {
            this.state.periodStart = getMonthStartStrInTz(newTz);
        }
        await this.loadRows();
    }

    async switchViewMode(mode) {
        this.state.viewMode = mode;
        const { tz } = this.state;
        if (mode === "today") {
            this.state.periodStart = getTodayStrInTz(tz);
        } else if (mode === "week") {
            this.state.periodStart = getMondayStrInTz(tz);
        } else {
            this.state.periodStart = getMonthStartStrInTz(tz);
        }
        await this.loadRows();
    }

    async prevPeriod() {
        const { viewMode, periodStart } = this.state;
        if (viewMode === "today") {
            this.state.periodStart = addDays(periodStart, -1);
        } else if (viewMode === "week") {
            this.state.periodStart = addDays(periodStart, -7);
        } else {
            this.state.periodStart = addMonths(periodStart, -1);
        }
        await this.loadRows();
    }

    async nextPeriod() {
        const { viewMode, periodStart } = this.state;
        if (viewMode === "today") {
            this.state.periodStart = addDays(periodStart, 1);
        } else if (viewMode === "week") {
            this.state.periodStart = addDays(periodStart, 7);
        } else {
            this.state.periodStart = addMonths(periodStart, 1);
        }
        await this.loadRows();
    }

    async goToday() {
        const { tz, viewMode } = this.state;
        if (viewMode === "today") {
            this.state.periodStart = getTodayStrInTz(tz);
        } else if (viewMode === "week") {
            this.state.periodStart = getMondayStrInTz(tz);
        } else {
            this.state.periodStart = getMonthStartStrInTz(tz);
        }
        await this.loadRows();
    }

    async onTutorChange(ev) {
        this.state.tutor_id = ev.target.value;
        await this.loadRows();
    }

    async onStudentKeydown(ev) {
        if (ev.key === "Enter") await this.loadRows();
    }

    onStudentInput(ev) { this.state.student_name = ev.target.value; }

    async searchStudent() { await this.loadRows(); }

    openOccurrence(ev) {
        const id = parseInt(ev.currentTarget.dataset.id);
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "class.schedule.occurrence",
            res_id: id,
            views: [[false, "form"]],
        });
    }
}

registry.category("actions").add("tm_schedule_viewer", TmScheduleViewer);
