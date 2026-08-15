/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { formatInteger } from "@web/views/fields/formatters";

/**
 * DrilldownStatField
 *
 * Read-only integer display for report list rows. Clicking the number
 * itself calls the given object method (an `action_view_*`-style method
 * on the row's own record) and opens the resulting action — merging what
 * used to be a separate "Details" button into the stat value, and without
 * falling back to the generic "open form" popup.
 *
 * Register with:  widget="tm_drilldown_stat"
 * Required option: options="{'action': 'action_view_scheduled'}"
 */
export class DrilldownStatField extends Component {
    static template = "tuition_management.DrilldownStatField";
    static props = {
        ...standardFieldProps,
        action: { type: String, optional: true },
    };

    setup() {
        this.actionService = useService("action");
    }

    get formattedValue() {
        return formatInteger(this.props.record.data[this.props.name]);
    }

    async onClick() {
        if (!this.props.action) {
            return;
        }
        // Route through doActionButton (the same path a normal <button type="object">
        // click uses) so the returned action dict (e.g. `view_mode` without an
        // explicit `views` list) gets properly normalized before opening.
        await this.actionService.doActionButton({
            type: "object",
            name: this.props.action,
            resModel: this.props.record.resModel,
            resId: this.props.record.resId,
        });
    }
}

registry.category("fields").add("tm_drilldown_stat", {
    component: DrilldownStatField,
    supportedTypes: ["integer"],
    extractProps: ({ options }) => ({
        action: options.action,
    }),
});
