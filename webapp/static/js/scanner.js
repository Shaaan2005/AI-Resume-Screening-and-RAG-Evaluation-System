/* Scanner motion layer, shared by every redesigned page.
   - Lenis smooth scroll, driven by gsap.ticker (autoRaf off), ScrollTrigger.update on every scroll
   - GSAP + ScrollTrigger + SplitText for scroll and text animation
   - Motion (window.Motion: animate / inView / hover) for small UI interactions
   With prefers-reduced-motion nothing here runs: the HTML/CSS is already the finished page. */
(function () {
    'use strict';
    var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var hasGsap = !!(window.gsap && window.ScrollTrigger);
    var M = window.Motion || null;
    var S = window.Scanner = { reduce: reduce || !hasGsap, lenis: null, ready: null };

    function navOffset() {
        return -(document.querySelector('.nav') ? document.querySelector('.nav').offsetHeight + 24 : 24);
    }

    // In-page links (#analyze, #search …): smooth scroll, then move keyboard focus to the target
    document.addEventListener('click', function (e) {
        var a = e.target.closest && e.target.closest('a[href^="#"]');
        if (!a || a.getAttribute('href').length < 2) return;
        var target = document.getElementById(a.getAttribute('href').slice(1));
        if (!target) return;
        e.preventDefault();
        var focusTarget = function () {
            if (!target.hasAttribute('tabindex')) target.setAttribute('tabindex', '-1');
            target.focus({ preventScroll: true });
        };
        if (S.lenis) S.lenis.scrollTo(target, { offset: navOffset(), duration: 1.3, onComplete: focusTarget });
        else { target.scrollIntoView({ block: 'start' }); window.scrollBy(0, navOffset()); focusTarget(); }
        history.replaceState(null, '', a.getAttribute('href'));
    });

    if (S.reduce) { S.ready = Promise.resolve(); return; }

    gsap.registerPlugin(ScrollTrigger);
    if (window.SplitText) gsap.registerPlugin(SplitText);

    // ---- Lenis, on GSAP's clock -------------------------------------------------
    if (window.Lenis) {
        var lenis = S.lenis = new Lenis({ autoRaf: false, duration: 1.15, smoothWheel: true,
            easing: function (t) { return Math.min(1, 1.001 - Math.pow(2, -10 * t)); } });
        lenis.on('scroll', ScrollTrigger.update);
        gsap.ticker.add(function (time) { lenis.raf(time * 1000); });
        gsap.ticker.lagSmoothing(0);
    }

    // Split text measures glyphs, so wait for the web fonts (capped, in case they never come)
    S.ready = Promise.race([
        document.fonts ? document.fonts.ready : Promise.resolve(),
        new Promise(function (r) { setTimeout(r, 1500); })
    ]);

    // ---- Section titles: words rise out of a mask (React Bits "SplitText") -------
    S.revealTitles = function (scope) {
        if (!window.SplitText) return;
        (scope || document).querySelectorAll('.reveal-title').forEach(function (el) {
            SplitText.create(el, {
                type: 'words', mask: 'words', autoSplit: true,
                onSplit: function (self) {
                    return gsap.from(self.words, {
                        yPercent: 110, opacity: 0, duration: 1, ease: 'expo.out', stagger: 0.06,
                        scrollTrigger: { trigger: el, start: 'top 88%', once: true }
                    });
                }
            });
        });
    };

    // ---- Blocks fade up as they enter ---------------------------------------------
    S.revealBlocks = function (selector, opts) {
        var els = gsap.utils.toArray(selector);
        if (!els.length) return;
        gsap.set(els, { opacity: 0, y: 36 });
        ScrollTrigger.batch(els, {
            start: 'top 90%', once: true,
            onEnter: function (batch) {
                gsap.to(batch, Object.assign({ opacity: 1, y: 0, duration: 0.9, ease: 'expo.out', stagger: 0.09,
                    clearProps: 'transform' }, opts || {}));
            }
        });
    };

    // ---- Motion: magnetic, springy buttons ----------------------------------------
    S.magnetic = function (selector) {
        if (!M) return;
        var fine = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
        document.querySelectorAll(selector).forEach(function (btn) {
            var spring = { type: 'spring', stiffness: 320, damping: 22, mass: 0.6 };
            if (fine) {
                M.hover(btn, function () {
                    var move = function (e) {
                        var r = btn.getBoundingClientRect();
                        var dx = (e.clientX - (r.left + r.width / 2)) / r.width;
                        var dy = (e.clientY - (r.top + r.height / 2)) / r.height;
                        M.animate(btn, { x: dx * 8, y: dy * 6, scale: btn.disabled ? 1 : 1.03 }, spring);
                    };
                    btn.addEventListener('pointermove', move);
                    return function () {
                        btn.removeEventListener('pointermove', move);
                        M.animate(btn, { x: 0, y: 0, scale: 1 }, spring);
                    };
                });
            }
            btn.addEventListener('pointerdown', function () { if (!btn.disabled) M.animate(btn, { scale: 0.96 }, spring); });
            btn.addEventListener('pointerup', function () { M.animate(btn, { scale: fine ? 1.03 : 1 }, spring); });
            btn.addEventListener('pointercancel', function () { M.animate(btn, { scale: 1 }, spring); });
        });
    };

    // ---- Spotlight cards: a glow follows the pointer (transform only) --------------
    S.spotlight = function (selector) {
        if (!window.matchMedia('(hover: hover)').matches) return;
        document.querySelectorAll(selector).forEach(function (card) {
            var spot = document.createElement('span');
            spot.className = 'spot';
            spot.setAttribute('aria-hidden', 'true');
            card.prepend(spot);
            var setX = gsap.quickTo(spot, 'x', { duration: 0.5, ease: 'power3' });
            var setY = gsap.quickTo(spot, 'y', { duration: 0.5, ease: 'power3' });
            card.addEventListener('pointermove', function (e) {
                var r = card.getBoundingClientRect();
                setX(e.clientX - r.left); setY(e.clientY - r.top);
            });
        });
    };

    // ---- Motion: numbers count up when they scroll into view ----------------------
    // <b data-count="1234">1234</b>: the real number is in the HTML; we only replay it.
    // Decimals follow the server's number ("62.56" counts with 2, "242" with 0).
    S.countTo = function (el, opts) {
        if (!M) return null;
        var raw = el.getAttribute('data-count');
        var end = parseFloat(raw);
        if (!isFinite(end)) return null;
        var decimals = raw.indexOf('.') >= 0 ? raw.split('.')[1].length : 0;
        var fmt = function (v) { return Number(v).toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals }); };
        el.textContent = fmt(0);
        return M.animate(0, end, Object.assign({ duration: 1.6, ease: [0.16, 1, 0.3, 1],
            onUpdate: function (v) { el.textContent = fmt(v); } }, opts || {}));
    };
    S.counters = function (selector) {
        if (!M) return;
        document.querySelectorAll(selector).forEach(function (el) {
            if (!isFinite(parseFloat(el.getAttribute('data-count')))) return;
            el.textContent = '0';
            M.inView(el, function () { S.countTo(el); }, { amount: 0.6 });
        });
    };

    // ---- Ambient glow drifts slowly ------------------------------------------------
    S.drift = function () {
        var g = document.querySelector('.glow');
        if (g) gsap.to(g, { x: '-12vmax', y: '10vmax', duration: 14, ease: 'sine.inOut', yoyo: true, repeat: -1 });
    };

    // Layout can shift once fonts land; re-measure every trigger then
    S.ready.then(function () { ScrollTrigger.refresh(); });
})();
