/* Home page motion: the scanner hero and the section reveals.
   Desktop: the hero pins and the scan is scrubbed by scroll.
   Phone:   no pinning; the scan plays once when the resume comes into view.
   Reduced motion: nothing runs; the HTML already shows the finished scan. */
(function () {
    'use strict';
    var S = window.Scanner;
    var html = document.documentElement;
    if (!S || S.reduce) { html.classList.remove('motion'); return; }
    S.started = true;

    var GLYPHS = '#%&*+/<=>?@$01';   // ASCII only: keeps the monospace width, so ghosts wrap like the text
    function scramble(str) {
        var out = '';
        for (var i = 0; i < str.length; i++) {
            out += str[i] === ' ' ? ' ' : GLYPHS[(Math.random() * GLYPHS.length) | 0];
        }
        return out;
    }

    // ---- Intro: headline letters rise in (React Bits "SplitText"), then the rest ----
    function intro() {
        var title = document.querySelector('.hero-title');
        var tl = gsap.timeline({ defaults: { ease: 'expo.out' } });
        gsap.set('[data-intro]', { autoAlpha: 1 });
        if (title && window.SplitText) {
            var split = SplitText.create(title, { type: 'chars,words', mask: 'words' });
            tl.from(split.chars, { yPercent: 115, duration: 1.1, stagger: 0.028,
                onComplete: function () { split.revert(); } }, 0);
        }
        tl.from('.hero-copy .eyebrow', { opacity: 0, y: 12, duration: 0.8 }, 0.1)
          .from('.hero-sub, .hero-ctas, .hero-facts', { opacity: 0, y: 24, duration: 1, stagger: 0.08 }, 0.45)
          .from('.scanner', { opacity: 0, y: 40, rotate: 2, duration: 1.3 }, 0.3);
        html.classList.remove('motion');
        return tl;
    }

    // ---- The scan ------------------------------------------------------------------
    function buildScan(root, onDesktop) {
        var paper = root.querySelector('.paper');
        var beam = root.querySelector('.beam');
        var stamp = root.querySelector('.stamp');
        var lines = Array.prototype.slice.call(root.querySelectorAll('.line'));
        var scoreNum = root.querySelector('.score-num [data-score]');
        var bar = root.querySelector('.score-bar i');
        var countEl = root.querySelector('[data-matched]');
        var finalScore = parseInt(scoreNum.getAttribute('data-score'), 10);
        var totalSkills = root.querySelectorAll('.tray .chip').length;
        var stampShown = false;

        // Ghost layer per line: same characters, scrambled
        lines.forEach(function (line) {
            var real = line.querySelector('.real');
            var ghost = document.createElement('span');
            ghost.className = 'ghost';
            line._text = real.textContent;
            ghost.textContent = scramble(line._text);
            line.appendChild(ghost);
            line._ghost = ghost;
        });
        root.classList.add('is-scanning');
        gsap.set('.tray .chip', { opacity: 0, scale: 0.8 });
        gsap.set(stamp, { opacity: 0, scale: 1.6 });
        gsap.set(bar, { scaleX: 0 });
        scoreNum.textContent = '0';
        countEl.textContent = '0';

        function matched() { return root.querySelectorAll('.line.lit .mark').length; }

        // React Bits "DecryptedText": resolves left to right as the beam crosses
        function decrypt(line) {
            if (line._lit) return;
            line._lit = true;
            if (line._tw) line._tw.kill();
            var text = line._text, o = { p: 0 };
            line._tw = gsap.to(o, {
                p: 1, duration: 0.45, ease: 'none',
                onUpdate: function () {
                    var k = Math.floor(o.p * text.length);
                    line._ghost.textContent = text.slice(0, k) + scramble(text.slice(k));
                },
                onComplete: function () {
                    line.classList.add('lit');
                    flySkills(line);
                }
            });
        }
        function encrypt(line) {
            if (!line._lit) return;
            line._lit = false;
            if (line._tw) line._tw.kill();
            line.classList.remove('lit');
            line._ghost.textContent = scramble(line._text);
            line.querySelectorAll('.mark').forEach(function (m) {
                var chip = root.querySelector('.tray .chip[data-skill="' + m.getAttribute('data-skill') + '"]');
                gsap.to(chip, { opacity: 0, scale: 0.8, x: 0, y: 0, duration: 0.25, overwrite: true });
            });
            countEl.textContent = matched();
        }
        // Matched skills lift off the page and fly into the tray (FLIP, transform only)
        function flySkills(line) {
            line.querySelectorAll('.mark').forEach(function (m, i) {
                var chip = root.querySelector('.tray .chip[data-skill="' + m.getAttribute('data-skill') + '"]');
                if (!chip) return;
                gsap.set(chip, { x: 0, y: 0, scale: 1 });
                var a = m.getBoundingClientRect(), b = chip.getBoundingClientRect();
                gsap.fromTo(chip,
                    { x: (a.left + a.width / 2) - (b.left + b.width / 2), y: (a.top + a.height / 2) - (b.top + b.height / 2), scale: 0.7, opacity: 0.4 },
                    { x: 0, y: 0, scale: 1, opacity: 1, duration: 0.9, delay: i * 0.08, ease: 'expo.out', overwrite: true });
            });
            countEl.textContent = matched();
        }
        function showStamp(on) {
            if (on === stampShown) return;
            stampShown = on;
            gsap.to(stamp, on ? { opacity: 1, scale: 1, duration: 0.5, ease: 'back.out(2.2)', overwrite: true }
                              : { opacity: 0, scale: 1.6, duration: 0.2, overwrite: true });
        }

        var tl = gsap.timeline({
            paused: !onDesktop,
            onUpdate: function () {
                var p = Math.min(1, tl.time() / 1);
                var beamY = p * paper.clientHeight;
                lines.forEach(function (line) {
                    var mid = line.offsetTop + line.offsetHeight / 2;
                    if (beamY >= mid) decrypt(line); else encrypt(line);
                });
                scoreNum.textContent = Math.round(p * finalScore);
                gsap.set(bar, { scaleX: p * finalScore / 100 });
                showStamp(p >= 0.985);
            }
        });
        tl.fromTo(beam, { y: 0 }, { y: function () { return paper.clientHeight - 2; }, duration: 1, ease: 'none' })
          .to(beam, { opacity: 0, duration: 0.08 })
          .to('.scroll-cue', { opacity: 0, duration: 0.2 }, 0);

        if (onDesktop) {
            document.querySelector('.scan-hero').classList.add('pinned');
            ScrollTrigger.create({
                trigger: '.scan-hero', start: 'top top', end: '+=130%',
                pin: true, scrub: 0.6, animation: tl, invalidateOnRefresh: true
            });
        } else {
            tl.timeScale(1 / 3.2);
            ScrollTrigger.create({ trigger: paper, start: 'top 75%', once: true, onEnter: function () { tl.play(); } });
        }

        // Undo everything if the breakpoint changes (gsap.matchMedia reverts the tweens)
        return function () {
            document.querySelector('.scan-hero').classList.remove('pinned');
            root.classList.remove('is-scanning');
            lines.forEach(function (line) {
                if (line._tw) line._tw.kill();
                line._lit = false;
                line.classList.remove('lit');
                if (line._ghost) line._ghost.remove();
            });
            scoreNum.textContent = finalScore;
            countEl.textContent = totalSkills;
        };
    }

    // ---- How it works: the pipeline line fills as you scroll -------------------------
    function pipeline() {
        var fill = document.querySelector('.pipe-fill');
        if (!fill) return;
        var vertical = window.matchMedia('(max-width: 899px)').matches;
        gsap.fromTo(fill, vertical ? { scaleY: 0 } : { scaleX: 0 }, Object.assign(vertical ? { scaleY: 1 } : { scaleX: 1 }, {
            ease: 'none', scrollTrigger: { trigger: '.pipeline', start: 'top 80%', end: 'bottom 60%', scrub: 0.5 }
        }));
    }

    S.ready.then(function () {
        intro();
        var root = document.querySelector('[data-scanner]');
        if (root) {
            gsap.matchMedia().add({ desk: '(min-width: 900px)', mob: '(max-width: 899px)' }, function (ctx) {
                return buildScan(root, ctx.conditions.desk);
            });
        }
        S.revealTitles();
        S.revealBlocks('.reveal');
        S.magnetic('.btn');
        S.spotlight('.spotlight');
        S.counters('[data-count]');
        S.drift();
        pipeline();
        ScrollTrigger.refresh();
    });
})();
