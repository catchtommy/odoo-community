/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { session } from "@web/session";
import { _t } from "@web/core/l10n/translation";

// ─── Date helpers (mirrors schedule_viewer.js) ──────────────────────────────

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

function getPrevMonthStartStrInTz(tz) {
    const [y, m] = getMonthStartStrInTz(tz).split("-").map(Number);
    const prev = new Date(Date.UTC(y, m - 2, 1)); // m-1 = current month (0-indexed), -1 more = previous month
    return `${prev.getUTCFullYear()}-${String(prev.getUTCMonth() + 1).padStart(2, "0")}-01`;
}

function addDays(dateStr, days) {
    const [y, m, d] = dateStr.split("-").map(Number);
    return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10);
}

function monthEndStrInTz(dateStr) {
    const [y, m] = dateStr.split("-").map(Number);
    const last = new Date(Date.UTC(y, m, 0)); // day-0 of next month = last day of this month
    return `${last.getUTCFullYear()}-${String(last.getUTCMonth() + 1).padStart(2, "0")}-${String(last.getUTCDate()).padStart(2, "0")}`;
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
        .toLocaleDateString([], { weekday: "short", day: "numeric", month: "short", year: "numeric", timeZone: tz });
}

// ─── Component ──────────────────────────────────────────────────────────────

class TmAttendanceReport extends Component {
    static template = "tuition_management.AttendanceReport";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        const sessionTz = (session.user_context && session.user_context.tz) || "UTC";
        const today = getTodayStrInTz(sessionTz);

        this.state = useState({
            tz: sessionTz,
            viewMode: "today",       // "today" | "week" | "month" | "custom"
            periodStart: today,      // anchor for today/week/month
            dateFrom: today,         // custom range inputs
            dateTo: today,
            rows: [],
            course_id: "",
            tutor_id: "",
            status: "",
            student_name: "",
            courses: [],
            tutors: [],
            courseSearch: "",
            courseDropdownOpen: false,
            tutorSearch: "",
            tutorDropdownOpen: false,
            timezones: [],
            tzSearch: "",
            tzDropdownOpen: false,
            loading: false,
        });

