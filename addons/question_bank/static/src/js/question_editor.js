/** @odoo-module **/

import { registry }       from "@web/core/registry";
import { Component, useState, useEffect, useRef, onMounted, onPatched }
    from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { TextField }      from "@web/views/fields/text/text_field";

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Trigger MathJax re-render on a DOM node (if MathJax is loaded). */
function renderMathJax(el) {
    if (!el) return;
    if (window.MathJax) {
        try {
            if (MathJax.typesetPromise) {
                MathJax.typesetPromise([el]);
            } else if (MathJax.Hub) {
                MathJax.Hub.Queue(["Typeset", MathJax.Hub, el]);
            }
        } catch (_) { /* MathJax not ready yet */ }
    }
}

function safeParseJson(str) {
    try { return JSON.parse(str); }
    catch (_) { return null; }
}

// ─── Live Preview Component ────────────────────────────────────────────────────

class QuestionPreview extends Component {
    static template = "question_bank.QuestionPreview";
    static props = { question: Object };

    latexContainer = useRef("latexContainer");

    get typeLabel() {
        const labels = {
            mcq:        "MCQ",
            true_false: "True / False",
            fill_blank: "Fill in the Blank",
        };
        return labels[this.props.question.question_type] || "—";
    }

    get difficultyLabel() {
        const labels = { easy: "Easy", medium: "Medium", hard: "Hard" };
        return labels[this.props.question.difficulty] || "—";
    }

    get formattedGraph() {
        const parsed = safeParseJson(this.props.question.graph_json);
        return parsed ? JSON.stringify(parsed, null, 2) : this.props.question.graph_json;
    }

    setup() {
        onMounted(() => renderMathJax(this.latexContainer.el));
        onPatched(() => renderMathJax(this.latexContainer.el));
    }
}

// ─── LaTeX Preview Field Widget ───────────────────────────────────────────────

class LatexPreviewWidget extends Component {
    static template = "question_bank.LatexPreviewWidget";
    static props    = { ...standardFieldProps, placeholder: { type: String, optional: true } };

    latexBox = useRef("latexBox");

    onInput(ev) {
        this.props.record.update({ [this.props.name]: ev.target.value });
    }

    setup() {
        onPatched(() => renderMathJax(this.latexBox.el));
        onMounted(() => renderMathJax(this.latexBox.el));
    }
}

registry.category("fields").add("qb_latex_preview", {
    component: LatexPreviewWidget,
    supportedTypes: ["text", "char"],
});

// ─── Graph Editor Field Widget ─────────────────────────────────────────────────

class GraphEditorWidget extends Component {
    static template = "question_bank.GraphEditorWidget";
    static props    = { ...standardFieldProps, placeholder: { type: String, optional: true } };

    get jsonValid() {
        return !!safeParseJson(this.props.record.data[this.props.name]);
    }

    get formattedJson() {
        const parsed = safeParseJson(this.props.record.data[this.props.name]);
        return parsed ? JSON.stringify(parsed, null, 2) : "";
    }

    get value() {
        return this.props.record.data[this.props.name] || "";
    }

    onInput(ev) {
        this.props.record.update({ [this.props.name]: ev.target.value });
    }
}

registry.category("fields").add("qb_graph_editor", {
    component: GraphEditorWidget,
    supportedTypes: ["text"],
});

// ─── Live Preview Panel Mount ──────────────────────────────────────────────────
//
// We attach an OWL QuestionPreview component to the #qb-live-preview-root div
// rendered in the form view. We watch the form model for changes and re-render.
//

registry.category("form_footers").add("qb_question_preview", {
    // Using a service-style hook so it applies globally when the form is visible.
    // Actual mount is done via a FormController patch below.
});

// Patch FormRenderer to mount the preview when viewing a qb.question form.
import { patch }           from "@web/core/utils/patch";
import { FormRenderer }    from "@web/views/form/form_renderer";
import { useService }      from "@web/core/utils/hooks";
import { App }             from "@odoo/owl";

