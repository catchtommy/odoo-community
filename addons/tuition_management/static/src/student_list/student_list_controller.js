/** @odoo-module **/

import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { onWillStart, useState } from "@odoo/owl";

export class StudentListController extends ListController {
    setup() {
        super.setup();
        this.orm = useService("orm");

        this.studentFilters = useState({
            name: "",
            parentName: "",
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
            this.studentFilters.subjects = subjects;
            this.studentFilters.categories = categories;
            this.studentFilters.grades = grades;
        });
    }

    /** Build the domain from the custom filter bar and reload the list —
     * this replaces the model's domain outright rather than layering onto
     * the built-in search bar, since these custom fields are meant to be
     * used instead of the standard search-view facets. */
    async applyStudentFilters() {
        const f = this.studentFilters;
        const domain = [];
        if (f.name.trim()) domain.push(["name", "ilike", f.name.trim()]);
        if (f.parentName.trim()) domain.push(["parent_id.name", "ilike", f.parentName.trim()]);
        if (f.status) domain.push(["status", "=", f.status]);
        if (f.categoryId) domain.push(["subjects_ids.category_id", "in", [parseInt(f.categoryId)]]);
        if (f.subjectId) domain.push(["subjects_ids", "in", [parseInt(f.subjectId)]]);
        if (f.gradeId) domain.push(["grade_id", "=", parseInt(f.gradeId)]);
        await this.model.load({ domain: [...(this.props.domain || []), ...domain] });
    }

    onStudentNameInput(ev) {
        this.studentFilters.name = ev.target.value;
    }

    async onStudentNameKeydown(ev) {
        if (ev.key === "Enter") await this.applyStudentFilters();
    }

    onStudentParentNameInput(ev) {
        this.studentFilters.parentName = ev.target.value;
    }

    async onStudentParentNameKeydown(ev) {
        if (ev.key === "Enter") await this.applyStudentFilters();
    }

    async onStudentStatusChange(ev) {
        this.studentFilters.status = ev.target.value;
        await this.applyStudentFilters();
    }

    async onStudentCategoryChange(ev) {
        this.studentFilters.categoryId = ev.target.value;
        await this.applyStudentFilters();
    }

    async onStudentSubjectChange(ev) {
        this.studentFilters.subjectId = ev.target.value;
        await this.applyStudentFilters();
    }

    async onStudentGradeChange(ev) {
        this.studentFilters.gradeId = ev.target.value;
        await this.applyStudentFilters();
    }

    async clearStudentFilters() {
        Object.assign(this.studentFilters, {
            name: "", parentName: "", status: "", subjectId: "", categoryId: "", gradeId: "",
        });
        await this.applyStudentFilters();
    }
}

StudentListController.template = "tuition_management.StudentListController";

registry.category("views").add("student_profile_list", {
    ...listView,
    Controller: StudentListController,
});
