/** @odoo-module **/

/**
 * Loads MathLive (https://cortexjs.io/mathlive/) — an open-source (MIT),
 * fully client-side visual math input. It defines a <math-field> custom
 * element: curriculum authors click/type to build an equation (fractions,
 * exponents, square roots, Greek letters, etc. all have on-screen buttons
 * and keyboard shortcuts, e.g. typing "x^2" or "sqrt(" auto-formats), and
 * `.value` on the element gives back correct LaTeX — no LaTeX knowledge
 * needed. See equation_editor_dialog.js for the dialog that hosts it and
 * education_math_text_field.js for the "Insert Equation" button that opens
 * that dialog from a curriculum text field.
 *
 * Backend-only (web.assets_backend) — this is an authoring tool for
 * curriculum managers/admins, not something shown to students/tutors
 * reading already-published content.
 */
function ensureMathLiveLoaded() {
    if (window.customElements && window.customElements.get("math-field")) {
        return;
    }
    if (window.__eduMathLiveLoading) {
        return;
    }
    window.__eduMathLiveLoading = true;

    // Plain classic script (NOT type="module" — that's what the .mjs
    // build is for), matching MathLive's own documented CDN usage. The
    // path must include /dist/: the bare "mathlive@0.98/mathlive.min.js"
    // 404s (the package ships its browser bundles under dist/, not at the
    // package root for this version), which silently fails — the script
    // tag just never loads, <math-field> never gets registered as a
    // custom element, and it renders as a dead, non-interactive tag with
    // no keyboard and no way to type anything into it.
    const script = document.createElement("script");
    script.defer = true;
    script.src = "https://cdn.jsdelivr.net/npm/mathlive@0.98.6/dist/mathlive.min.js";
    document.head.appendChild(script);
}

ensureMathLiveLoaded();
