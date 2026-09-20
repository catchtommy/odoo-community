/** @odoo-module **/
import { registry } from "@web/core/registry";
import { TextField, textField } from "@web/views/fields/text/text_field";
import { onMounted, onPatched, useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { renderMathJax } from "../js/math_typeset";
import { EquationEditorDialog } from "./equation_editor_dialog";
// Registers the <math-field> custom element used by EquationEditorDialog.
import "../js/mathlive_loader";

/**
 * Same as the standard Text/Html field widget, but shows a MathJax-typeset
 * preview of the value (re-typeset after every mount/patch) — so a
 * curriculum description, lesson body, or lesson-plan field containing
 * LaTeX delimiters ($x^2$, \(x^2\), $$...$$) renders as real math instead
 * of literal "$x^2$" text.
 *
 * The preview shows whenever the record is writable, not only when
 * props.readonly is true: this build has no separate view/edit mode — a
 * record the user can write to is basically always "editable" (no Edit
 * button to click first), so relying on props.readonly alone meant the
 * typeset version almost never actually rendered. The base widget's plain
 * textarea is kept as-is for editing the raw source; the preview appears
 * underneath it.
 *
 * Used via widget="edu_math_text" on any Text or Html field that curriculum
 * authors might write equations into (see education_*_views.xml).
 */
export class EducationMathTextField extends TextField {
    static template = "shiningace_education_core.EducationMathTextField";

    setup() {
        super.setup();
        this.mathRoot = useRef("mathRoot");
        this.dialogService = useService("dialog");
        onMounted(() => renderMathJax(this.mathRoot.el));
        onPatched(() => renderMathJax(this.mathRoot.el));
    }

    get isHtml() {
        return this.props.record.fields[this.props.name].type === "html";
    }

    /**
     * Opens the visual equation builder (see equation_editor_dialog.js) and,
     * on "Insert", splices the resulting LaTeX — wrapped in $...$ so MathJax
     * picks it up — into the field at the current cursor position (or at
     * the end, if the textarea isn't focused/available). Lets curriculum
     * authors add correct LaTeX without knowing the syntax themselves.
     */
    openEquationEditor() {
        this.dialogService.add(EquationEditorDialog, {
            onInsert: (latex) => this.insertEquation(latex),
        });
    }

    insertEquation(latex) {
        const wrapped = `$${latex}$`;
        const current = this.props.record.data[this.props.name] || "";
        const el = this.textareaRef.el;
        // selectionStart/End persist on the textarea even after focus moves
        // elsewhere (e.g. into the dialog we just closed), so this still
        // inserts at the spot the user last had their cursor. Falls back to
        // appending at the end if the field was never focused at all.
        const start = el && el.selectionStart != null ? el.selectionStart : current.length;
        const end = el && el.selectionEnd != null ? el.selectionEnd : current.length;
        const newValue = current.slice(0, start) + wrapped + current.slice(end);
        this.props.record.update({ [this.props.name]: newValue });
    }
}

export const educationMathTextField = {
    ...textField,
    component: EducationMathTextField,
    supportedTypes: ["text", "html"],
};

registry.category("fields").add("edu_math_text", educationMathTextField);
