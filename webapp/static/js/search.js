/* Search results motion: the query headline reveals word by word, candidate cards rise in
   as you scroll, and each card's score counts up (Motion) while its bar fills.
   Reduced motion: nothing runs; the HTML is the finished list. */
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
        var q = document.querySelector('.query');
        if (q && window.SplitText) {
            var split = SplitText.create(q, { type: 'words', mask: 'words' });
            tl.from(split.words, { yPercent: 110, duration: 1, stagger: 0.04,
                onComplete: function () { split.revert(); } }, 0.1);
        }
        tl.from('.crumbs', { opacity: 0, y: -10, duration: 0.6 }, 0)
          .from('.query-meta > *', { opacity: 0, y: 12, duration: 0.7, stagger: 0.06 }, 0.05)
          .from('.notice, .alt-depts', { opacity: 0, y: 16, duration: 0.8, stagger: 0.08 }, 0.5);
    }

    // Cards tilt up into place in batches; each one then counts its score
    function cards() {
        var items = gsap.utils.toArray('.cand');
        if (!items.length) return;
        gsap.set(items, { opacity: 0, y: 60, rotationX: -14, transformPerspective: 900, transformOrigin: '50% 0%' });
        items.forEach(function (c) {
            var bar = c.querySelector('.bar i');
            if (bar) c._scale = gsap.getProperty(bar, 'scaleX');
            if (bar) gsap.set(bar, { scaleX: 0 });
            var num = c.querySelector('[data-count]');
            if (num && isFinite(parseFloat(num.getAttribute('data-count')))) num.textContent = '0';
        });
        ScrollTrigger.batch(items, {
            start: 'top 92%', once: true,
            onEnter: function (batch) {
                gsap.to(batch, { opacity: 1, y: 0, rotationX: 0, duration: 0.9, ease: 'expo.out', stagger: 0.08, clearProps: 'transform' });
                batch.forEach(function (c, i) {
                    var bar = c.querySelector('.bar i');
                    if (bar) gsap.to(bar, { scaleX: c._scale, duration: 1.3, ease: 'power3.out', delay: 0.15 + i * 0.08 });
                    var num = c.querySelector('[data-count]');
                    if (num) S.countTo(num, { duration: 1.3, delay: 0.15 + i * 0.08 });
                });
            }
        });
    }

    S.ready.then(function () {
        intro();
        cards();
        S.revealTitles();
        S.revealBlocks('.reveal');
        S.magnetic('.btn');
        S.drift();
        ScrollTrigger.refresh();
    });
})();
