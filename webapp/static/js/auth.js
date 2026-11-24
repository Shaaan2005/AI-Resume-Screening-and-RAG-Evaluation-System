/* Login / Register motion. A calm background (React Bits "Squares": a drifting grid whose
   cells softly light up, plus a slow scan beam), a word-by-word headline, and inputs that
   respond to focus. Reduced motion: a still grid with a few lit cells, no movement. */
(function () {
    'use strict';
    var S = window.Scanner;
    var html = document.documentElement;
    var grid = document.querySelector('.auth-bg .grid');
    var CELL = 64;

    function makeCells(n) {
        if (!grid) return [];
        var cols = Math.ceil((window.innerWidth + CELL * 2) / CELL);
        var rows = Math.ceil((window.innerHeight + CELL * 2) / CELL);
        var out = [];
        for (var i = 0; i < n; i++) {
            var c = document.createElement('span');
            c.className = 'cell';
            c.style.left = (1 + ((Math.random() * cols) | 0) * CELL) + 'px';
            c.style.top = (1 + ((Math.random() * rows) | 0) * CELL) + 'px';
            grid.appendChild(c);
            out.push(c);
        }
        return out;
    }

    if (!S || S.reduce) {
        makeCells(10).forEach(function (c) { c.classList.add('lit'); });
        html.classList.remove('motion');
        return;
    }
    S.started = true;

    function background() {
        var small = window.innerWidth < 900;
        makeCells(small ? 10 : 22).forEach(function (c) {
            gsap.to(c, {
                opacity: function () { return gsap.utils.random(0.05, 0.2); },
                duration: gsap.utils.random(1.8, 3.5), ease: 'sine.inOut',
                repeat: -1, yoyo: true, delay: gsap.utils.random(0, 5), repeatDelay: gsap.utils.random(0.5, 4)
            });
        });
        // One tile of drift loops seamlessly (the grid is one tile larger than the screen)
        gsap.to(grid, { x: CELL, y: CELL, duration: 40, ease: 'none', repeat: -1 });
        gsap.fromTo('.auth-bg .vbeam', { y: -160 }, {
            y: function () { return window.innerHeight + 20; },
            duration: 7, ease: 'sine.inOut', repeat: -1, repeatDelay: 2.5, delay: 0.8
        });
    }

    function intro() {
        gsap.set('[data-intro]', { autoAlpha: 1 });
        html.classList.remove('motion');
        var tl = gsap.timeline({ defaults: { ease: 'expo.out' } });
        var title = document.querySelector('.auth-title');
        if (title && window.SplitText) {
            var split = SplitText.create(title, { type: 'words', mask: 'words' });
            tl.from(split.words, { yPercent: 110, duration: 1.1, stagger: 0.06,
                onComplete: function () { split.revert(); } }, 0.1);
        }
        tl.from('.auth-story .eyebrow, .auth-story > p', { opacity: 0, y: 14, duration: 0.8, stagger: 0.08 }, 0.2)
          .from('.signals li', { opacity: 0, x: -16, duration: 0.7, stagger: 0.08 }, 0.5)
          .from('.auth-card', { opacity: 0, y: 30, duration: 1.1 }, 0.15)
          .from('.auth-card .afield, .auth-card .btn-block, .auth-foot', { opacity: 0, y: 12, duration: 0.7, stagger: 0.06 }, 0.4);
        // Wrong password / taken username: the card shakes once
        if (document.querySelector('.form-error')) {
            tl.fromTo('.auth-card', { x: -12 }, { x: 0, duration: 0.9, ease: 'elastic.out(1, 0.25)', clearProps: 'x' }, 0.9);
        }
    }

    // Motion: fields lift slightly on focus, with a spring
    function inputs() {
        var M = window.Motion;
        if (!M) return;
        var spring = { type: 'spring', stiffness: 380, damping: 26 };
        document.querySelectorAll('.afield').forEach(function (f) {
            var control = f.querySelector('.control');
            f.addEventListener('focusin', function () { M.animate(control, { y: -2, scale: 1.01 }, spring); });
            f.addEventListener('focusout', function () { M.animate(control, { y: 0, scale: 1 }, spring); });
        });
        // A rule ticking over gets a small pop
        var rules = document.getElementById('pwRules');
        if (rules) {
            new MutationObserver(function (list) {
                list.forEach(function (m) {
                    if (m.target.classList.contains('ok') && (m.oldValue || '').indexOf('ok') < 0) {
                        M.animate(m.target, { scale: [1, 1.12, 1] }, { duration: 0.35 });
                    }
                });
            }).observe(rules, { subtree: true, attributes: true, attributeFilter: ['class'], attributeOldValue: true });
        }
    }

    S.ready.then(function () {
        background();
        intro();
        inputs();
        S.magnetic('.btn');
    });
})();
