/* Home page motion.
   1. Hero: a light beam scans a sample resume (pinned + scrubbed on desktop, played once in
      view on phones). Visitors can pick or type a role; the matching sample resume is loaded
      and scanned again. The score is real keyword coverage of that sample (found / wanted).
   2. Story: one resume through the four pipeline stages (pinned + scrubbed on desktop).
   Reduced motion: no animation; the role picker still swaps in the finished result. */
(function () {
    'use strict';
    var S = window.Scanner || { reduce: true };
    var html = document.documentElement;
    var reduce = !!S.reduce;

    // ------------------------------------------------------------------ sample data
    // {Skill} marks a skill the job asks for. Lines stay short so they fit one line on desktop.
    var PROFILES = [
        { role: 'Python Developer', keys: ['python', 'developer', 'backend', 'django', 'flask', 'software', 'engineer', 'programmer'],
          name: 'Ananya Rao', initials: 'AR', line: 'Backend Engineer · Bengaluru · 4 yrs',
          wants: ['Python', 'Flask', 'SQL', 'Machine Learning', 'Docker', 'AWS'],
          sections: [['EXPERIENCE', ['Built {Flask} REST APIs serving 1.2M requests a day', 'Cut report time 70% with {SQL} window functions', 'Shipped a churn model in {Python} and scikit-learn']],
                     ['PROJECTS', ['Resume ranker with {Machine Learning} embeddings', 'Containerised six services with {Docker} and CI']],
                     ['EDUCATION', ['B.Tech Computer Science, VIT Vellore, 2021']]] },
        { role: 'Data Analyst', keys: ['data', 'analyst', 'analytics', 'tableau', 'power bi', 'bi ', 'insight'],
          name: 'Meera Iyer', initials: 'MI', line: 'Data Analyst · Pune · 3 yrs',
          wants: ['SQL', 'Excel', 'Tableau', 'Python', 'Statistics'],
          sections: [['EXPERIENCE', ['Built {Tableau} dashboards for 40 regional managers', 'Automated weekly reports in {Excel} Power Query', 'Wrote {SQL} to reconcile 2M sales rows a month']],
                     ['PROJECTS', ['A/B test readouts using {Statistics} in R', 'Churn study in pandas notebooks']],
                     ['EDUCATION', ['B.Sc Mathematics, Fergusson College, 2022']]] },
        { role: 'Accountant', keys: ['account', 'finance', 'tax', 'audit', 'gst', 'bookkeep', 'ca '],
          name: 'Rahul Mehta', initials: 'RM', line: 'Accountant · Mumbai · 6 yrs',
          wants: ['Tally', 'GST', 'Excel', 'Reconciliation', 'Audit', 'IFRS'],
          sections: [['EXPERIENCE', ['Filed monthly {GST} returns for 30 clients', 'Led bank {Reconciliation} across 12 accounts', 'Kept books in {Tally} ERP for a retail chain']],
                     ['PROJECTS', ['Cut month-end close 3 days with {Excel} macros', 'Prepared files for statutory {Audit} reviews']],
                     ['EDUCATION', ['B.Com, University of Mumbai, 2018']]] },
        { role: 'Chef', keys: ['chef', 'cook', 'kitchen', 'culinary', 'restaurant', 'baker'],
          name: 'Daniel Fernandes', initials: 'DF', line: 'Sous Chef · Goa · 7 yrs',
          wants: ['Menu Planning', 'Food Safety', 'Inventory', 'Pastry', 'Catering'],
          sections: [['EXPERIENCE', ['Owned {Menu Planning} for a 90-cover bistro', 'Kept {Food Safety} audits at 100% for 3 years', 'Cut waste 18% with weekly {Inventory} counts']],
                     ['PROJECTS', ['Ran banquets for weddings up to 400 guests', 'Seasonal tasting menu with local seafood']],
                     ['EDUCATION', ['Diploma in Culinary Arts, IHM Goa, 2016']]] },
        { role: 'Sales Executive', keys: ['sales', 'business development', 'bdm', 'bde', 'account manager', 'cold'],
          name: 'Sara Khan', initials: 'SK', line: 'Sales Executive · Delhi · 2 yrs',
          wants: ['Cold Calling', 'CRM', 'Negotiation', 'B2B', 'Lead Generation'],
          sections: [['EXPERIENCE', ['Booked 25 demos a week from {Cold Calling}', 'Kept the pipeline clean in {CRM} (HubSpot)', 'Grew retail store sales 22% in a year']],
                     ['PROJECTS', ['Ran a festive offer that doubled walk-ins', 'Trained four new hires on product demos']],
                     ['EDUCATION', ['BBA Marketing, Amity University, 2023']]] },
        { role: 'Product Designer', keys: ['design', 'ux', 'ui', 'figma', 'product designer', 'visual'],
          name: 'Ishaan Roy', initials: 'IR', line: 'Product Designer · Hyderabad · 5 yrs',
          wants: ['Figma', 'User Research', 'Prototyping', 'Design Systems', 'Accessibility'],
          sections: [['EXPERIENCE', ['Shipped {Design Systems} library in {Figma}', 'Ran 30 {User Research} interviews a quarter', 'Built {Prototyping} flows for checkout']],
                     ['PROJECTS', ['Redesigned onboarding, +14% activation', 'Audited contrast for {Accessibility} (WCAG AA)']],
                     ['EDUCATION', ['B.Des, NID Ahmedabad, 2019']]] }
    ];

    function slug(s) { return s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''); }
    function esc(s) { return s.replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
    function markup(line) {
        return esc(line).replace(/\{([^}]+)\}/g, function (_, k) { return '<span class="mark" data-skill="' + slug(k) + '">' + k + '</span>'; });
    }
    function found(p) {
        var all = p.sections.map(function (s) { return s[1].join(' '); }).join(' ');
        return p.wants.filter(function (w) { return all.indexOf('{' + w + '}') >= 0; });
    }
    function verdict(score) { return score >= 80 ? ['SHORTLIST', 'green'] : score >= 50 ? ['CONSIDER', 'yellow'] : ['REJECT', 'red']; }
    function findProfile(text) {
        var t = ' ' + text.toLowerCase().trim() + ' ';
        if (!t.trim()) return null;
        for (var i = 0; i < PROFILES.length; i++) {
            if (PROFILES[i].role.toLowerCase() === t.trim()) return PROFILES[i];
        }
        for (i = 0; i < PROFILES.length; i++) {
            if (PROFILES[i].keys.some(function (k) { return t.indexOf(k) >= 0; })) return PROFILES[i];
        }
        return null;
    }

    var root = document.querySelector('[data-scanner]');
    var statusEl = document.getElementById('scanStatus');
    var hint = document.getElementById('tryHint');

    function statusText(p) {
        var f = found(p), score = Math.round(100 * f.length / p.wants.length);
        return 'Sample ' + p.role + ' resume: ' + f.length + ' of ' + p.wants.length + ' skills found, ' + score + '%, ' + verdict(score)[0] + '.';
    }

    // Writes a profile into the illustration, in its finished state
    function render(p) {
        var f = found(p), score = Math.round(100 * f.length / p.wants.length), v = verdict(score);
        root.querySelector('[data-initials]').textContent = p.initials;
        root.querySelector('[data-name]').textContent = p.name;
        root.querySelector('[data-role-line]').textContent = p.line;
        root.querySelector('[data-wants]').textContent = p.wants.join(' · ');
        root.querySelector('[data-body]').innerHTML = p.sections.map(function (sec) {
            return '<div class="paper-sec">' + esc(sec[0]) + '</div>' + sec[1].map(function (l) {
                return '<p class="line"><span class="real">' + markup(l) + '</span></p>';
            }).join('');
        }).join('');
        root.querySelector('[data-tray]').innerHTML = p.wants.map(function (w) {
            return '<span class="chip' + (f.indexOf(w) >= 0 ? '' : ' miss') + '" data-skill="' + slug(w) + '">' + esc(w) + '</span>';
        }).join('');
        var num = root.querySelector('[data-score]');
        num.setAttribute('data-score', score);
        num.textContent = score;
        root.querySelector('.score-bar i').style.transform = 'scaleX(' + (score / 100) + ')';
        root.querySelector('[data-matched]').textContent = f.length;
        root.querySelector('[data-total]').textContent = p.wants.length;
        var stamp = root.querySelector('[data-stamp]');
        stamp.textContent = v[0];
        stamp.className = 'stamp band-' + v[1];
        document.querySelectorAll('.try-chip').forEach(function (c) {
            c.setAttribute('aria-pressed', c.getAttribute('data-role') === p.role);
        });
        statusEl.textContent = statusText(p);
    }

    // ------------------------------------------------------------------ the scan
    var GLYPHS = '#%&*+/<=>?@$01';   // ASCII only: keeps the monospace width, so ghosts wrap like the text
    function scramble(str) {
        var out = '';
        for (var i = 0; i < str.length; i++) out += str[i] === ' ' ? ' ' : GLYPHS[(Math.random() * GLYPHS.length) | 0];
        return out;
    }

    var scanST = null;   // the desktop ScrollTrigger, for replays

    function buildScan(onDesktop) {
        var paper = root.querySelector('.paper');
        var beam = root.querySelector('.beam');
        var stamp = root.querySelector('[data-stamp]');
        var lines = Array.prototype.slice.call(root.querySelectorAll('.line'));
        var scoreNum = root.querySelector('[data-score]');
        var bar = root.querySelector('.score-bar i');
        var countEl = root.querySelector('[data-matched]');
        var finalScore = parseInt(scoreNum.getAttribute('data-score'), 10);
        var finalCount = countEl.textContent;
        var misses = root.querySelectorAll('.tray .chip.miss');
        var stampShown = false;

        lines.forEach(function (line) {
            var ghost = document.createElement('span');
            ghost.className = 'ghost';
            line._text = line.querySelector('.real').textContent;
            ghost.textContent = scramble(line._text);
            line.appendChild(ghost);
            line._ghost = ghost;
        });
        root.classList.add('is-scanning');
        gsap.set(root.querySelectorAll('.tray .chip:not(.miss)'), { opacity: 0, scale: 0.8 });
        gsap.set(misses, { opacity: 0 });
        gsap.set(stamp, { opacity: 0, scale: 1.6 });
        gsap.set(bar, { scaleX: 0 });
        scoreNum.textContent = '0';
        countEl.textContent = '0';

        function matched() { return root.querySelectorAll('.line.lit .mark').length; }
        function chipFor(m) { return root.querySelector('.tray .chip[data-skill="' + m.getAttribute('data-skill') + '"]'); }

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
                onComplete: function () { line.classList.add('lit'); flySkills(line); }
            });
        }
        function encrypt(line) {
            if (!line._lit) return;
            line._lit = false;
            if (line._tw) line._tw.kill();
            line.classList.remove('lit');
            line._ghost.textContent = scramble(line._text);
            line.querySelectorAll('.mark').forEach(function (m) {
                gsap.to(chipFor(m), { opacity: 0, scale: 0.8, x: 0, y: 0, duration: 0.25, overwrite: true });
            });
            countEl.textContent = matched();
        }
        // Matched skills lift off the page and fly into the tray (FLIP, transform only)
        function flySkills(line) {
            line.querySelectorAll('.mark').forEach(function (m, i) {
                var chip = chipFor(m);
                if (!chip) return;
                gsap.set(chip, { x: 0, y: 0, scale: 1 });
                var a = m.getBoundingClientRect(), b = chip.getBoundingClientRect();
                gsap.fromTo(chip,
                    { x: (a.left + a.width / 2) - (b.left + b.width / 2), y: (a.top + a.height / 2) - (b.top + b.height / 2), scale: 0.7, opacity: 0.4 },
                    { x: 0, y: 0, scale: 1, opacity: 1, duration: 0.9, delay: i * 0.08, ease: 'expo.out', overwrite: true });
            });
            countEl.textContent = matched();
        }
        // The verdict lands; skills that were never found show up as missing
        function showStamp(on) {
            if (on === stampShown) return;
            stampShown = on;
            gsap.to(stamp, on ? { opacity: 1, scale: 1, duration: 0.5, ease: 'back.out(2.2)', overwrite: true }
                              : { opacity: 0, scale: 1.6, duration: 0.2, overwrite: true });
            gsap.to(misses, on ? { opacity: 1, duration: 0.4, stagger: 0.08, overwrite: true } : { opacity: 0, duration: 0.2, overwrite: true });
        }

        var tl = gsap.timeline({
            paused: !onDesktop,
            onUpdate: function () {
                var p = Math.min(1, tl.time());
                var beamY = p * paper.clientHeight;
                lines.forEach(function (line) {
                    if (beamY >= line.offsetTop + line.offsetHeight / 2) decrypt(line); else encrypt(line);
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
            scanST = ScrollTrigger.create({
                trigger: '.scan-hero', start: 'top top', end: '+=130%',
                pin: true, scrub: 0.6, animation: tl, invalidateOnRefresh: true,
                // Rebuilt after a role swap, i.e. after the story trigger: measure it first anyway,
                // or the story below is positioned as if the hero had no pinned height.
                refreshPriority: 1
            });
            ScrollTrigger.sort();
        } else {
            tl.timeScale(1 / 3.2);
            ScrollTrigger.create({ trigger: paper, start: 'top 85%', once: true, onEnter: function () { tl.play(); } });
        }

        return function () {
            scanST = null;
            document.querySelector('.scan-hero').classList.remove('pinned');
            root.classList.remove('is-scanning');
            lines.forEach(function (line) {
                if (line._tw) line._tw.kill();
                line._lit = false;
                line.classList.remove('lit');
                if (line._ghost) line._ghost.remove();
            });
            scoreNum.textContent = finalScore;
            countEl.textContent = finalCount;
        };
    }

    var mm = null;
    function startScan() {
        mm = gsap.matchMedia();
        mm.add({ desk: '(min-width: 900px)', mob: '(max-width: 899px)' }, function (ctx) {
            return buildScan(ctx.conditions.desk);
        });
    }

    // Desktop replay: glide through the pinned section so the scrubbed scan plays again
    function replayDesktop() {
        if (!scanST) return;
        var start = scanST.start, end = scanST.end;
        var ease = function (t) { return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; };
        if (S.lenis) {
            S.lenis.scrollTo(start, { immediate: true, force: true });
            requestAnimationFrame(function () { S.lenis.scrollTo(end, { duration: 2.8, easing: ease, force: true }); });
        } else {
            window.scrollTo(0, start);
            window.scrollTo({ top: end, behavior: 'smooth' });
        }
    }

    function load(text) {
        var p = findProfile(text);
        if (!p) {
            hint.textContent = 'No “' + text.trim().slice(0, 18) + '” sample. Try:';
            hint.classList.add('warn');
            statusEl.textContent = 'No sample resume for that role. Try one of the listed roles.';
            if (!reduce) gsap.fromTo('.try-row', { x: -6 }, { x: 0, duration: 0.6, ease: 'elastic.out(1, 0.3)' });
            return;
        }
        hint.textContent = 'Try a role:';
        hint.classList.remove('warn');
        document.getElementById('tryRole').value = p.role;
        if (reduce) { render(p); return; }
        if (mm) mm.revert();
        render(p);
        startScan();
        ScrollTrigger.refresh();
        if (window.matchMedia('(min-width: 900px)').matches) replayDesktop();
    }

    function wireDemo() {
        if (!root) return;
        document.getElementById('tryForm').addEventListener('submit', function (e) {
            e.preventDefault();
            load(document.getElementById('tryRole').value);
        });
        document.querySelectorAll('.try-chip').forEach(function (c) {
            c.addEventListener('click', function () { load(c.getAttribute('data-role')); });
        });
    }

    wireDemo();
    if (reduce || !window.gsap) { html.classList.remove('motion'); return; }
    S.started = true;

    // ------------------------------------------------------------------ intro
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

    // ------------------------------------------------------------------ story
    function story() {
        var stage = document.querySelector('.story-stage');
        if (!stage) return;
        var steps = stage.querySelectorAll('.story-step');
        var list = stage.querySelector('.story-steps');
        var rail = document.createElement('span');
        rail.className = 'story-rail';
        rail.setAttribute('aria-hidden', 'true');
        list.prepend(rail);
        var marks = [0, 1.1, 2.1, 3.2];   // when each stage starts on the timeline

        gsap.matchMedia().add({ desk: '(min-width: 900px)', mob: '(max-width: 899px)' }, function (ctx) {
            var desk = ctx.conditions.desk;
            var tl = gsap.timeline({
                paused: !desk, defaults: { ease: 'power2.out' },
                onUpdate: function () {
                    var t = tl.time(), idx = 0;
                    for (var i = 0; i < marks.length; i++) if (t >= marks[i]) idx = i;
                    steps.forEach(function (s, i) { s.classList.toggle('active', i === idx); s.classList.toggle('done', i < idx); });
                    gsap.set(rail, { scaleY: tl.progress() });
                }
            });
            tl.from('.sv-jd', { opacity: 0, y: 16, duration: 0.5 }, 0)
              .from('.sv-card', { opacity: 0, y: 24, duration: 0.5 }, 0.3)
              .from('.sv-dept', { opacity: 0, scale: 0.6, duration: 0.4, ease: 'back.out(2)' }, 0.6)
              .from('.sv-kw i', { scaleX: 0, duration: 0.35, stagger: 0.2 }, marks[1])
              .from('.sv-kwcount', { opacity: 0, duration: 0.3 }, marks[1] + 0.6)
              .from('.sv-sim i', { scaleX: 0, duration: 0.5, stagger: 0.15 }, marks[2])
              .from('.sv-sim em', { opacity: 0, duration: 0.3, stagger: 0.15 }, marks[2] + 0.1)
              .from('.sv-best', { opacity: 0, scale: 1.04, duration: 0.4 }, marks[2] + 0.7)
              .from('.sv-rank li', { opacity: 0, x: 24, duration: 0.4, stagger: 0.12 }, marks[3])
              .to({}, { duration: 0.3 });   // hold the finished state for a moment

            if (desk) {
                stage.classList.add('stepping');
                ScrollTrigger.create({ trigger: stage, start: 'center center', end: '+=220%', pin: true, scrub: 0.6, animation: tl });
            } else {
                gsap.set(rail, { scaleY: 1 });
                ScrollTrigger.create({ trigger: '.story-visual', start: 'top 75%', once: true, onEnter: function () { tl.play(); } });
            }
            return function () { stage.classList.remove('stepping'); };
        });
    }

    S.ready.then(function () {
        intro();
        if (root) startScan();
        story();
        S.revealTitles();
        S.revealBlocks('.reveal');
        S.magnetic('.btn');
        S.spotlight('.spotlight');
        S.counters('[data-count]');
        S.drift();
        ScrollTrigger.refresh();
        // Links like /#analyze: the pinned sections add height after the browser has already
        // jumped to the anchor, so jump again now that the layout is final.
        if (location.hash.length > 1) {
            var target = document.getElementById(location.hash.slice(1));
            if (target) {
                var y = target.getBoundingClientRect().top + window.scrollY - (document.querySelector('.nav').offsetHeight + 24);
                if (S.lenis) S.lenis.scrollTo(y, { immediate: true, force: true }); else window.scrollTo(0, y);
            }
        }
    });
})();
