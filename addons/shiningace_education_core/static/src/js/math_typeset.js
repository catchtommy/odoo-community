/** @odoo-module **/

/**
 * Trigger a MathJax re-typeset on a specific DOM node (if MathJax has
 * loaded yet — it's an async CDN script, see mathjax_loader.js). Shared by
 * every OWL component/widget in the Education suite that displays
 * curriculum text which may contain LaTeX delimiters.
 */
export function renderMathJax(el) {
    if (!el || !window.MathJax) {
        return;
    }
    try {
        if (window.MathJax.typesetPromise) {
            window.MathJax.typesetPromise([el]);
        } else if (window.MathJax.Hub) {
            window.MathJax.Hub.Queue(["Typeset", window.MathJax.Hub, el]);
        }
    } catch (_) {
        /* MathJax not fully ready yet — the loader's own onload handler
           will do a page-wide typeset once it is. */
    }
}
