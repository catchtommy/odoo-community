/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

// ─── Date / timezone helpers (mirrors schedule_viewer.js) ───────────────────

function getTodayStrInTz(tz) {
    return new Intl.DateTimeFormat("en-CA", { timeZone: tz }).format(new Date());
}

function addDays(dateStr, days) {
    const [y, m, d] = dateStr.split("-").map(Number);
    return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10);
}

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

// ─── Component ──────────────────────────────────────────────────────────────

class TuitionDashboard extends Component {
    static template = "tuition_management.Dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            courses: 0,
            active_courses: 0,
            enrollments: 0,
            active_enrollments: 0,
            enquiries: 0,
            new_enquiries: 0,
            demo_sessions: 0,
            upcoming_demos: 0,
            today_schedules: 0,
            students: 0,
            tutors: 0,
            // Timezone state
            tz: "UTC",
            tzSearch: "",
            tzDropdownOpen: false,
            timezones: [],
            // Schedule navigation
            schedule_date_str: getTodayStrInTz("UTC"), // YYYY-MM-DD; updated after tz fetch
            schedule_label: "",
            schedule_rows: [],
        });

        onWillStart(async () => {
            const [userTz, rawTzList] = await Promise.all([
                this.orm.call("class.schedule", "get_user_timezone", []),
                this.orm.call("class.schedule", "get_common_timezones", []),
            ]);

            this.state.timezones = rawTzList.map(([value, label]) => ({ value, label }));
            this.state.tz = userTz;
            this.state.schedule_date_str = getTodayStrInTz(userTz);

            await Promise.all([this.loadData(), this.loadSchedule()]);
        });
    }

    // ── Computed getters ───────────────────────────────────────────────────

    get selectedTzLabel() {
        const found = this.state.timezones.find(t => t.value === this.state.tz);
        return found ? found.label : this.state.tz;
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

    async loadData() {
        const [courses, activeCourses, enrollments, activeEnrollments,
               enquiries, newEnquiries, demoSessions, students, tutors,
               upcomingDemos] = await Promise.all([
            this.orm.searchCount("course.master", []),
            this.orm.searchCount("course.master", [["status", "=", "active"]]),
            this.orm.searchCount("course.enrollment", []),
            this.orm.searchCount("course.enrollment", [["status", "=", "active"]]),
            this.orm.searchCount("enquiry", []),
            this.orm.searchCount("enquiry", [["is_enrolled", "=", false]]),
            this.orm.searchCount("demo.session", []),
            this.orm.searchCount("student.profile", []),
            this.orm.searchCount("tutor.profile", []),
            this.orm.searchCount("demo.session", [["status", "=", "scheduled"]]),
        ]);

        Object.assign(this.state, {
            courses, active_courses: activeCourses,
            enrollments, active_enrollments: activeEnrollments,
            enquiries, new_enquiries: newEnquiries,
            demo_sessions: demoSessions, upcoming_demos: upcomingDemos,
            students, tutors,
        });
    }

    async loadSchedule() {
        const { schedule_date_str: dateStr, tz } = this.state;

        // Compute exact UTC milliseconds for midnight–end-of-day in the selected timezone
        const startUtcMs = tzMidnightToUtcMs(dateStr, tz);
        const endUtcMs   = startUtcMs + 24 * 3600 * 1000 - 1000;

        // Build a readable date label
        const [y, m, d] = dateStr.split("-").map(Number);
        const dt = new Date(Date.UTC(y, m - 1, d));
        const todayStr   = getTodayStrInTz(tz);
        const longLabel  = dt.toLocaleDateString(undefined, {
            weekday: "long", year: "numeric", month: "long", day: "numeric", timeZone: "UTC",
        });
        let label = longLabel;
        if (dateStr === todayStr)          label = `Today — ${longLabel}`;
        else if (dateStr === addDays(todayStr, -1)) label = `Yesterday — ${longLabel}`;
        else if (dateStr === addDays(todayStr,  1)) label = `Tomorrow — ${longLabel}`;
        this.state.schedule_label = label;

        const rows = await this.orm.searchRead(
            "class.schedule.occurrence",
            [["start_datetime", ">=", msToOdooStr(startUtcMs)],
             ["start_datetime", "<=", msToOdooStr(endUtcMs)]],
            ["name", "course_id", "tutor_id", "start_datetime", "stop_datetime", "lesson_status", "attendance_marked"],
            { order: "start_datetime asc" }
        );

        for (const row of rows) {
            const start = new Date(row.start_datetime.replace(" ", "T") + "Z");
            const stop  = new Date(row.stop_datetime.replace(" ", "T") + "Z");
            row.start_time = start.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", timeZone: tz });
            row.stop_time  = stop.toLocaleTimeString([],  { hour: "2-digit", minute: "2-digit", timeZone: tz });
            row.course_name = row.course_id ? row.course_id[1] : "";
            row.tutor_name  = row.tutor_id  ? row.tutor_id[1]  : "";
            // `name` bakes in the date the occurrence was generated on (not tz-aware),
            // which reads as the wrong date once converted to the viewer's timezone —
            // show the course name instead, keeping any "(Rescheduled)" suffix.
            row.lesson_label = row.course_name + (row.name && row.name.includes("(Rescheduled)") ? " (Rescheduled)" : "");
        }
        this.state.schedule_rows   = rows;
        this.state.today_schedules = rows.length;
    }

    // ── Timezone handlers ──────────────────────────────────────────────────

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
        ev.preventDefault();
        const newTz = ev.currentTarget.dataset.value;
        this.state.tz = newTz;
        this.state.tzSearch = "";
        this.state.tzDropdownOpen = false;
        this.state.schedule_date_str = getTodayStrInTz(newTz);
        await this.loadSchedule();
    }

    // ── Day navigation ─────────────────────────────────────────────────────

    async prevDay() {
        this.state.schedule_date_str = addDays(this.state.schedule_date_str, -1);
        await this.loadSchedule();
    }

    async nextDay() {
        this.state.schedule_date_str = addDays(this.state.schedule_date_str, 1);
        await this.loadSchedule();
    }

    async goToday() {
        this.state.schedule_date_str = getTodayStrInTz(this.state.tz);
        await this.loadSchedule();
    }

    // ── Navigation actions ─────────────────────────────────────────────────

    openOccurrence(ev) {
        const id = parseInt(ev.currentTarget.dataset.id);
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "class.schedule.occurrence",
            res_id: id,
            views: [[false, "form"]],
        });
    }

    viewCourses()       { this.action.doAction("tuition_management.action_course_masters"); }
    viewEnrollments()   { this.action.doAction("tuition_management.action_course_enrollments"); }
    viewEnquiries()     { this.action.doAction("tuition_management.action_enquiry"); }
    viewDemoSessions()  { this.action.doAction("tuition_management.action_demo_sessions"); }
    viewStudents()      { this.action.doAction("tuition_management.action_student_profiles"); }
    viewTutors()        { this.action.doAction("tuition_management.action_tutor_profiles"); }

    viewTodaySchedules() {
        const { schedule_date_str: dateStr, tz } = this.state;
        const startUtcMs = tzMidnightToUtcMs(dateStr, tz);
        const endUtcMs   = startUtcMs + 24 * 3600 * 1000 - 1000;
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Schedule",
            res_model: "class.schedule.occurrence",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
            domain: [
                ["start_datetime", ">=", msToOdooStr(startUtcMs)],
                ["start_datetime", "<=", msToOdooStr(endUtcMs)],
            ],
        });
    }

    viewCalendar() { this.action.doAction("tuition_management.action_schedule_viewer"); }
}

registry.category("actions").add("tuition_dashboard", TuitionDashboard);
