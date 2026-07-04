/** @odoo-module **/
import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/core/dialog/dialog";
import { getTodayStrInTz, addDays } from "../utils/tz_utils";

export class AddShiftModal extends Component {
    static template = "employee_shift.AddShiftModal";
    static components = { Dialog };
    static props = {
        employees: { type: Array },
        tz: { type: String },
        close: { type: Function },
        onCreated: { type: Function },
    };

    setup() {
        this.orm = useService("orm");
        const today = getTodayStrInTz(this.props.tz);
        this.state = useState({
            templates: [],
            templateId: "",
            employeeIds: [],
            dateFrom: today,
            dateTo: today,
            error: "",
            saving: false,
        });

        onWillStart(async () => {
            this.state.templates = await this.orm.searchRead(
                "shift.template",
                [],
                ["id", "name", "start_time", "end_time", "base_tz"]
            );
        });
    }

    get selectedTemplate() {
        return this.state.templates.find((t) => t.id === parseInt(this.state.templateId));
    }

    onTemplateChange(ev) {
        this.state.templateId = ev.target.value;
    }

    onEmployeesChange(ev) {
        this.state.employeeIds = Array.from(ev.target.selectedOptions).map((o) => parseInt(o.value));
    }

    onDateFromChange(ev) {
        this.state.dateFrom = ev.target.value;
        if (this.state.dateTo && this.state.dateTo < this.state.dateFrom) {
            this.state.dateTo = this.state.dateFrom;
        }
    }

    onDateToChange(ev) {
        this.state.dateTo = ev.target.value;
    }

    /** All calendar dates from dateFrom to dateTo, inclusive. */
    get dateRange() {
        const dates = [];
        if (!this.state.dateFrom || !this.state.dateTo || this.state.dateTo < this.state.dateFrom) {
            return dates;
        }
        let cursor = this.state.dateFrom;
        while (cursor <= this.state.dateTo) {
            dates.push(cursor);
            cursor = addDays(cursor, 1);
        }
        return dates;
    }

    async confirm() {
        this.state.error = "";
        const dates = this.dateRange;
        if (!this.state.templateId) {
            this.state.error = "Select a shift template.";
            return;
        }
        if (!this.state.employeeIds.length) {
            this.state.error = "Select at least one employee.";
            return;
        }
        if (!dates.length) {
            this.state.error = "Date To must be on or after Date From.";
            return;
        }

        this.state.saving = true;
        try {
            await this.orm.call("employee.shift", "create_from_template", [
                parseInt(this.state.templateId),
                this.state.employeeIds,
                dates,
            ]);
            this.props.onCreated();
            this.props.close();
        } catch (e) {
            this.state.error = (e && e.data && e.data.message) || "Could not create the shift(s).";
        } finally {
            this.state.saving = false;
        }
    }

    discard() {
        this.props.close();
    }
}
