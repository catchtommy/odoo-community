/** @odoo-module **/

import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { onWillStart, useState } from "@odoo/owl";

export class TutorListController extends ListController {
    setup() {
        super.setup();
        this.actionService = useService("action");
        this.orm = useService("orm");

        this.tutorFilters = useState({
            name: "",
            employmentType: "",
            status: "",
            subjectId: "",
            categoryId: "",
            gradeId: "",
            subjects: [],
            categories: [],
            grades: [],
        });

        onWillStart(async () => {
            const [subjects, categories, grades] = await Promise.all([
                this.orm.searchRead("subject.master", [], ["id", "name"], { order: "name asc" }),
                this.orm.searchRead("subject.category", [], ["id", "name"], { order: "name asc" }),
                this.orm.searchRead("grade.master", [], ["id", "name"], { order: "name asc" }),
            ]);
            this.tutorFilters.subjects = subjects;
            this.tutorFilters.categories = categories;
            this.tutorFilters.grades = grades;
        });
    }

    openImportExport() {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            name: "Tutor Import / Export",
            res_model: "tutor.import.wizard",
            views: [[false, "form"]],
            target: "new",
        });
    }

    /** Build the domain from the custom filter bar and reload the list —
     * this replaces the model's domain outright rather than layering onto
     * the built-in search bar, since these custom fields are meant to be
     * used instead of the standard search-view facets. */
    async applyTutorFilters() {
        const f = this.tutorFilters;
        const domain = [];
        if (f.name.trim()) domain.push(["name", "ilike", f.name.trim()]);
        if (f.employmentType) domain.push(["employment_type", "=", f.employmentType]);
        if (f.status) domain.push(["status", "=", f.status]);
        if (f.categoryId) domain.push(["category_ids", "in", [parseInt(f.categoryId)]]);
        if (f.subjectId) domain.push(["subject_ids", "in", [parseInt(f.subjectId)]]);
        if (f.gradeId) domain.push(["grade_ids", "in", [parseInt(f.gradeId)]]);
        await this.model.load({ domain: [...(this.props.domain || []), ...domain] });
    }

    onTutorNameInput(ev) {
        this.tutorFilters.name = ev.target.value;
    }

    async onTutorNameKeydown(ev) {
        if (ev.key === "Enter") await this.applyTutorFilters();
    }

    async onTutorEmploymentChange(ev) {
        this.tutorFilters.employmentType = ev.target.value;
        await this.applyTutorFilters();
    }

    async onTutorStatusChange(ev) {
        this.tutorFilters.status = ev.target.value;
        await this.applyTutorFilters();
    }

    async onTutorCategoryChange(ev) {
        this.tutorFilters.categoryId = ev.target.value;
        await this.applyTutorFilters();
    }

    async onTutorSubjectChange(ev) {
        this.tutorFilters.subjectId = ev.target.value;
        await this.applyTutorFilters();
    }

    async onTutorGradeChange(ev) {
        this.tutorFilters.gradeId = ev.target.value;
        await this.applyTutorFilters();
    }

    async clearTutorFilters() {
        Object.assign(this.tutorFilters, {
            name: "", employmentType: "", status: "", subjectId: "", categoryId: "", gradeId: "",
        });
        await this.applyTutorFilters();
    }
}

TutorListController.template = "tuition_management.TutorListController";

registry.category("views").add("tutor_profile_list", {
    ...listView,
    Controller: TutorListController,
});
