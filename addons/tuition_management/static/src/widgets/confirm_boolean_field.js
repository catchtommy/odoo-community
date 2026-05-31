/** @odoo-module **/

import { registry } from "@web/core/registry";
import { BooleanField, booleanField } from "@web/views/fields/boolean/boolean_field";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

/**
 * ConfirmBooleanField
 *
 * A checkbox field that shows a confirmation dialog before the value is set
 * to `true`.  Unchecking (setting back to false) proceeds without a prompt.
 *
 * Register with:  widget="confirm_boolean"
 * Customise the dialog via optional field options:
 *   options="{'confirm_title': '...', 'confirm_body': '...', 'confirm_label': '...', 'cancel_label': '...'}"
 */
export class ConfirmBooleanField extends BooleanField {
    setup() {
        super.setup();
        this.dialogService = useService("dialog");
    }

    /**
     * Intercept the checkbox change.
     * - Unchecking: pass through immediately.
     * - Checking:   show a ConfirmationDialog first.
     */
    onChange(newValue) {
        if (!newValue) {
            // Clearing the flag needs no confirmation
            this.props.record.update({ [this.props.name]: newValue });
            return;
        }

        const opts = this.props.options || {};
        const title   = opts.confirm_title  || "Warning";
        const body    = opts.confirm_body   ||
            "This lesson will be excluded from tutor payroll calculations " +
            "and will not appear in any payroll run. Do you want to continue?";
        const confirmLabel = opts.confirm_label || "Yes, Exclude";
        const cancelLabel  = opts.cancel_label  || "No";

        // Set to true immediately so the record matches the DOM state the
        // browser has already applied. This gives cancel a real value
        // transition (true → false) that forces OWL to re-render the checkbox
        // back to unchecked when the user dismisses the dialog.
        this.props.record.update({ [this.props.name]: true });

        this.dialogService.add(ConfirmationDialog, {
            title,
            body,
            confirmLabel,
            cancelLabel,
            confirm: () => {
                // Value is already true — nothing more to do.
            },
            // Explicit cancel callback: revert true → false so OWL patches
            // the DOM checkbox back to unchecked.
            cancel: () => {
                this.props.record.update({ [this.props.name]: false });
            },
        });
    }
}

// Reuse the standard BooleanField template — no custom XML needed.
ConfirmBooleanField.template = "web.BooleanField";

export const confirmBooleanField = {
    ...booleanField,
    component: ConfirmBooleanField,
    displayName: "Confirm Boolean",
};

registry.category("fields").add("confirm_boolean", confirmBooleanField);
