// Shiningace Landing Page — JS

document.addEventListener('DOMContentLoaded', function () {

    // ── Pill selection via event delegation ───────────────────────────────
    document.querySelectorAll('.sa-chat__pills').forEach(function (group) {
        group.addEventListener('click', function (e) {
            var pill = e.target.closest('.sa-pill');
            if (!pill) return;
            group.querySelectorAll('.sa-pill').forEach(function (p) {
                p.classList.remove('sa-pill--active');
            });
            pill.classList.add('sa-pill--active');
        });
    });

    // ── Chat input send on Enter ──────────────────────────────────────────
    var chatInput = document.querySelector('.sa-chat__input');
    var sendBtn   = document.querySelector('.sa-chat__send');
    if (chatInput && sendBtn) {
        chatInput.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' && chatInput.value.trim()) {
                e.preventDefault();
                chatInput.value = '';
            }
        });
        sendBtn.addEventListener('click', function () {
            chatInput.value = '';
            chatInput.focus();
        });
    }
});

