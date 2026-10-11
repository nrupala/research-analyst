/* Research Analyst theme boot + toggle — Ajna (third eye) chakra system.
 *
 * Modes: dark (default) / bright / night. The choice persists in
 * localStorage under 'ra-theme'. With no saved choice, the OS
 * prefers-color-scheme is honored (light -> bright); otherwise dark.
 *
 * This script loads synchronously in <head>, before the stylesheet, so the
 * data-theme attribute is set before first paint (no theme flash).
 *
 * SPDX-License-Identifier: Apache-2.0
 */
(function () {
    'use strict';

    var KEY = 'ra-theme';
    var MODES = ['dark', 'bright', 'night'];
    var THEME_COLORS = { dark: '#0f172a', bright: '#f4f6fc', night: '#14100b' };

    function preferred() {
        try {
            var saved = window.localStorage.getItem(KEY);
            if (saved && MODES.indexOf(saved) !== -1) return saved;
        } catch (e) { /* storage unavailable — fall through */ }
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) {
            return 'bright';
        }
        return 'dark';
    }

    function reflect(mode) {
        var toggles = document.querySelectorAll('.theme-toggle button');
        for (var i = 0; i < toggles.length; i++) {
            toggles[i].setAttribute('aria-pressed', toggles[i].getAttribute('data-mode') === mode ? 'true' : 'false');
        }
        var meta = document.querySelector('meta[name="theme-color"]');
        if (meta && THEME_COLORS[mode]) meta.setAttribute('content', THEME_COLORS[mode]);
    }

    function apply(mode) {
        if (MODES.indexOf(mode) === -1) mode = 'dark';
        document.documentElement.setAttribute('data-theme', mode);
        try { window.localStorage.setItem(KEY, mode); } catch (e) { /* ignore */ }
        reflect(mode);
    }

    // Boot immediately — no saved choice yet means reflect() still marks the toggle.
    apply(preferred());

    function wire() {
        var toggles = document.querySelectorAll('.theme-toggle button');
        for (var i = 0; i < toggles.length; i++) {
            (function (btn) {
                btn.addEventListener('click', function () {
                    apply(btn.getAttribute('data-mode'));
                });
            })(toggles[i]);
        }
        reflect(document.documentElement.getAttribute('data-theme') || 'dark');
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', wire);
    } else {
        wire();
    }
})();
