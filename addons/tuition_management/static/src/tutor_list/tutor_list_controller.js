/** @odoo-module **/

import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class TutorListController extends ListController {
    setup() {
        super.setup();
        this.actionService = useService("action");
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
}

TutorListController.template = "tuition_management.TutorListController";

registry.category("views").add("tutor_profile_list", {
    ...listView,
    Controller: TutorListController,
});
