/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import {
    getTodayStrInTz,
    addDays,
    mondayOfDateStr,
    fmtLongDateInTz,
    fmtShortDateInTz,
    fmtTimeInTz,
    fmtDateInTz,
    dayContainsShift,
} from "../utils/tz_utils";
import { AddShiftModal } from "../add_shift_modal/add_shift_modal";

const TIME_RANGE_OPTIONS = [
    { value: "", label: "Any time" },
    { value: "morning", label: "Morning" },
    { value: "evening", label: "Evening" },
    { value: "custom", label: "Custom range" },
];

export class EmployeeShiftDashboard extends Component {
    static template = "employee_shift.Dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.timeRangeOptions = TIME_RANGE_OPTIONS;

        this.myShiftsOnly = !!(this.props.action && this.props.action.context && this.props.action.context.my_shifts_only);

        this.state = useState({
            tz: "UTC",
            tzSearch: "",
            tzDropdownOpen: false,
            timezones: [],

            viewMode: this.myShiftsOnly ? "today" : "weekly",
            periodStart: getTodayStrInTz("UTC"),
            periodLabel: "",

            dailyShifts: [],
            weekGrid: [],
            monthGrid: [],
            currentEmployees: [],
            leaveOverview: [],

            employees: [],
            myEmployeeId: false,

            filterEmployeeId: "",
            filterDate: "",
            filterTimeRange: "",
            filterCustomStart: "",
            filterCustomEnd: "",
            filteredShifts: null,

            loading: true,
        });

