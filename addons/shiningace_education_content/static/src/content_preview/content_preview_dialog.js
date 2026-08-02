/** @odoo-module **/
import { Component } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

export class ContentPreviewDialog extends Component {
    static template = "shiningace_education_content.ContentPreviewDialog";
    static components = { Dialog };
    static props = { close: Function, info: Object };
}
