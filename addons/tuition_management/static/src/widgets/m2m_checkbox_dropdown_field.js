/** @odoo-module **/

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { Dropdown } from "@web/core/dropdown/dropdown";
import {
    Many2ManyCheckboxesField,
    many2ManyCheckboxesField,
} from "@web/views/fields/many2many_checkboxes/many2many_checkboxes_field";

/**
 * many2many_checkboxes rendered as a dropdown of checkboxes, for report filters
 * with a few options: <field name="x_ids" widget="tm_m2m_checkbox_dropdown"/>.
 * Nothing ticked is shown as "All".
 */
export class M2MCheckboxDropdownField extends Many2ManyCheckboxesField {
    static template = "tuition_management.M2MCheckboxDropdownField";
    static components = { ...Many2ManyCheckboxesField.components, Dropdown };

    get toggleLabel() {
        const selected = (this.items || []).filter((item) => this.isSelected(item));
        if (!selected.length || selected.length === this.items.length) {
            return _t("All");
        }
        return selected.map((item) => item[1]).join(", ");
    }

    /** Apply each tick immediately (no debounce) so the checkmark and label update at once. */
    onToggle(item) {
        const list = this.props.record.data[this.props.name];
        if (this.isSelected(item)) {
            list.addAndRemove({ remove: [item[0]] });
        } else {
            list.addAndRemove({ add: [item[0]] });
        }
    }
}

registry.category("fields").add("tm_m2m_checkbox_dropdown", {
    ...many2ManyCheckboxesField,
    component: M2MCheckboxDropdownField,
    displayName: _t("Checkbox Dropdown"),
});