        onWillStart(async () => {
            const [userTz, timezones] = await Promise.all([
                this.orm.call("class.schedule", "get_user_timezone", []),
                this.orm.call("class.schedule", "get_common_timezones", []),
            ]);
            this.state.timezones = timezones;
            this.state.tz = userTz;
            const todayInTz = getTodayStrInTz(userTz);
            this.state.periodStart = todayInTz;
            this.state.dateFrom = todayInTz;
            this.state.dateTo = todayInTz;

            await Promise.all([this.loadFilters(), this.loadRows()]);
        });
    }

    // ── Computed properties ────────────────────────────────────────────────

    get periodLabel() {
        const { dateFrom, dateTo, viewMode } = this.rangeStrs();
        if (viewMode === "today") return this.fmtLabel(dateFrom);
        return `${this.fmtLabel(dateFrom)} — ${this.fmtLabel(dateTo)}`;
    }

    fmtLabel(str) {
        const [y, m, d] = str.split("-").map(Number);
        return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString(undefined, {
            day: "numeric", month: "short", year: "numeric", timeZone: "UTC",
        });
    }

    /** Push the current view mode's resolved range into the Date From/To inputs,
     * so they stay visible and editable — the user can nudge either boundary to
     * combine a quick filter (Today/Week/Month/Previous Month) with a custom
     * range, instead of the inputs silently staying stale. */
    syncDateInputsFromRange() {
        const { dateFrom, dateTo } = this.rangeStrs();
        this.state.dateFrom = dateFrom;
        this.state.dateTo = dateTo;
    }

    /** Resolve the effective from/to date strings for the current view mode. */
    rangeStrs() {
        const { viewMode, periodStart, dateFrom, dateTo, tz } = this.state;
        if (viewMode === "today") return { dateFrom: periodStart, dateTo: periodStart, viewMode };
        if (viewMode === "week") return { dateFrom: periodStart, dateTo: addDays(periodStart, 6), viewMode };
        if (viewMode === "prev_month") return { dateFrom: periodStart, dateTo: monthEndStrInTz(periodStart), viewMode };
        if (viewMode === "month") return { dateFrom: periodStart, dateTo: monthEndStrInTz(periodStart), viewMode };
        return { dateFrom: dateFrom || getTodayStrInTz(tz), dateTo: dateTo || getTodayStrInTz(tz), viewMode };
    }

    get selectedCourseLabel() {
        const found = this.state.courses.find(c => String(c.id) === String(this.state.course_id));
        return found ? found.name : "All Courses";
    }

    get selectedTutorLabel() {
        const found = this.state.tutors.find(t => String(t.id) === String(this.state.tutor_id));
        return found ? found.name : "All Tutors";
    }

    get selectedTzLabel() {
        const found = this.state.timezones.find(t => t[0] === this.state.tz);
        return found ? found[1] : this.state.tz;
    }

    get filteredCourses() {
        const q = this.state.courseSearch.trim().toLowerCase();
        if (!q) return this.state.courses;
        return this.state.courses.filter(c => c.name.toLowerCase().includes(q));
    }

    get filteredTutors() {
        const q = this.state.tutorSearch.trim().toLowerCase();
        if (!q) return this.state.tutors;
        return this.state.tutors.filter(t => t.name.toLowerCase().includes(q));
    }

    get filteredTimezones() {
        const q = this.state.tzSearch.trim().toLowerCase();
        if (!q) return this.state.timezones;
        return this.state.timezones.filter(t => t[1].toLowerCase().includes(q));
    }

    // ── Data loaders ───────────────────────────────────────────────────────

    async loadFilters() {
        const [courses, tutors] = await Promise.all([
            this.orm.searchRead("course.master", [], ["id", "name"], { order: "name asc" }),
            this.orm.searchRead("tutor.profile", [], ["id", "name"], { order: "name asc" }),
        ]);
        this.state.courses = courses;
        this.state.tutors = tutors;
    }

    async loadRows() {
        this.state.loading = true;
        const { tz } = this.state;
        const { dateFrom, dateTo } = this.rangeStrs();

        const startUtcMs = tzMidnightToUtcMs(dateFrom, tz);
        const endUtcMs   = tzMidnightToUtcMs(dateTo, tz) + 24 * 3600 * 1000 - 1000;

        const domain = [
            ["start_datetime", ">=", msToOdooStr(startUtcMs)],
            ["start_datetime", "<=", msToOdooStr(endUtcMs)],
        ];
        if (this.state.course_id) domain.push(["course_id", "=", parseInt(this.state.course_id)]);
        if (this.state.tutor_id) domain.push(["tutor_id", "=", parseInt(this.state.tutor_id)]);
        if (this.state.status) domain.push(["lesson_status", "=", this.state.status]);
        if (this.state.student_name.trim()) {
            domain.push(["course_id.enrollment_ids.student_id.name", "ilike", this.state.student_name.trim()]);
        }

        const rows = await this.orm.searchRead(
            "class.schedule.occurrence",
            domain,
            ["course_id", "tutor_id", "start_datetime", "stop_datetime", "lesson_status",
             "attendance_marked", "attendance_present_count", "attendance_absent_count"],
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
        const mode = ev.currentTarget.dataset.mode;
        this.state.viewMode = mode;
        const { tz } = this.state;
        if (mode === "today") this.state.periodStart = getTodayStrInTz(tz);
        else if (mode === "week") this.state.periodStart = getMondayStrInTz(tz);
        else if (mode === "prev_month") this.state.periodStart = getPrevMonthStartStrInTz(tz);
        else if (mode === "month") this.state.periodStart = getMonthStartStrInTz(tz);
        this.syncDateInputsFromRange();
        await this.loadRows();
    }

    async onDateFromChange(ev) {
        this.state.dateFrom = ev.target.value;
        this.state.viewMode = "custom";
        await this.loadRows();
    }

    async onDateToChange(ev) {
        this.state.dateTo = ev.target.value;
        this.state.viewMode = "custom";
        await this.loadRows();
    }

    onCourseSearchInput(ev) { this.state.courseSearch = ev.target.value; }

    onCourseFocus() {
        this.state.courseSearch = "";
        this.state.courseDropdownOpen = true;
    }

    onCourseBlur() {
        this.state.courseDropdownOpen = false;
        this.state.courseSearch = "";
    }

    async onCourseSelect(ev) {
        ev.preventDefault(); // prevent blur before mousedown completes
        this.state.course_id = ev.currentTarget.dataset.value;
        this.state.courseSearch = "";
        this.state.courseDropdownOpen = false;
        await this.loadRows();
    }

    onTutorSearchInput(ev) { this.state.tutorSearch = ev.target.value; }

    onTutorFocus() {
        this.state.tutorSearch = "";
        this.state.tutorDropdownOpen = true;
    }

    onTutorBlur() {
        this.state.tutorDropdownOpen = false;
        this.state.tutorSearch = "";
    }

    async onTutorSelect(ev) {
        ev.preventDefault(); // prevent blur before mousedown completes
        this.state.tutor_id = ev.currentTarget.dataset.value;
        this.state.tutorSearch = "";
        this.state.tutorDropdownOpen = false;
        await this.loadRows();
    }

    async onStatusChange(ev) {
        this.state.status = ev.target.value;
        await this.loadRows();
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

    /** Re-anchor the current view mode's date(s) in the newly selected timezone,
     * then reload — "Today"/"This Week"/"This Month" must reflect the chosen
     * timezone's calendar, not the timezone that was active when they were set. */
    async onTzSelect(ev) {
        ev.preventDefault(); // prevent blur before mousedown completes
        this.state.tz = ev.currentTarget.dataset.value;
        this.state.tzSearch = "";
        this.state.tzDropdownOpen = false;
        const { tz, viewMode } = this.state;
        if (viewMode === "today") this.state.periodStart = getTodayStrInTz(tz);
        else if (viewMode === "week") this.state.periodStart = getMondayStrInTz(tz);
        else if (viewMode === "prev_month") this.state.periodStart = getPrevMonthStartStrInTz(tz);
        else if (viewMode === "month") this.state.periodStart = getMonthStartStrInTz(tz);
        if (viewMode !== "custom") this.syncDateInputsFromRange();
        await this.loadRows();
    }

    onStudentInput(ev) { this.state.student_name = ev.target.value; }

    async onStudentKeydown(ev) {
        if (ev.key === "Enter") await this.loadRows();
    }

    async searchStudent() { await this.loadRows(); }

    openOccurrence(ev) {
        const id = parseInt(ev.currentTarget.dataset.id);
        // Reuse the standard Attendance Report action so the record opens in its
        // pinned view_attendance_report_form (not the generic occurrence form).
        this.action.doAction("tuition_management.action_attendance_report", {
            resId: id,
            viewType: "form",
        });
    }

    async exportExcel() {
        if (!this.state.rows.length) {
            this.notification.add(_t("No lessons in the current filter to export."), { type: "warning" });
            return;
        }
        const ids = this.state.rows.map(r => r.id);
        const action = await this.orm.call(
            "class.schedule.occurrence",
            "action_export_attendance_excel",
            [ids],
            { tz: this.state.tz }
        );
        await this.action.doAction(action);
    }
}

registry.category("actions").add("tm_attendance_report", TmAttendanceReport);
