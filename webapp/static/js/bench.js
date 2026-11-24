/* Benchmark motion: title reveal, KPI numbers count up (Motion) while gauges fill,
   nDCG bars grow and table rows reveal as you scroll. Reduced motion: nothing runs. */
(function () {
    'use strict';
    var S = window.Scanner;
    var html = document.documentElement;
    if (!S || S.reduce) { html.classList.remove('motion'); return; }
    S.started = true;

    function intro() {
        gsap.set('[data-intro]', { autoAlpha: 1 });
        html.classList.remove('motion');
        var tl = gsap.timeline({ defaults: { ease: 'expo.out' } });
        var t = document.querySelector('.bench-title');
        if (t && window.SplitText) {
            var split = SplitText.create(t, { type: 'chars,words', mask: 'words' });
            tl.from(split.chars, { yPercent: 110, duration: 1, stagger: 0.025,
                onComplete: function () { split.revert(); } }, 0.05);
        }
        tl.from('.crumbs', { opacity: 0, y: -10, duration: 0.6 }, 0)
          .from('.bench-head .eyebrow, .bench-sub', { opacity: 0, y: 14, duration: 0.8, stagger: 0.08 }, 0.3);
    }

    function grow(selector, start) {
        document.querySelectorAll(selector).forEach(function (bar) {
            gsap.from(bar, { scaleX: 0, duration: 1.5, ease: 'power3.out',
                scrollTrigger: { trigger: bar, start: start || 'top 92%', once: true } });
        });
    }

    S.ready.then(function () {
        intro();
        S.counters('.kpi-value [data-count]');
        grow('.gauge i');
        grow('.ndcg-bar i');
        S.revealTitles();
        S.revealBlocks('.reveal');
        S.revealBlocks('.q-row', { stagger: 0.03, duration: 0.6 });
        S.spotlight('.kpi');
        S.magnetic('.btn');
        S.drift();
        ScrollTrigger.refresh();
    });
})();
