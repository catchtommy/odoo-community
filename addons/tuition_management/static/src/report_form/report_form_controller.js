/** @odoo-module **/
import { formView } from "@web/views/form/form_view";
import { FormController } from "@web/views/form/form_controller";
import { registry } from "@web/core/registry";
import { useSubEnv } from "@odoo/owl";

/**
 * The report wizards (Class Status, Subject-wise, Tutor-wise, Pricing) are
 * always opened as a single, pre-created record — there is never a second
 * record to page through, so the "1/1" pager in the control panel is dead
 * chrome. Shadow it out after the base FormController registers it.
 */
class ReportFormController extends FormController {
    setup() {
        super.setup();
        useSubEnv({ config: { ...this.env.config, pagerProps: { total: 0 } } });
    }
}

registry.category("views").add("tm_report_form", {
    ...formView,
    Controller: ReportFormController,
});
