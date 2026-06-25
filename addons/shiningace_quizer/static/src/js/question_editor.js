/** @odoo-module **/
/**
 * ShiningAce Quizer - Enhanced Question Editor
 * Provides LaTeX integration and dual HTML/LaTeX editing capabilities.
 */

import { registry } from '@web/core/registry';
import { FormController } from '@web/views/form/form_controller';

// Extend the form controller for question-specific behaviour
export class ShiningAceQuestionFormController extends FormController {
    setup() {
        super.setup();
        // Additional setup for question editor
    }
}

registry
    .category('views')
    .add('shiningace_question_form', ShiningAceQuestionFormController);

/**
 * Helper function to detect LaTeX content in text
 */
export function containsLatex(text) {
    if (!text) return false;
    return (
        text.includes('$$') ||
        text.includes('\\(') ||
        text.includes('\\[') ||
        text.includes('\\begin{equation}') ||
        text.includes('\\begin{align}')
    );
}

/**
 * Helper to extract LaTeX expressions from text
 */
export function extractLatexExpressions(text) {
    if (!text) return [];
    const expressions = [];

    // Match $$...$$ blocks
    const blockPattern = /\$\$(.*?)\$\$/gs;
    let match;
    while ((match = blockPattern.exec(text)) !== null) {
        expressions.push({
            type: 'display',
            latex: match[1],
            fullMatch: match[0],
            start: match.index,
            end: match.index + match[0].length,
        });
    }

    // Match inline \(...\) patterns
    const inlinePattern = /\\\((.*?)\\\)/gs;
    while ((match = inlinePattern.exec(text)) !== null) {
        expressions.push({
            type: 'inline',
            latex: match[1],
            fullMatch: match[0],
            start: match.index,
            end: match.index + match[0].length,
        });
    }

    return expressions;
}

/**
 * Preview LaTeX expressions by wrapping them in spans with a latex class
 * This works with MathJax/KaTeX if configured on the frontend
 */
export function prepareLatexPreview(text) {
    if (!text) return text;

    // Process display math
    text = text.replace(/\$\$(.*?)\$\$/gs, (match, latex) => {
        return `<span class="shiningace-latex-display" data-latex="${latex.trim()}">${match}</span>`;
    });

    // Process inline math
    text = text.replace(/\\\((.*?)\\\)/gs, (match, latex) => {
        return `<span class="shiningace-latex-inline" data-latex="${latex.trim()}">${match}</span>`;
    });

    return text;
}
