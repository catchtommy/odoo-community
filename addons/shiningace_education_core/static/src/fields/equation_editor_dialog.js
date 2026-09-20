/** @odoo-module **/
import { Component, useRef, onMounted, onWillDestroy } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

/**
 * Lets a curriculum author build an equation visually (via MathLive's
 * <math-field>: click buttons or type natural shorthand like "x^2" or
 * "sqrt(", both auto-format live) instead of typing raw LaTeX. On
 * "Insert", hands the resulting LaTeX string back to whoever opened the
 * dialog (see education_math_text_field.js) to be wrapped in $...$ and
 * spliced into the underlying text field.
 */
export class EquationEditorDialog extends Component {
    static template = "shiningace_education_core.EquationEditorDialog";
    static components = { Dialog };
    static props = { close: Function, onInsert: Function };

    setup() {
        this.mathFieldRef = useRef("mathField");
        onMounted(() => {
            const el = this.mathFieldRef.el;
            if (!el) {
                return;
            }
            // MathLive's default virtual-keyboard policy ("auto") only
            // auto-shows the on-screen keyboard on touch devices — on a
            // normal mouse/desktop browser it never appears on its own,
            // which is why the dialog looked like it had no buttons at
            // all. "manual" + explicit show()/hide() on focus makes it
            // show every time regardless of input device. (z-index is
            // handled separately in CSS — MathLive's keyboard defaults to
            // z-index 105, which sits behind this Dialog's own backdrop.)
            el.mathVirtualKeyboardPolicy = "manual";
            el.addEventListener("focusin", () => window.mathVirtualKeyboard?.show());
            el.addEventListener("focusout", () => window.mathVirtualKeyboard?.hide());
            el.focus();
            window.mathVirtualKeyboard?.show();
        });
        // Whether the dialog closes via Insert, Cancel, Esc, or clicking
        // outside — always dismiss the keyboard with it, so it doesn't
        // stay stuck open over the rest of the page.
        onWillDestroy(() => window.mathVirtualKeyboard?.hide());
    }

    insert() {
        const el = this.mathFieldRef.el;
        const latex = el && el.value ? el.value.trim() : "";
        if (latex) {
            this.props.onInsert(latex);
        }
        this.props.close();
    }
}