patch(FormRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        this._qbPreviewApp = null;
    },

    _mountQbPreview() {
        const model = this.props.model;
        if (!model || model.root.resModel !== "qb.question") return;

        const root = this.__owl__.bdom?.el?.querySelector?.("#qb-live-preview-root");
        if (!root || root.dataset.qbMounted) return;
        root.dataset.qbMounted = "1";

        const getQuestion = () => {
            const data = model.root.data || {};
            return {
                name:             data.name || "",
                question_type:    data.question_type || "mcq",
                difficulty:       data.difficulty || "medium",
                marks:            data.marks || 0,
                question_html:    data.question_html || "",
                explanation:      data.explanation || "",
                latex_equation:   data.latex_equation || "",
                graph_json:       data.graph_json || "",
                true_false_answer: data.true_false_answer || "",
                blank_answer:     data.blank_answer || "",
                options: (data.option_ids?.records || []).map(r => ({
                    option_text: r.data.option_text || "",
                    is_correct:  r.data.is_correct  || false,
                })),
            };
        };

        class PreviewRoot extends Component {
            static template = "question_bank.QuestionPreview";
            static components = {};
            setup() {
                this.question = useState(getQuestion());
                // Poll every 600 ms for field changes (OWL form model is reactive
                // but external subscription is the safest approach here).
                this._interval = setInterval(() => {
                    const fresh = getQuestion();
                    Object.assign(this.question, fresh);
                }, 600);
            }
            get typeLabel() {
                const labels = { mcq: "MCQ", true_false: "True / False", fill_blank: "Fill in the Blank" };
                return labels[this.question.question_type] || "—";
            }
            get difficultyLabel() {
                const labels = { easy: "Easy", medium: "Medium", hard: "Hard" };
                return labels[this.question.difficulty] || "—";
            }
            get formattedGraph() {
                const p = safeParseJson(this.question.graph_json);
                return p ? JSON.stringify(p, null, 2) : this.question.graph_json;
            }
            get latexContainer() { return { el: this.__owl__.bdom?.el?.querySelector(".qb-latex-render") }; }
        }

        PreviewRoot.components = { QuestionPreview };

        this._qbPreviewApp = new App(PreviewRoot, {
            templates: odoo.__qb_templates__ || {},
            env: { _t: (s) => s },
            dev: false,
        });
        // Use simple template approach — the template is already registered globally.
        // We'll mount with a simpler inline component using the registered template.
        this._mountSimplePreview(root, model, getQuestion);
    },

    _mountSimplePreview(root, model, getQuestion) {
        // Clean approach: render preview as reactive HTML without full OWL App
        // (avoids double-App issues). Sync every 600ms.
        const render = () => {
            const q = getQuestion();
            root.innerHTML = buildPreviewHTML(q);
            renderMathJax(root);
        };
        render();
        root._qbInterval = setInterval(render, 600);
    },

    __destroy__() {
        // clean up interval if present
        const root = this.__owl__?.bdom?.el?.querySelector?.("#qb-live-preview-root");
        if (root && root._qbInterval) clearInterval(root._qbInterval);
        super.__destroy__?.(...arguments);
    },
});

// ─── HTML Preview Builder ──────────────────────────────────────────────────────

