/* Assignment Annotation Viewer for Student Portal */
(function () {
    'use strict';

    var PDFJS_CDN = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js';
    var PDFJS_WORKER = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

    function loadScript(src) {
        return new Promise(function (resolve, reject) {
            if (document.querySelector('script[src="' + src + '"]')) { resolve(); return; }
            var s = document.createElement('script');
            s.src = src;
            s.onload = resolve;
            s.onerror = reject;
            document.head.appendChild(s);
        });
    }

    /* ─── Constructor ─────────────────────────────────────────── */
    function AnnotationViewer(containerId, attachments) {
        this.container = document.getElementById(containerId);
        if (!this.container || !attachments || attachments.length === 0) return;

        this.attachments  = attachments;
        this.currentIndex = 0;
        this.currentPdf   = null;
        this.currentPage  = 1;
        this.totalPages   = 1;

        this.tool      = 'draw';
        this.color     = '#e74c3c';
        this.lineWidth = 3;
        this.isDrawing = false;

        this._activeTA   = null;   // currently open text-entry textarea
        this._activeHint = null;   // hint label below the textarea

        this.baseCanvas = document.getElementById('tm-base-canvas');
        this.annCanvas  = document.getElementById('tm-ann-canvas');
        if (!this.baseCanvas || !this.annCanvas) return;

        this.baseCtx = this.baseCanvas.getContext('2d');
        this.annCtx  = this.annCanvas.getContext('2d');

        this._bindToolbar();
        this._bindCanvas();
        this._bindTabs();
        this._bindForms();
        this._loadAttachment(0);
    }

    /* ─── Toolbar ─────────────────────────────────────────────── */
    AnnotationViewer.prototype._bindToolbar = function () {
        var self = this;
        ['draw', 'text', 'highlight', 'eraser'].forEach(function (t) {
            var btn = document.getElementById('tm-tool-' + t);
            if (btn) btn.addEventListener('click', function () { self._setTool(t); });
        });
        var cp = document.getElementById('tm-color-picker');
        if (cp) cp.addEventListener('input', function (e) { self.color = e.target.value; });

        var lw = document.getElementById('tm-line-width');
        if (lw) lw.addEventListener('input', function (e) { self.lineWidth = parseInt(e.target.value, 10); });

        var cl = document.getElementById('tm-clear-ann');
        if (cl) cl.addEventListener('click', function () {
            self.annCtx.clearRect(0, 0, self.annCanvas.width, self.annCanvas.height);
        });
        var pp = document.getElementById('tm-prev-page');
        if (pp) pp.addEventListener('click', function () {
            if (self.currentPage > 1) { self.currentPage--; self._renderPdfPage(); }
        });
        var np = document.getElementById('tm-next-page');
        if (np) np.addEventListener('click', function () {
            if (self.currentPage < self.totalPages) { self.currentPage++; self._renderPdfPage(); }
        });
    };

    AnnotationViewer.prototype._setTool = function (tool) {
        this.tool = tool;
        var self = this;
        // Dismiss open textarea when switching away from text tool
        if (tool !== 'text') {
            if (self._activeTA)   { self._activeTA.remove();   self._activeTA   = null; }
            if (self._activeHint) { self._activeHint.remove(); self._activeHint = null; }
        }
        ['draw', 'text', 'highlight', 'eraser'].forEach(function (t) {
            var btn = document.getElementById('tm-tool-' + t);
            if (!btn) return;
            btn.classList.toggle('tm-btn-primary', t === tool);
            btn.classList.toggle('tm-btn-outline', t !== tool);
        });
        var cursors = { eraser: 'cell', text: 'text', draw: 'crosshair', highlight: 'crosshair' };
        this.annCanvas.style.cursor = cursors[tool] || 'crosshair';
        // Show/hide hint panel if present in template
        var panel = document.getElementById('tm-text-panel');
        if (panel) panel.style.display = tool === 'text' ? 'block' : 'none';
    };

    /* ─── Canvas events ───────────────────────────────────────── */
    AnnotationViewer.prototype._getPos = function (e) {
        var rect   = this.annCanvas.getBoundingClientRect();
        var scaleX = this.annCanvas.width  / rect.width;
        var scaleY = this.annCanvas.height / rect.height;
        return {
            x: (e.clientX - rect.left) * scaleX,
            y: (e.clientY - rect.top)  * scaleY,
        };
    };

    AnnotationViewer.prototype._bindCanvas = function () {
        var self = this;
        this.annCanvas.addEventListener('mousedown', function (e) {
            // Prevent Chrome from focusing the overflow:auto ancestor (#tm-annotation-viewer)
            // which would immediately blur our text textarea.
            if (self.tool === 'text') e.preventDefault();
            self._onDown(e);
        });
        this.annCanvas.addEventListener('mousemove',  function (e) { self._onMove(e); });
        this.annCanvas.addEventListener('mouseup',    function (e) { self._onUp(e); });
        this.annCanvas.addEventListener('mouseleave', function (e) { self._onUp(e); });
        this.annCanvas.addEventListener('touchstart', function (e) {
            e.preventDefault(); self._onDown(e.touches[0]);
        }, { passive: false });
        this.annCanvas.addEventListener('touchmove', function (e) {
            e.preventDefault(); self._onMove(e.touches[0]);
        }, { passive: false });
        this.annCanvas.addEventListener('touchend', function (e) {
            e.preventDefault(); self._onUp(e);
        });
    };

    AnnotationViewer.prototype._onDown = function (e) {
        var pos = this._getPos(e);
        if (this.tool === 'text') {
            this._placeText(pos.x, pos.y);
            return;
        }
        this.isDrawing = true;
        this._startStroke(pos.x, pos.y);
    };

    AnnotationViewer.prototype._onMove = function (e) {
        if (!this.isDrawing) return;
        var pos = this._getPos(e);
        this._continueStroke(pos.x, pos.y);
    };

    AnnotationViewer.prototype._onUp = function () {
        if (!this.isDrawing) return;
        this.isDrawing = false;
        this.annCtx.globalAlpha = 1.0;
        this.annCtx.globalCompositeOperation = 'source-over';
    };

    AnnotationViewer.prototype._startStroke = function (x, y) {
        this.annCtx.beginPath();
        this.annCtx.moveTo(x, y);
    };

    AnnotationViewer.prototype._continueStroke = function (x, y) {
        var ctx = this.annCtx;
        if (this.tool === 'eraser') {
            var sz = this.lineWidth * 8;
            ctx.clearRect(x - sz / 2, y - sz / 2, sz, sz);
        } else if (this.tool === 'draw') {
            ctx.globalAlpha = 1.0;
            ctx.globalCompositeOperation = 'source-over';
            ctx.strokeStyle = this.color;
            ctx.lineWidth   = this.lineWidth;
            ctx.lineCap     = 'round';
            ctx.lineJoin    = 'round';
            ctx.lineTo(x, y);
            ctx.stroke();
            ctx.beginPath();
            ctx.moveTo(x, y);
        } else if (this.tool === 'highlight') {
            ctx.globalAlpha = 0.35;
            ctx.globalCompositeOperation = 'source-over';
            ctx.strokeStyle = '#ffeb3b';
            ctx.lineWidth   = this.lineWidth * 7;
            ctx.lineCap     = 'square';
            ctx.lineJoin    = 'round';
            ctx.lineTo(x, y);
            ctx.stroke();
            ctx.beginPath();
            ctx.moveTo(x, y);
        }
    };

    /* ─── Text tool ───────────────────────────────────────────── */
    AnnotationViewer.prototype._placeText = function (canvasX, canvasY) {
        var self       = this;
        var fontSize   = Math.max(16, self.lineWidth * 5);
        var lineHeight = fontSize * 1.4;

        // Remove any already-open text editor
        if (self._activeTA && self._activeTA.parentNode) {
            self._activeTA.remove();
            self._activeTA = null;
        }
        if (self._activeHint && self._activeHint.parentNode) {
            self._activeHint.remove();
            self._activeHint = null;
        }

        // Convert canvas coords → fixed viewport coords
        var rect    = self.annCanvas.getBoundingClientRect();
        var scaleX  = rect.width  / self.annCanvas.width;
        var scaleY  = rect.height / self.annCanvas.height;
        var screenX = rect.left + canvasX * scaleX;
        var screenY = rect.top  + canvasY * scaleY;

        var ta = document.createElement('textarea');
        ta.rows        = 3;
        ta.placeholder = 'Type here…\nEnter = new line\nCtrl+Enter = done';
        ta.style.cssText = [
            'position:fixed',
            'left:'   + Math.max(4, screenX) + 'px',
            'top:'    + Math.max(4, screenY) + 'px',
            'font-size:'   + fontSize + 'px',
            'font-family:Arial,sans-serif',
            'font-weight:bold',
            'color:'  + self.color,
            'background:rgba(255,255,255,0.95)',
            'border:2px dashed ' + self.color,
            'border-radius:4px',
            'padding:4px 8px',
            'outline:none',
            'min-width:200px',
            'resize:both',
            'overflow:auto',
            'line-height:' + lineHeight + 'px',
            'z-index:999999',
            'box-sizing:border-box',
            'box-shadow:0 2px 12px rgba(0,0,0,0.22)',
        ].join(';');

        // Small "Ctrl+Enter to finish" hint below the textarea
        var hint = document.createElement('div');
        hint.textContent = 'Ctrl+Enter to finish · Esc to cancel';
        hint.style.cssText = [
            'position:fixed',
            'font-size:11px',
            'color:#555',
            'background:rgba(255,255,255,0.88)',
            'padding:2px 7px',
            'border-radius:3px',
            'z-index:999999',
            'pointer-events:none',
            'white-space:nowrap',
        ].join(';');

        document.body.appendChild(ta);
        document.body.appendChild(hint);
        self._activeTA   = ta;
        self._activeHint = hint;

        function positionHint() {
            var taRect = ta.getBoundingClientRect();
            hint.style.left = taRect.left + 'px';
            hint.style.top  = (taRect.bottom + 3) + 'px';
        }
        positionHint();

        // Auto-grow height as user types
        function autoGrow() {
            ta.style.height = 'auto';
            ta.style.height = (ta.scrollHeight + 4) + 'px';
            positionHint();
        }
        ta.addEventListener('input', autoGrow);

        // Call focus() synchronously — Chrome requires focus inside mousedown handler.
        ta.focus();

        var committed = false;

        function commit() {
            if (committed) return;
            committed = true;
            if (ta.parentNode)   ta.remove();
            if (hint.parentNode) hint.remove();
            self._activeTA   = null;
            self._activeHint = null;
            // Strip leading/trailing blank lines but preserve internal newlines
            var val = ta.value.replace(/^\n+|\n+$/g, '');
            if (!val) return;
            var ctx   = self.annCtx;
            ctx.globalAlpha = 1.0;
            ctx.globalCompositeOperation = 'source-over';
            ctx.fillStyle = self.color;
            ctx.font      = 'bold ' + fontSize + 'px Arial, sans-serif';
            // Draw each line separately so multi-line text renders correctly
            var lines = val.split('\n');
            lines.forEach(function (line, i) {
                ctx.fillText(line, canvasX, canvasY + i * lineHeight);
            });
        }

        ta.addEventListener('keydown', function (e) {
            // Ctrl+Enter or Cmd+Enter → commit
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                commit();
                return;
            }
            // Escape → cancel
            if (e.key === 'Escape') {
                committed = true;
                if (ta.parentNode)   ta.remove();
                if (hint.parentNode) hint.remove();
                self._activeTA   = null;
                self._activeHint = null;
            }
            // Plain Enter → natural newline (browser default, no action needed)
        });

        // Stop clicks inside textarea from re-triggering canvas _onDown
        ta.addEventListener('mousedown', function (e) { e.stopPropagation(); });

        // Commit on blur only if text has been entered; re-focus if spurious blur (Chrome)
        ta.addEventListener('blur', function () {
            setTimeout(function () {
                if (committed) return;
                var val = ta.value.replace(/^\n+|\n+$/g, '');
                if (!val) {
                    if (ta.parentNode) ta.focus();
                } else {
                    commit();
                }
            }, 150);
        });
    };

    /* ─── Tabs ────────────────────────────────────────────────── */
    AnnotationViewer.prototype._bindTabs = function () {
        var self = this;
        this.attachments.forEach(function (att, i) {
            var tab = document.getElementById('tm-att-tab-' + i);
            if (tab) tab.addEventListener('click', function () { self._loadAttachment(i); });
        });
    };

    /* ─── Form export ─────────────────────────────────────────── */
    AnnotationViewer.prototype._bindForms = function () {
        var self = this;
        document.querySelectorAll('form[data-annotation-form]').forEach(function (form) {
            form.addEventListener('submit', function () {
                var hidden = form.querySelector('.tm-annotated-image-data');
                if (hidden) hidden.value = self._exportMerged();
            });
        });
    };

    /* ─── Attachment loading ──────────────────────────────────── */
    AnnotationViewer.prototype._loadAttachment = function (index) {
        var self = this;
        this.currentIndex = index;
        var att = this.attachments[index];

        this.attachments.forEach(function (_, i) {
            var tab = document.getElementById('tm-att-tab-' + i);
            if (!tab) return;
            tab.classList.toggle('tm-btn-primary', i === index);
            tab.classList.toggle('tm-btn-outline',  i !== index);
        });

        this.annCtx.clearRect(0, 0, this.annCanvas.width, this.annCanvas.height);
        this.currentPdf  = null;
        this.currentPage = 1;

        var url = '/web/content/' + att.id + '?access_token=' + att.access_token;

        if (att.mimetype === 'application/pdf') {
            this._showPageNav(true);
            loadScript(PDFJS_CDN).then(function () {
                if (window.pdfjsLib) {
                    window.pdfjsLib.GlobalWorkerOptions.workerSrc = PDFJS_WORKER;
                }
                self._loadPdf(url);
            });
        } else {
            this._showPageNav(false);
            this._loadImage(url);
        }
    };

    AnnotationViewer.prototype._loadPdf = function (url) {
        var self = this;
        window.pdfjsLib.getDocument(url).promise.then(function (pdf) {
            self.currentPdf  = pdf;
            self.totalPages  = pdf.numPages;
            self._renderPdfPage();
        }).catch(function (err) {
            console.error('[Annotator] PDF load error:', err);
        });
    };

    AnnotationViewer.prototype._renderPdfPage = function () {
        var self = this;
        if (!this.currentPdf) return;
        this.currentPdf.getPage(this.currentPage).then(function (page) {
            var containerW = self.baseCanvas.parentElement.parentElement.clientWidth || 760;
            var vp1   = page.getViewport({ scale: 1 });
            var scale = Math.min(containerW / vp1.width, 2.5);
            var vp    = page.getViewport({ scale: scale });

            self.baseCanvas.width  = vp.width;
            self.baseCanvas.height = vp.height;
            self.annCanvas.width   = vp.width;
            self.annCanvas.height  = vp.height;

            page.render({ canvasContext: self.baseCtx, viewport: vp }).promise.then(function () {
                self._updatePageIndicator();
            });
            self.annCtx.clearRect(0, 0, vp.width, vp.height);
        });
    };

    AnnotationViewer.prototype._loadImage = function (url) {
        var self = this;
        var img  = new Image();
        img.crossOrigin = 'anonymous';
        img.onload = function () {
            var containerW = self.baseCanvas.parentElement.parentElement.clientWidth || 760;
            var scale = Math.min(containerW / img.naturalWidth, 1);
            var w = Math.round(img.naturalWidth  * scale);
            var h = Math.round(img.naturalHeight * scale);
            self.baseCanvas.width  = w;
            self.baseCanvas.height = h;
            self.annCanvas.width   = w;
            self.annCanvas.height  = h;
            self.baseCtx.drawImage(img, 0, 0, w, h);
            self.annCtx.clearRect(0, 0, w, h);
        };
        img.src = url;
    };

    AnnotationViewer.prototype._showPageNav = function (show) {
        var nav = document.getElementById('tm-page-nav');
        if (nav) nav.style.display = show ? 'flex' : 'none';
    };

    AnnotationViewer.prototype._updatePageIndicator = function () {
        var el = document.getElementById('tm-page-indicator');
        if (el) el.textContent = 'Page ' + this.currentPage + ' / ' + this.totalPages;
    };

    AnnotationViewer.prototype._exportMerged = function () {
        var merged = document.createElement('canvas');
        merged.width  = this.baseCanvas.width;
        merged.height = this.baseCanvas.height;
        var ctx = merged.getContext('2d');
        ctx.drawImage(this.baseCanvas, 0, 0);
        ctx.drawImage(this.annCanvas,  0, 0);
        return merged.toDataURL('image/png');
    };

    /* ─── Boot ────────────────────────────────────────────────── */
    document.addEventListener('DOMContentLoaded', function () {
        var container = document.getElementById('tm-annotation-viewer');
        if (!container) return;
        var attachments = [];
        try { attachments = JSON.parse(container.dataset.attachments || '[]'); } catch (e) { return; }
        if (!attachments.length) return;
        window.tmAnnotationViewer = new AnnotationViewer('tm-annotation-viewer', attachments);
    });
})();
