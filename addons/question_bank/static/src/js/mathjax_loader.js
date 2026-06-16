/** @odoo-module **/

/**
 * Minimal MathJax v3 loader for backend views.
 *
 * We need this because Moodle XML frequently contains LaTeX delimiters in the
 * HTML (e.g. `$...$`, `$$...$$`, `\\(...\\)`), and the question bank preview/editor
 * relies on MathJax to typeset it.
 */

function ensureMathJaxLoaded() {
    if (window.MathJax) {
        return;
    }
    if (window.__qbMathJaxLoading) {
        return;
    }
    window.__qbMathJaxLoading = true;

    // Configure before loading the library.
    window.MathJax = {
        tex: {
            inlineMath: [["$", "$"], ["\\(", "\\)"]],
            displayMath: [["$$", "$$"], ["\\[", "\\]"]],
            processEscapes: true,
        },
        options: {
            skipHtmlTags: ["script", "noscript", "style", "textarea", "pre", "code"],
        },
    };

    const script = document.createElement("script");
    script.async = true;
    script.src = "https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js";
    script.onload = () => {
        // Best-effort initial typeset for already-rendered content.
        try {
            window.MathJax?.typesetPromise?.();
        } catch (_) {}
    };
    document.head.appendChild(script);
}

// Load once when the backend bundle is evaluated.
ensureMathJaxLoaded();