        onWillStart(async () => {
            const [userTz, rawTzList, employees] = await Promise.all([
                this.orm.call("employee.shift", "get_user_timezone", []),
                this.orm.call("employee.shift", "get_common_timezones", []),
                this.orm.searchRead("hr.employee", [["requires_shift_management", "=", true]], ["id", "name", "user_id"]),
            ]);

            this.state.timezones = rawTzList.map(([value, label]) => ({ value, label }));
            this.state.tz = userTz;
            this.state.employees = employees;

            const me = employees.find((e) => e.user_id && e.user_id[0] === user.userId);
            this.state.myEmployeeId = me ? me.id : false;

            this.state.periodStart = getTodayStrInTz(userTz);
            await this.loadAll();
        });
    }

    // ── Computed getters ───────────────────────────────────────────────────

    get selectedTzLabel() {
        const found = this.state.timezones.find((t) => t.value === this.state.tz);
        return found ? found.label : this.state.tz;
    }

    get filteredTimezones() {
        const q = this.state.tzSearch.trim().toLowerCase();
        const list = this.state.timezones;
        if (!q) return list;
        return list.filter((t) => t.value.toLowerCase().includes(q) || t.label.toLowerCase().includes(q));
    }

    get filterableEmployees() {
        return this.state.employees;
    }

    // ── Data loaders ───────────────────────────────────────────────────────

    async loadAll() {
        this.state.loading = true;
        try {
            if (this.myShiftsOnly) {
                await this.loadMyShifts();
            } else {
                await Promise.all([
                    this.state.viewMode === "weekly" ? this.loadWeekly() : this.loadDaily(),
                    this.loadLeaveOverview(),
                    this.loadCurrentlyActive(),
                ]);
            }
        } finally {
            this.state.loading = false;
        }
    }

    async loadDaily() {
        const data = await this.orm.call("employee.shift", "get_dashboard_data", ["daily", this.state.periodStart, this.state.tz]);
        this.state.dailyShifts = data.shifts;
        this.state.periodLabel = this._dayLabel(data.date);
    }

    async loadWeekly() {
        const data = await this.orm.call("employee.shift", "get_dashboard_data", ["weekly", this.state.periodStart, this.state.tz]);
        this.state.weekGrid = data.week_grid.map((day) => ({ ...day, label: fmtShortDateInTz(day.date) }));
        this.state.periodLabel = `${fmtShortDateInTz(data.week_grid[0].date)} – ${fmtShortDateInTz(data.week_grid[6].date)}`;
    }

    async loadLeaveOverview() {
        this.state.leaveOverview = await this.orm.call("employee.shift", "get_leave_overview", [this.state.viewMode, this.state.periodStart, this.state.tz, false]);
    }

    async loadCurrentlyActive() {
        this.state.currentEmployees = await this.orm.call("employee.shift", "get_currently_active", []);
    }

    async loadMyShifts() {
        if (!this.state.myEmployeeId) {
            this.state.dailyShifts = [];
            this.state.weekGrid = [];
            this.state.monthGrid = [];
            this.state.periodLabel = "";
            return;
        }
        const tz = this.state.tz;
        let days = [];
        if (this.state.viewMode === "weekly") {
            const monday = mondayOfDateStr(this.state.periodStart);
            days = Array.from({ length: 7 }, (_, i) => addDays(monday, i));
        } else if (this.state.viewMode === "monthly") {
            const [y, m] = this.state.periodStart.split("-").map(Number);
            const first = `${y}-${String(m).padStart(2, "0")}-01`;
            const daysInMonth = new Date(Date.UTC(y, m, 0)).getUTCDate();
            days = Array.from({ length: daysInMonth }, (_, i) => addDays(first, i));
        } else {
            days = [this.state.periodStart];
        }

        const shifts = await this.orm.call("employee.shift", "search_shifts", [{
            employee_id: this.state.myEmployeeId,
            date_from: days[0],
            date_to: days[days.length - 1],
            tz,
        }]);

        const buckets = days.map((day) => ({
            date: day,
            label: fmtShortDateInTz(day),
            shifts: shifts.filter((s) => dayContainsShift(day, s, tz)),
        }));

        if (this.state.viewMode === "weekly") {
            this.state.weekGrid = buckets;
            this.state.periodLabel = `${fmtShortDateInTz(days[0])} – ${fmtShortDateInTz(days[days.length - 1])}`;
        } else if (this.state.viewMode === "monthly") {
            this.state.monthGrid = buckets;
            this.state.periodLabel = fmtLongDateInTz(days[0]).replace(/^\w+, /, "");
        } else {
            this.state.dailyShifts = buckets[0].shifts;
            this.state.periodLabel = this._dayLabel(days[0]);
        }
    }

    _dayLabel(dateStr) {
        const todayStr = getTodayStrInTz(this.state.tz);
        const longLabel = fmtLongDateInTz(dateStr);
        if (dateStr === todayStr) return `Today — ${longLabel}`;
        if (dateStr === addDays(todayStr, -1)) return `Yesterday — ${longLabel}`;
        if (dateStr === addDays(todayStr, 1)) return `Tomorrow — ${longLabel}`;
        return longLabel;
    }

    fmtTime(dt) {
        return fmtTimeInTz(dt, this.state.tz);
    }

    /** True if a shift's start date differs between the viewing tz and its native tz. */
    hasTzMismatch(shift) {
        if (!shift.native_tz || shift.native_tz === this.state.tz) return false;
        return fmtDateInTz(shift.start_datetime, this.state.tz) !== fmtDateInTz(shift.start_datetime, shift.native_tz);
    }

    nativeTimeTooltip(shift) {
        return `Native: ${fmtTimeInTz(shift.start_datetime, shift.native_tz)} (${shift.native_tz})`;
    }

    // ── Timezone handlers ──────────────────────────────────────────────────

    onTzSearchInput(ev) {
        this.state.tzSearch = ev.target.value;
    }

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
        this.state.tz = ev.currentTarget.dataset.value;
        this.state.tzSearch = "";
        this.state.tzDropdownOpen = false;
        await this.loadAll();
        if (this.state.filteredShifts !== null) {
            await this.applyFilters();
        }
    }

    // ── View / period navigation ───────────────────────────────────────────

    async switchViewMode(mode) {
        if (this.state.viewMode === mode) return;
        this.state.viewMode = mode;
        this.state.periodStart = getTodayStrInTz(this.state.tz);
        await this.loadAll();
    }

    async prevPeriod() {
        const step = this.state.viewMode === "weekly" ? 7 : this.state.viewMode === "monthly" ? -1 : -1;
        if (this.state.viewMode === "monthly") {
            const [y, m] = this.state.periodStart.split("-").map(Number);
            const prevMonth = new Date(Date.UTC(y, m - 2, 1));
            this.state.periodStart = `${prevMonth.getUTCFullYear()}-${String(prevMonth.getUTCMonth() + 1).padStart(2, "0")}-01`;
        } else {
            this.state.periodStart = addDays(this.state.periodStart, this.state.viewMode === "weekly" ? -7 : -1);
        }
        await this.loadAll();
    }

    async nextPeriod() {
        if (this.state.viewMode === "monthly") {
            const [y, m] = this.state.periodStart.split("-").map(Number);
            const nextMonth = new Date(Date.UTC(y, m, 1));
            this.state.periodStart = `${nextMonth.getUTCFullYear()}-${String(nextMonth.getUTCMonth() + 1).padStart(2, "0")}-01`;
        } else {
            this.state.periodStart = addDays(this.state.periodStart, this.state.viewMode === "weekly" ? 7 : 1);
        }
        await this.loadAll();
    }

    async goToday() {
        this.state.periodStart = getTodayStrInTz(this.state.tz);
        await this.loadAll();
    }

    // ── Search / filter bar ────────────────────────────────────────────────

    onFilterEmployeeChange(ev) {
        this.state.filterEmployeeId = ev.target.value;
    }

    onFilterDateChange(ev) {
        this.state.filterDate = ev.target.value;
    }

    onFilterTimeRangeChange(ev) {
        this.state.filterTimeRange = ev.target.value;
    }

    onFilterCustomStartChange(ev) {
        this.state.filterCustomStart = ev.target.value;
    }

    onFilterCustomEndChange(ev) {
        this.state.filterCustomEnd = ev.target.value;
    }

    async applyFilters() {
        const domainFilters = { tz: this.state.tz };
        if (this.state.filterEmployeeId) domainFilters.employee_id = parseInt(this.state.filterEmployeeId);
        if (this.state.filterDate) {
            domainFilters.date_from = this.state.filterDate;
            domainFilters.date_to = this.state.filterDate;
        }
        if (this.state.filterTimeRange === "morning" || this.state.filterTimeRange === "evening") {
            domainFilters.time_range = this.state.filterTimeRange;
        } else if (this.state.filterTimeRange === "custom" && this.state.filterCustomStart && this.state.filterCustomEnd) {
            const [sh, sm] = this.state.filterCustomStart.split(":").map(Number);
            const [eh, em] = this.state.filterCustomEnd.split(":").map(Number);
            domainFilters.time_range = { start: sh + sm / 60, end: eh + em / 60 };
        }
        this.state.filteredShifts = await this.orm.call("employee.shift", "search_shifts", [domainFilters]);
    }

    clearFilters() {
        Object.assign(this.state, {
            filterEmployeeId: "",
            filterDate: "",
            filterTimeRange: "",
            filterCustomStart: "",
            filterCustomEnd: "",
            filteredShifts: null,
        });
    }

    // ── Add Shift modal ────────────────────────────────────────────────────

    openAddShiftModal() {
        this.dialog.add(AddShiftModal, {
            employees: this.state.employees,
            tz: this.state.tz,
            onCreated: () => this.onShiftsCreated(),
        });
    }

    async onShiftsCreated() {
        await this.loadAll();
        if (this.state.filteredShifts !== null) {
            await this.applyFilters();
        }
    }

    // ── Amend an existing shift ─────────────────────────────────────────────

    openShift(shift) {
        this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "employee.shift",
                res_id: shift.id,
                views: [[false, "form"]],
                target: "new",
            },
            {
                onClose: () => this.onShiftsCreated(),
            }
        );
    }
}

registry.category("actions").add("employee_shift_dashboard", EmployeeShiftDashboard);
