/* Error page: a beam scans the big error code, revealing its lime fill top to bottom, then
   keeps idling slowly. Clip-path is used for the reveal mask; the beam itself moves by transform.
   Reduced motion: the filled code is simply shown. */
(function () {
    'use strict';
    var S = window.Scanner;
    var html = document.documentElement;
    if (!S || S.reduce) { html.classList.remove('motion'); return; }
    S.started = true;

    S.ready.then(function () {
        gsap.set('[data-intro]', { autoAlpha: 1 });
        html.classList.remove('motion');
        var code = document.querySelector('.code');
        var fill = code.querySelector('.fill');
        var beam = code.querySelector('.beam');
        var h = function () { return code.offsetHeight; };

        var tl = gsap.timeline({ defaults: { ease: 'expo.out' } });
        tl.from(code, { opacity: 0, scale: 0.94, duration: 1 }, 0)
          .set(beam, { opacity: 1 }, 0.3)
          .fromTo(fill, { clipPath: 'inset(0 0 100% 0)' }, { clipPath: 'inset(0 0 0% 0)', duration: 1.4, ease: 'power2.inOut' }, 0.3)
          .fromTo(beam, { y: 0 }, { y: h, duration: 1.4, ease: 'power2.inOut' }, 0.3)
          .to(beam, { opacity: 0, duration: 0.3 }, 1.7)
          .from('.err .eyebrow, .err h1, .err p, .err .btn', { opacity: 0, y: 18, duration: 0.9, stagger: 0.08 }, 1.1);

        // Idle: every few seconds the beam passes again, lightly
        gsap.timeline({ repeat: -1, repeatDelay: 3.5, delay: 3 })
            .set(beam, { y: 0, opacity: 0.7 })
            .to(beam, { y: h, duration: 2.2, ease: 'sine.inOut' })
            .to(beam, { opacity: 0, duration: 0.3 });

        S.magnetic('.btn');
        S.drift();
    });
})();
