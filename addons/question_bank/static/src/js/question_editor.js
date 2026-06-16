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

patch(FormRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        onMounted(() => this._mountQbPreview());
        onPatched(() => this._mountQbPreview());
    },

    _mountQbPreview() {
        const model = this.props.model;
        if (!model || model.root.resModel !== "qb.question") return;

        const rendererEl = (this.__owl__ && this.__owl__.bdom && this.__owl__.bdom.el) ? this.__owl__.bdom.el : null;
        const root = rendererEl && rendererEl.querySelector ? rendererEl.querySelector("#qb-live-preview-root") : null;
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
                options: (((data.option_ids && data.option_ids.records) ? data.option_ids.records : [])).map(r => ({
                    option_text: r.data.option_text || "",
                    is_correct:  r.data.is_correct  || false,
                })),
            };
        };

        // Mount a lightweight HTML preview; keep it robust for create-mode (new record)
        // where relying on OWL internal component tree lookups is brittle.
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
        const rendererEl = (this.__owl__ && this.__owl__.bdom && this.__owl__.bdom.el) ? this.__owl__.bdom.el : null;
        const root = rendererEl && rendererEl.querySelector ? rendererEl.querySelector("#qb-live-preview-root") : null;
        if (root && root._qbInterval) clearInterval(root._qbInterval);
        if (super.__destroy__) {
            super.__destroy__(...arguments);
        }
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

    // HTML content (trusted — from our own HTML field). LaTeX delimiters inside
    // this HTML are typeset by MathJax via renderMathJax(root).
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

    // MCQ options (option_text is HTML; MathJax will typeset any LaTeX delimiters)
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

// Preview mounting is handled via the FormRenderer patch above.
