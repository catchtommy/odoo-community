/** @odoo-module **/
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/**
 * Clicking a row in the Curricula list opens the Curriculum Structure Tree
 * (see static/src/curriculum_tree) instead of the classic form — the tree is
 * the primary way to work with a curriculum day to day. The classic form is
 * still reachable from inside the tree via its "Edit Details" link.
 */
export class EducationCurriculumListController extends ListController {
    setup() {
        super.setup();
        this.actionService = useService("action");
    }

    async openRecord(record) {
        await this.actionService.doAction({
            type: "ir.actions.client",
            tag: "education_curriculum_tree",
            name: record.data.name,
            // `active_id` (not a custom key) so the browser back button works —
            // see education.curriculum.action_view_structure_tree() for why.
            context: { active_id: record.resId },
        });
    }
}

registry.category("views").add("education_curriculum_list", {
    ...listView,
    Controller: EducationCurriculumListController,
});