function buildPreviewHTML(q) {
    if (!q.name) {
        return `<div class="qb-preview-empty text-center py-4 text-muted">
                    <i class="fa fa-eye-slash fa-2x"></i>
                    <p class="mt-2">Fill in details to see a live preview.</p>
                </div>`;
    }

    const typeLabels = { mcq: "MCQ", true_false: "True / False", fill_blank: "Fill in the Blank" };
    const diffLabels = { easy: "Easy", medium: "Medium", hard: "Hard" };
    const escape = (s) => String(s || "")
        .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

    let html = `<div class="qb-preview-content">`;

    // Badges
    html += `<div class="qb-preview-badges d-flex gap-2 flex-wrap mb-3">
        <span class="badge qb-type-badge qb-type-${escape(q.question_type)}">${escape(typeLabels[q.question_type] || q.question_type)}</span>
        <span class="badge qb-diff-badge qb-diff-${escape(q.difficulty)}">${escape(diffLabels[q.difficulty] || q.difficulty)}</span>
        <span class="badge text-bg-secondary">${escape(q.marks)} mark(s)</span>
    </div>`;

    // Title
    html += `<h5 class="qb-preview-title">${escape(q.name)}</h5>`;

    // HTML content (trusted — from our own HTML field)
    if (q.question_html) {
        html += `<div class="qb-preview-html">${q.question_html}</div>`;
    }

    // LaTeX
    if (q.latex_equation) {
        html += `<div class="qb-preview-latex mt-3">
            <div class="qb-preview-section-label">Equation</div>
            <div class="qb-latex-render">\\( ${escape(q.latex_equation)} \\)</div>
        </div>`;
    }

    // Graph
    if (q.graph_json) {
        const p = safeParseJson(q.graph_json);
        const display = p ? JSON.stringify(p, null, 2) : q.graph_json;
        html += `<div class="qb-preview-graph mt-3">
            <div class="qb-preview-section-label">Graph Config</div>
            <pre class="qb-graph-json">${escape(display)}</pre>
        </div>`;
    }

    // MCQ options
    if (q.question_type === "mcq" && q.options && q.options.length) {
        html += `<div class="qb-preview-options mt-3">
            <div class="qb-preview-section-label">Options</div>
            <div class="qb-preview-options-list">`;
        q.options.forEach((opt, i) => {
            const letter = String.fromCharCode(65 + i);
            const cls = opt.is_correct ? "qb-preview-option qb-preview-option--correct" : "qb-preview-option";
            html += `<div class="${cls}">
                <span class="qb-option-letter">${letter}</span>
                <span class="qb-option-text">${opt.option_text || ""}</span>
                ${opt.is_correct ? '<i class="fa fa-check-circle text-success ms-2"></i>' : ""}
            </div>`;
        });
        html += `</div></div>`;
    }

    // True/False
    if (q.question_type === "true_false" && q.true_false_answer) {
        const isTrue = q.true_false_answer === "true";
        html += `<div class="qb-preview-tf mt-3">
            <div class="qb-preview-section-label">Correct Answer</div>
            <span class="badge fs-6 ${isTrue ? "text-bg-success" : "text-bg-danger"}">
                <i class="fa ${isTrue ? "fa-check" : "fa-times"} me-1"></i>
                ${isTrue ? "TRUE" : "FALSE"}
            </span>
        </div>`;
    }

    // Fill in the blank
    if (q.question_type === "fill_blank" && q.blank_answer) {
        html += `<div class="qb-preview-blank mt-3">
            <div class="qb-preview-section-label">Correct Answer</div>
            <span class="badge text-bg-primary fs-6">
                <i class="fa fa-key me-1"></i>${escape(q.blank_answer)}
            </span>
        </div>`;
    }

    // Explanation
    if (q.explanation) {
        html += `<div class="qb-preview-explanation mt-3">
            <div class="qb-preview-section-label">
                <i class="fa fa-lightbulb-o me-1"></i> Explanation
            </div>
            <div class="qb-preview-html qb-preview-html--explanation">${q.explanation}</div>
        </div>`;
    }

    html += `</div>`;
    return html;
}

// ─── Trigger preview mount after form renders ──────────────────────────────────

// We use a MutationObserver to detect when the preview root appears in the DOM.
const observer = new MutationObserver(() => {
    document.querySelectorAll("#qb-live-preview-root:not([data-qb-mounted])").forEach(root => {
        root.dataset.qbMounted = "1";
        // Find the nearest form model via OWL component tree
        const formEl = root.closest(".o_form_view");
        if (!formEl) return;

        // Get the OWL component from the DOM element
        const owlNode = formEl.__owl__;
        const model = owlNode?.component?.props?.model || owlNode?.component?.model;

        const getQuestion = () => {
            try {
                const data = model?.root?.data || {};
                return {
                    name:              data.name || "",
                    question_type:     data.question_type || "mcq",
                    difficulty:        data.difficulty || "medium",
                    marks:             data.marks || 0,
                    question_html:     data.question_html || "",
                    explanation:       data.explanation || "",
                    latex_equation:    data.latex_equation || "",
                    graph_json:        data.graph_json || "",
                    true_false_answer: data.true_false_answer || "",
                    blank_answer:      data.blank_answer || "",
                    options: (data.option_ids?.records || []).map(r => ({
                        option_text: r.data?.option_text || "",
                        is_correct:  r.data?.is_correct  || false,
                    })),
                };
            } catch (_) { return {}; }
        };

        const render = () => {
            root.innerHTML = buildPreviewHTML(getQuestion());
            renderMathJax(root);
        };

        render();
        root._qbInterval = setInterval(render, 700);
    });
});

// Defer until DOM is ready so document.body is guaranteed to exist.
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
        observer.observe(document.body, { childList: true, subtree: true });
    });
} else {
    observer.observe(document.body, { childList: true, subtree: true });
}
