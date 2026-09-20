/** @odoo-module **/

/**
 * Minimal MathJax v3 loader, shared by every module in the Education suite.
 *
 * Curriculum authors write equations as plain LaTeX delimiters directly in
 * description/body text (e.g. `$x^2$`, `\(x^2\)`, `$$...$$`) — without this,
 * that text just renders as literal characters ("$x^2$") instead of proper
 * math. This loads MathJax once and configures the delimiters; the actual
 * (re-)typesetting of a given bit of DOM after it renders/updates is
 * triggered separately — see education_math_text_field.js for backend
 * fields, and curriculum_tree.js for the Curriculum Structure Tree page.
 *
 * (Mirrors question_bank/static/src/js/mathjax_loader.js — kept as a
 * separate copy here rather than a cross-module dependency, since the two
 * apps are unrelated; loading the same CDN script twice if both happen to
 * be installed is harmless, MathJax no-ops once window.MathJax exists.)
 */

function ensureMathJaxLoaded() {
    if (window.MathJax) {
        return;
    }
    if (window.__eduMathJaxLoading) {
        return;
    }
    window.__eduMathJaxLoading = true;

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
        // Best-effort initial typeset for whatever's already on the page
        // (covers server-rendered portal pages, which never call
        // typesetPromise() explicitly themselves).
        try {
            window.MathJax?.typesetPromise?.();
        } catch (_) { /* ignore */ }
    };
    document.head.appendChild(script);
}

ensureMathJaxLoaded();
