/** @odoo-module **/

import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { onWillStart, useState } from "@odoo/owl";

export class ParentListController extends ListController {
    setup() {
        super.setup();
        this.orm = useService("orm");

        this.parentFilters = useState({
            name: "",
            studentName: "",
            status: "",
            tz: "",
            tzSearch: "",
            tzDropdownOpen: false,
            timezones: [],
        });

        onWillStart(async () => {
            this.parentFilters.timezones = await this.orm.call("class.schedule", "get_common_timezones", []);
        });
    }

    /** Build the domain from the custom filter bar and reload the list —
     * this replaces the model's domain outright rather than layering onto
     * the built-in search bar, since these custom fields are meant to be
     * used instead of the standard search-view facets. */
    async applyParentFilters() {
        const f = this.parentFilters;
        const domain = [];
        if (f.name.trim()) domain.push(["name", "ilike", f.name.trim()]);
        if (f.studentName.trim()) domain.push(["student_ids.name", "ilike", f.studentName.trim()]);
        if (f.status) domain.push(["status", "=", f.status]);
        if (f.tz) domain.push(["timezone", "=", f.tz]);
        await this.model.load({ domain: [...(this.props.domain || []), ...domain] });
    }

    get selectedTzLabel() {
        const found = this.parentFilters.timezones.find(t => t[0] === this.parentFilters.tz);
        return found ? found[1] : "All Timezones";
    }

    get filteredTimezones() {
        const q = this.parentFilters.tzSearch.trim().toLowerCase();
        if (!q) return this.parentFilters.timezones;
        return this.parentFilters.timezones.filter(t => t[1].toLowerCase().includes(q));
    }

    onParentNameInput(ev) {
        this.parentFilters.name = ev.target.value;
    }

    async onParentNameKeydown(ev) {
        if (ev.key === "Enter") await this.applyParentFilters();
    }

    onParentStudentNameInput(ev) {
        this.parentFilters.studentName = ev.target.value;
    }

    async onParentStudentNameKeydown(ev) {
        if (ev.key === "Enter") await this.applyParentFilters();
    }

    async onParentStatusChange(ev) {
        this.parentFilters.status = ev.target.value;
        await this.applyParentFilters();
    }

    onTzSearchInput(ev) { this.parentFilters.tzSearch = ev.target.value; }

    onTzFocus() {
        this.parentFilters.tzSearch = "";
        this.parentFilters.tzDropdownOpen = true;
    }

    onTzBlur() {
        this.parentFilters.tzDropdownOpen = false;
        this.parentFilters.tzSearch = "";
    }

    async onTzSelect(ev) {
        ev.preventDefault(); // prevent blur before mousedown completes
        this.parentFilters.tz = ev.currentTarget.dataset.value;
        this.parentFilters.tzSearch = "";
        this.parentFilters.tzDropdownOpen = false;
        await this.applyParentFilters();
    }

    async clearParentFilters() {
        Object.assign(this.parentFilters, {
            name: "", studentName: "", status: "", tz: "", tzSearch: "", tzDropdownOpen: false,
        });
        await this.applyParentFilters();
    }
}

ParentListController.template = "tuition_management.ParentListController";

registry.category("views").add("parent_profile_list", {
    ...listView,
    Controller: ParentListController,
});
