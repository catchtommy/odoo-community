/* AI Chatbot — pure vanilla JS, no framework dependencies.
   Injected on every website/portal page via website_templates.xml */
(function () {
    "use strict";

    // ── Markdown → HTML (XSS-safe) ────────────────────────────────────────────
    function renderMarkdown(text) {
        if (!text) return "";
        let h = text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");
        // fenced code blocks
        h = h.replace(/```[\w]*\n?([\s\S]*?)```/g, (_, c) => `<pre><code>${c.trim()}</code></pre>`);
        // inline code
        h = h.replace(/`([^`]+)`/g, "<code>$1</code>");
        // bold / italic
        h = h.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
        h = h.replace(/\*(.+?)\*/g, "<em>$1</em>");
        // unordered lists
        h = h.replace(/^[ \t]*[-*] (.+)$/gm, "<li>$1</li>");
        h = h.replace(/(<li>[\s\S]*?<\/li>)/g, "<ul>$1</ul>");
        // ordered lists
        h = h.replace(/^\d+\. (.+)$/gm, "<li>$1</li>");
        // line breaks
        h = h.replace(/\n/g, "<br>");
        return h;
    }

    // ── JSON-RPC helper ───────────────────────────────────────────────────────
    async function rpc(route, params) {
        const res = await fetch(route, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest",
            },
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "call",
                id: Math.floor(Math.random() * 1e9),
                params,
            }),
        });
        if (!res.ok) throw new Error("HTTP " + res.status);
        const json = await res.json();
        if (json.error) {
            throw new Error(json.error.data?.message || json.error.message || "RPC error");
        }
        return json.result;
    }

    // ── Time helper ───────────────────────────────────────────────────────────
    function nowTime() {
        return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    }

    // ── Build widget HTML ─────────────────────────────────────────────────────
    function buildHTML(title, placeholder) {
        return `
<button class="sa-chat-launcher" id="sa-launcher" aria-label="AI Assistant">
  <span class="sa-chat-launcher__icon sa-chat-launcher__icon--chat" id="sa-icon-open">
    <svg viewBox="0 0 24 24" fill="none"><path d="M12 2C6.477 2 2 6.253 2 11.5c0 2.304.875 4.408 2.31 6.026L3 21l3.677-1.433A10.12 10.12 0 0012 21c5.523 0 10-4.253 10-9.5S17.523 2 12 2z" fill="currentColor"/><circle cx="8" cy="11.5" r="1.2" fill="white"/><circle cx="12" cy="11.5" r="1.2" fill="white"/><circle cx="16" cy="11.5" r="1.2" fill="white"/></svg>
  </span>
  <span class="sa-chat-launcher__icon sa-chat-launcher__icon--close d-none" id="sa-icon-close">
    <svg viewBox="0 0 24 24" fill="none"><path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/></svg>
  </span>
</button>

<div class="sa-chat-window" id="sa-chat-window">
  <div class="sa-chat-header">
    <div class="sa-chat-header__avatar">
      <svg viewBox="0 0 36 36" fill="none"><circle cx="18" cy="18" r="18" fill="rgba(255,255,255,0.2)"/><path d="M18 8C12.477 8 8 12.253 8 17.5c0 1.904.572 3.677 1.555 5.16L8 26l3.51-1.147A9.96 9.96 0 0018 27c5.523 0 10-4.253 10-9.5S23.523 8 18 8z" fill="white"/><circle cx="14" cy="17.5" r="1.1" fill="#6366f1"/><circle cx="18" cy="17.5" r="1.1" fill="#6366f1"/><circle cx="22" cy="17.5" r="1.1" fill="#6366f1"/></svg>
    </div>
    <div class="sa-chat-header__info">
      <span class="sa-chat-header__title">${escHtml(title)}</span>
      <span class="sa-chat-header__status"><span class="sa-chat-header__dot"></span>Online</span>
    </div>
    <button class="sa-chat-header__close" id="sa-header-close" aria-label="Close">
      <svg viewBox="0 0 24 24" fill="none"><path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
    </button>
  </div>

  <div class="sa-chat-messages" id="sa-messages">
    <div class="sa-chat-welcome" id="sa-welcome">
      <div class="sa-chat-welcome__icon">🤖</div>
      <p class="sa-chat-welcome__text">Hi there! I'm your AI assistant. How can I help you today?</p>
      <div class="sa-chat-suggestions" id="sa-suggestions">
        <button class="sa-chat-suggestion">What services do you offer?</button>
        <button class="sa-chat-suggestion">How do I enrol a student?</button>
        <button class="sa-chat-suggestion">Tell me about your tutors</button>
        <button class="sa-chat-suggestion">What are your pricing plans?</button>
      </div>
    </div>
  </div>

  <div class="sa-chat-input-area">
    <textarea class="sa-chat-input" id="sa-input"
              placeholder="${escHtml(placeholder)}"
              rows="1" maxlength="2000"></textarea>
    <button class="sa-chat-send" id="sa-send" aria-label="Send">
      <svg viewBox="0 0 24 24" fill="none"><path d="M22 2L11 13M22 2L15 22l-4-9-9-4 20-7z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
    </button>
  </div>
  <div class="sa-chat-footer">Powered by AI · <a href="#" tabindex="-1">Shiningace</a></div>
</div>`;
    }

    function escHtml(s) {
        return String(s || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    // ── Core chatbot logic ────────────────────────────────────────────────────
    function initChatbot(rootDiv) {
        const title       = rootDiv.dataset.title       || "AI Assistant";
        const placeholder = rootDiv.dataset.placeholder || "Type your question…";

        // Create wrapper
        const wrapper = document.createElement("div");
        wrapper.id = "sa-ai-chatbot-mount";
        wrapper.innerHTML = buildHTML(title, placeholder);
        document.body.appendChild(wrapper);

        // Refs
        const launcher    = wrapper.querySelector("#sa-launcher");
        const iconOpen    = wrapper.querySelector("#sa-icon-open");
        const iconClose   = wrapper.querySelector("#sa-icon-close");
        const chatWindow  = wrapper.querySelector("#sa-chat-window");
        const headerClose = wrapper.querySelector("#sa-header-close");
        const messagesEl  = wrapper.querySelector("#sa-messages");
        const inputEl     = wrapper.querySelector("#sa-input");
        const sendBtn     = wrapper.querySelector("#sa-send");
        const suggestions = wrapper.querySelectorAll(".sa-chat-suggestion");
        const welcomeDiv  = wrapper.querySelector("#sa-welcome");

        let isOpen    = false;
        let isLoading = false;
        let history   = [];          // [{role, content}, ...]

        // Stable session ID for this browser session
        const sessionId = (
            sessionStorage.getItem("sa_chatbot_sid") ||
            (() => {
                const id = "sid-" + Math.random().toString(36).slice(2) + "-" + Date.now();
                sessionStorage.setItem("sa_chatbot_sid", id);
                return id;
            })()
        );

        // ── Toggle ──────────────────────────────────────────────────────────
        function toggleChat() {
            isOpen = !isOpen;
            chatWindow.classList.toggle("sa-chat-window--open", isOpen);
            launcher.classList.toggle("sa-chat-launcher--open", isOpen);
            iconOpen.classList.toggle("d-none", isOpen);
            iconClose.classList.toggle("d-none", !isOpen);
            if (isOpen) setTimeout(() => inputEl.focus(), 320);
        }

        launcher.addEventListener("click", toggleChat);
        headerClose.addEventListener("click", toggleChat);

        // ── Suggestions ─────────────────────────────────────────────────────
        suggestions.forEach(btn => {
            btn.addEventListener("click", () => sendMessage(btn.textContent.trim()));
        });

        // ── Input ───────────────────────────────────────────────────────────
        sendBtn.addEventListener("click", () => {
            const text = inputEl.value.trim();
            if (text) sendMessage(text);
        });

        inputEl.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                const text = inputEl.value.trim();
                if (text) sendMessage(text);
            }
        });

        // Auto-resize textarea
        inputEl.addEventListener("input", () => {
            inputEl.style.height = "auto";
            inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + "px";
        });

        // ── Scroll ───────────────────────────────────────────────────────────
        function scrollBottom() {
            messagesEl.scrollTop = messagesEl.scrollHeight;
        }

        // ── Add message bubble ────────────────────────────────────────────────
        function addBubble(role, htmlContent, isError) {
            if (welcomeDiv) welcomeDiv.style.display = "none";
            const div = document.createElement("div");
            div.className = "sa-chat-msg sa-chat-msg--" + role;
            div.innerHTML = `
              <div class="sa-chat-msg__avatar">${role === "assistant" ? "🤖" : "👤"}</div>
              <div class="sa-chat-msg__body">
                <div class="sa-chat-msg__bubble${isError ? " sa-chat-msg__bubble--error" : ""}">${htmlContent}</div>
                <span class="sa-chat-msg__time">${nowTime()}</span>
              </div>`;
            messagesEl.appendChild(div);
            scrollBottom();
            return div;
        }

        // ── Typing indicator ──────────────────────────────────────────────────
        function showTyping() {
            if (welcomeDiv) welcomeDiv.style.display = "none";
            const div = document.createElement("div");
            div.className = "sa-chat-msg sa-chat-msg--assistant sa-chat-typing";
            div.id = "sa-typing";
            div.innerHTML = `
              <div class="sa-chat-msg__avatar">🤖</div>
              <div class="sa-chat-msg__body">
                <div class="sa-chat-msg__bubble sa-typing-dots">
                  <span></span><span></span><span></span>
                </div>
              </div>`;
            messagesEl.appendChild(div);
            scrollBottom();
        }

        function hideTyping() {
            const t = messagesEl.querySelector("#sa-typing");
            if (t) t.remove();
        }

        // ── Send ──────────────────────────────────────────────────────────────
        async function sendMessage(text) {
            if (isLoading || !text) return;
            isLoading = true;
            sendBtn.disabled = true;
            inputEl.value = "";
            inputEl.style.height = "auto";

            addBubble("user", escHtml(text));
            showTyping();

            const historySnap = history.slice(-10);

            try {
                const result = await rpc("/ai_chatbot/chat", {
                    message: text,
                    history: historySnap,
                    session_id: sessionId,
                });

                hideTyping();

                if (result && result.response) {
                    addBubble("assistant", renderMarkdown(result.response));
                    history.push({ role: "user", content: text });
                    history.push({ role: "assistant", content: result.response });
                    if (history.length > 20) history = history.slice(-20);
                } else {
                    const errMsg = result?.error || "No response from AI.";
                    addBubble("assistant", escHtml(errMsg), true);
                }
            } catch (err) {
                hideTyping();
                addBubble("assistant", escHtml("Could not reach the AI service. Please try again."), true);
                console.error("[ai_chatbot]", err);
            } finally {
                isLoading = false;
                sendBtn.disabled = false;
                inputEl.focus();
            }
        }
    }

    // ── Boot ──────────────────────────────────────────────────────────────────
    function boot() {
        const rootDiv = document.getElementById("sa-ai-chatbot-root");
        if (!rootDiv) return;
        initChatbot(rootDiv);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot);
    } else {
        boot();
    }
})();
