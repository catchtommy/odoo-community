/** @odoo-module **/

import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

// ── Base mixin ────────────────────────────────────────────────────────────────
function makeImportController(wizardModel, windowTitle, templateName) {
    class ImportListController extends ListController {
        setup() {
            super.setup();
            this.actionService = useService("action");
        }
        openImportExport() {
            this.actionService.doAction({
                type: "ir.actions.act_window",
                name: windowTitle,
                res_model: wizardModel,
                views: [[false, "form"]],
                target: "new",
            });
        }
    }
    ImportListController.template = templateName;
    return ImportListController;
}

// ── Subject Category list ──────────────────────────────────────────────────────
const SubjectCategoryListController = makeImportController(
    "subject.category.import.wizard",
    "Subject Category Import / Export",
    "tuition_management.SubjectCategoryListController"
);
registry.category("views").add("subject_category_list", {
    ...listView,
    Controller: SubjectCategoryListController,
});

// ── Subject list ───────────────────────────────────────────────────────────────
const SubjectListController = makeImportController(
    "subject.import.wizard",
    "Subject Import / Export",
    "tuition_management.SubjectListController"
);
registry.category("views").add("subject_master_list", {
    ...listView,
    Controller: SubjectListController,
});

// ── Grade list ─────────────────────────────────────────────────────────────────
const GradeListController = makeImportController(
    "grade.import.wizard",
    "Grade Import / Export",
    "tuition_management.GradeListController"
);
registry.category("views").add("grade_master_list", {
    ...listView,
    Controller: GradeListController,
});
