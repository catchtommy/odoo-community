/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

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
            schedule_date: new Date(),
            schedule_label: "",
            schedule_rows: [],
        });
        onWillStart(async () => {
            await this.loadData();
            await this.loadSchedule();
        });
    }

    _formatDate(d) {
        const yyyy = d.getFullYear();
        const mm = String(d.getMonth() + 1).padStart(2, "0");
        const dd = String(d.getDate()).padStart(2, "0");
        return `${yyyy}-${mm}-${dd}`;
    }

    _formatLabel(d) {
        const today = new Date();
        const todayStr = this._formatDate(today);
        const dStr = this._formatDate(d);
        const opts = { weekday: "long", year: "numeric", month: "long", day: "numeric" };
        const label = d.toLocaleDateString(undefined, opts);
        if (dStr === todayStr) return `Today — ${label}`;
        const yesterday = new Date(today);
        yesterday.setDate(yesterday.getDate() - 1);
        if (dStr === this._formatDate(yesterday)) return `Yesterday — ${label}`;
        const tomorrow = new Date(today);
        tomorrow.setDate(tomorrow.getDate() + 1);
        if (dStr === this._formatDate(tomorrow)) return `Tomorrow — ${label}`;
        return label;
    }

    async loadData() {
        const [courses, activeCourses, enrollments, activeEnrollments,
               enquiries, newEnquiries, demoSessions, students, tutors] = await Promise.all([
            this.orm.searchCount("course.master", []),
            this.orm.searchCount("course.master", [["status", "=", "active"]]),
            this.orm.searchCount("course.enrollment", []),
            this.orm.searchCount("course.enrollment", [["status", "=", "active"]]),
            this.orm.searchCount("enquiry", []),
            this.orm.searchCount("enquiry", [["is_enrolled", "=", false]]),
            this.orm.searchCount("demo.session", []),
            this.orm.searchCount("student.profile", []),
            this.orm.searchCount("tutor.profile", []),
        ]);

        const upcomingDemos = await this.orm.searchCount("demo.session", [["status", "=", "scheduled"]]);

        Object.assign(this.state, {
            courses, active_courses: activeCourses,
            enrollments, active_enrollments: activeEnrollments,
            enquiries, new_enquiries: newEnquiries,
            demo_sessions: demoSessions, upcoming_demos: upcomingDemos,
            students, tutors,
        });
    }

    async loadSchedule() {
        const d = this.state.schedule_date;
        const dateStr = this._formatDate(d);
        const startStr = `${dateStr} 00:00:00`;
        const endStr = `${dateStr} 23:59:59`;
        this.state.schedule_label = this._formatLabel(d);

        const rows = await this.orm.searchRead(
            "class.schedule.occurrence",
            [["start_datetime", ">=", startStr], ["start_datetime", "<=", endStr]],
            ["name", "course_id", "tutor_id", "start_datetime", "stop_datetime", "lesson_status", "attendance_marked"],
            { order: "start_datetime asc" }
        );
        // Format times
        for (const row of rows) {
            const start = new Date(row.start_datetime);
            const stop = new Date(row.stop_datetime);
            row.start_time = start.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
            row.stop_time = stop.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
            row.course_name = row.course_id ? row.course_id[1] : "";
            row.tutor_name = row.tutor_id ? row.tutor_id[1] : "";
        }
        this.state.schedule_rows = rows;
        this.state.today_schedules = rows.length;
    }

    async prevDay() {
        const d = new Date(this.state.schedule_date);
        d.setDate(d.getDate() - 1);
        this.state.schedule_date = d;
        await this.loadSchedule();
    }

    async nextDay() {
        const d = new Date(this.state.schedule_date);
        d.setDate(d.getDate() + 1);
        this.state.schedule_date = d;
        await this.loadSchedule();
    }

    async goToday() {
        this.state.schedule_date = new Date();
        await this.loadSchedule();
    }

    openOccurrence(ev) {
        const id = parseInt(ev.currentTarget.dataset.id);
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "class.schedule.occurrence",
            res_id: id,
            views: [[false, "form"]],
        });
    }

    viewCourses() {
        this.action.doAction("tuition_management.action_course_masters");
    }
    viewEnrollments() {
        this.action.doAction("tuition_management.action_course_enrollments");
    }
    viewEnquiries() {
        this.action.doAction("tuition_management.action_enquiry");
    }
    viewDemoSessions() {
        this.action.doAction("tuition_management.action_demo_sessions");
    }
    viewTodaySchedules() {
        const d = this.state.schedule_date;
        const dateStr = this._formatDate(d);
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Schedule",
            res_model: "class.schedule.occurrence",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
            domain: [["start_datetime", ">=", `${dateStr} 00:00:00`], ["start_datetime", "<=", `${dateStr} 23:59:59`]],
        });
    }
    viewCalendar() {
        this.action.doAction("tuition_management.action_class_schedule_calendar");
    }
    viewStudents() {
        this.action.doAction("tuition_management.action_student_profiles");
    }
    viewTutors() {
        this.action.doAction("tuition_management.action_tutor_profiles");
    }
}

registry.category("actions").add("tuition_dashboard", TuitionDashboard);
