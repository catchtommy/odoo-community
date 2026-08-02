/** @odoo-module **/
import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { ContentPreviewDialog } from "./content_preview_dialog";
import { getPreviewInfo } from "./content_preview_utils";

export class ContentPreviewButton extends Component {
    static template = "shiningace_education_content.ContentPreviewButton";
    static props = { ...standardFieldProps };

    setup() {
        this.dialogService = useService("dialog");
    }

    get info() {
        return getPreviewInfo(this.props.record);
    }

    openPreview() {
        const info = this.info;
        if (!info.available) {
            return;
        }
        this.dialogService.add(ContentPreviewDialog, { info });
    }
}

export const contentPreviewButton = {
    component: ContentPreviewButton,
};

registry.category("fields").add("content_preview_button", contentPreviewButton);
