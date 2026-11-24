/* Result page motion.
   Intro: the score ring fills while the number counts up (Motion), then the verdict is stamped.
   On scroll: sub-scores count, matched skills fly into place one by one, ranking rows reveal.
   Reduced motion: nothing runs; the HTML is already the finished result. */
(function () {
    'use strict';
    var S = window.Scanner;
    var html = document.documentElement;
    if (!S || S.reduce) { html.classList.remove('motion'); return; }
    S.started = true;

    function intro() {
        var tl = gsap.timeline({ defaults: { ease: 'expo.out' } });
        gsap.set('[data-intro]', { autoAlpha: 1 });
        html.classList.remove('motion');

        var name = document.querySelector('.file-name');
        if (name && window.SplitText) {
            var split = SplitText.create(name, { type: 'words,chars', mask: 'words' });
            tl.from(split.chars, { yPercent: 110, duration: 0.9, stagger: 0.018,
                onComplete: function () { split.revert(); } }, 0.05);
        }
        tl.from('.crumbs', { opacity: 0, y: -10, duration: 0.6 }, 0)
          .from('.file-meta, .file-head .eyebrow', { opacity: 0, y: 14, duration: 0.8 }, 0.15);

        var panel = document.querySelector('.verdict-panel');
        if (!panel) return tl;                      // error page: no verdict
        tl.from(panel, { opacity: 0, y: 40, duration: 1 }, 0.2);

        // Ring + counter, in step
        var fill = panel.querySelector('.ring-fill');
        var circ = parseFloat(fill.getAttribute('stroke-dasharray'));
        var target = parseFloat(fill.getAttribute('data-offset'));
        tl.fromTo(fill, { attr: { 'stroke-dashoffset': circ } },
            { attr: { 'stroke-dashoffset': target }, duration: 1.8, ease: 'power3.out' }, 0.45);
        tl.call(function () { S.countTo(panel.querySelector('.ring-num [data-count]'), { duration: 1.8, ease: [0.33, 1, 0.68, 1] }); }, null, 0.45);
        panel.querySelector('.ring-num [data-count]').textContent = '0';
        tl.from(panel.querySelectorAll('.ring-tick'), { opacity: 0, duration: 0.4, stagger: 0.1 }, 1.2);

        // Meter fills toward the score, ticks mark the job's cutoffs
        var meterFill = panel.querySelector('.meter-fill');
        if (meterFill) tl.from(meterFill, { scaleX: 0, duration: 1.6, ease: 'power3.out' }, 0.6);
        tl.from(panel.querySelectorAll('.meter .tick, .meter-legend, .verdict-note, .verdict-body .eyebrow'),
            { opacity: 0, duration: 0.6, stagger: 0.05 }, 1.0);

        // The verdict is stamped on, and the panel takes the hit
        var stamp = panel.querySelector('.stamp-big');
        tl.fromTo(stamp, { opacity: 0, scale: 2.4, rotation: -16 },
            { opacity: 1, scale: 1, rotation: -4, duration: 0.5, ease: 'back.out(2.2)' }, 2.0)
          .fromTo(panel, { x: -5 }, { x: 0, duration: 0.6, ease: 'elastic.out(1, 0.25)', clearProps: 'transform' }, 2.32)
          .from('.percentile', { opacity: 0, x: -12, duration: 0.6 }, 2.35);
        return tl;
    }

    // Matched skills fly in from scattered positions, one by one
    function flySkills() {
        document.querySelectorAll('[data-fly]').forEach(function (ul, n) {
            var items = ul.querySelectorAll('li');
            gsap.set(items, { opacity: 0 });
            ScrollTrigger.create({
                trigger: ul, start: 'top 88%', once: true,
                onEnter: function () {
                    gsap.fromTo(items, {
                        opacity: 0, scale: 0.4,
                        x: function () { return gsap.utils.random(-120, 120); },
                        y: function () { return gsap.utils.random(50, 120); },
                        rotation: function () { return gsap.utils.random(-25, 25); }
                    }, {
                        opacity: 1, scale: 1, x: 0, y: 0, rotation: 0, duration: 0.8, ease: 'back.out(1.5)',
                        stagger: 0.07, delay: n * 0.25, clearProps: 'transform'
                    });
                }
            });
        });
    }

    function subScores() {
        document.querySelectorAll('.sub-card .bar i').forEach(function (bar) {
            gsap.from(bar, { scaleX: 0, duration: 1.6, ease: 'power3.out',
                scrollTrigger: { trigger: bar, start: 'top 92%', once: true } });
        });
        S.counters('.sub-card [data-count]');
    }

    S.ready.then(function () {
        intro();
        subScores();
        flySkills();
        S.revealTitles();
        S.revealBlocks('.reveal');
        S.revealBlocks('.rank-row', { stagger: 0.05, duration: 0.7 });
        S.magnetic('.btn');
        S.spotlight('.spotlight');
        S.drift();
        ScrollTrigger.refresh();
    });
})();
