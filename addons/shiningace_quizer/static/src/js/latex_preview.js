/** @odoo-module **/
/**
 * ShiningAce Quizer - LaTeX Preview Widget
 * Provides real-time LaTeX preview in the question editor.
 */

import { registry } from '@web/core/registry';
import { parseXML, Component, useState, onWillStart, useRef } from '@odoo/owl';
import { useService } from '@web/core/utils/hooks';

export class ShiningAceLatexPreview extends Component {
    static template = 'shiningace.LatexPreview';

    setup() {
        this.state = useState({
            latexSource: '',
            rendered: false,
            error: '',
        });

        this.previewRef = useRef('latexPreview');
    }

    /**
     * Render LaTeX content for preview.
     * This triggers MathJax/KaTeX rendering if available.
     */
    renderLatex(latex) {
        this.state.latexSource = latex;
        this.state.error = '';

        if (!latex) {
            this.state.rendered = false;
            return;
        }

        try {
            // If MathJax is available, use it
            if (window.MathJax && window.MathJax.typesetPromise) {
                const container = this.previewRef.el;
                if (container) {
                    container.innerHTML = `<div class="latex-content">$$${latex}$$</div>`;
                    window.MathJax.typesetPromise([container])
                        .then(() => {
                            this.state.rendered = true;
                        })
                        .catch((err) => {
                            this.state.error = `MathJax error: ${err.message}`;
                        });
                }
            }
            // If KaTeX is available, use it
            else if (window.katex) {
                const container = this.previewRef.el;
                if (container) {
                    try {
                        const html = window.katex.renderToString(latex, {
                            throwOnError: true,
                            displayMode: true,
                        });
                        container.innerHTML = html;
                        this.state.rendered = true;
                    } catch (err) {
                        this.state.error = `KaTeX error: ${err.message}`;
                    }
                }
            }
            // Fallback: display raw LaTeX
            else {
                const container = this.previewRef.el;
                if (container) {
                    container.innerHTML = `
                        <div class="alert alert-info">
                            <strong>LaTeX Source:</strong><br/>
                            <code>${latex}</code>
                        </div>
                        <div class="alert alert-warning">
                            <i class="fa fa-info-circle"></i>
                            Install MathJax or KaTeX for rendered preview.
                        </div>
                    `;
                    this.state.rendered = true;
                }
            }
        } catch (err) {
            this.state.error = err.message;
        }
    }
}

registry
    .category('widgets')
    .add('shiningace_latex_preview', ShiningAceLatexPreview);
