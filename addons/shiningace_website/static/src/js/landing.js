// Shiningace Landing Page — JS

document.addEventListener('DOMContentLoaded', function () {

    // ── Mobile hamburger menu ─────────────────────────────────────────────
    var hamburger  = document.getElementById('sa-hamburger');
    var mobileMenu = document.getElementById('sa-mobile-menu');
    if (hamburger && mobileMenu) {
        hamburger.addEventListener('click', function () {
            mobileMenu.classList.toggle('is-open');
            hamburger.classList.toggle('is-open');
        });
        // Close menu when a link inside it is clicked
        mobileMenu.querySelectorAll('a').forEach(function (link) {
            link.addEventListener('click', function () {
                mobileMenu.classList.remove('is-open');
                hamburger.classList.remove('is-open');
            });
        });
    }

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

