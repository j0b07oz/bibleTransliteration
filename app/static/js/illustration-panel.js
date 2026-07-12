/**
 * Visual guide illustration panel (scrollytelling).
 *
 * Enhances the server-rendered #illustration-panel: as the reader scrolls the
 * chapter, a soft SVG spotlight highlights the region of the illustration that
 * the current verses describe, and the panel's caption shows that step's
 * Hebrew word, transliteration, gloss, and note. Without this script the panel
 * degrades to a static image plus the full annotated step list.
 *
 * Single master image + percentage-coordinate regions (authored in a 0-100
 * space with preserveAspectRatio="none", matching the validated prototype), so
 * adding a scene is data + one image, never new frames or new code.
 */
document.addEventListener('DOMContentLoaded', function () {
    'use strict';

    var scene = window.ILLUSTRATION_SCENE;
    var panel = document.getElementById('illustration-panel');
    var stage = document.getElementById('illustration-stage');
    if (!scene || !panel || !stage) {
        return;
    }

    var verseRows = Array.prototype.slice.call(document.querySelectorAll('.verse-row'));
    var steps = Array.isArray(scene.steps) ? scene.steps : [];
    // Nothing to track without verses (e.g. the error/fallback render) or steps.
    if (!verseRows.length || !steps.length) {
        return;
    }

    var SVG_NS = 'http://www.w3.org/2000/svg';
    var prefersReducedMotion = window.matchMedia
        && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    var stepEls = Array.prototype.slice.call(panel.querySelectorAll('.illustration-step'));
    var stepsList = document.getElementById('illustration-steps');
    var controls = document.getElementById('illustration-controls');
    var prevBtn = document.getElementById('illustration-prev');
    var nextBtn = document.getElementById('illustration-next');
    var countEl = document.getElementById('illustration-step-count');
    var activeStepEl = document.getElementById('illustration-active-step');

    var dimRect = null;
    var holesGroup = null;
    var activeIndex = null;   // null until the first render; -1 = overview state
    var rafPending = false;
    var inBand = {};          // verse number -> row element currently in the band
    var io = null;
    var manualUntil = 0;      // suppress scroll-sync until this time after a click

    // ===== SVG spotlight =====

    function svgEl(name, attrs) {
        var el = document.createElementNS(SVG_NS, name);
        for (var key in attrs) {
            if (Object.prototype.hasOwnProperty.call(attrs, key)) {
                el.setAttribute(key, String(attrs[key]));
            }
        }
        return el;
    }

    function buildSpotlight() {
        // Coordinates are percentages, so a 0-100 viewBox with a non-uniform
        // stretch maps them straight onto the image at any display size.
        var svg = svgEl('svg', {
            'class': 'illustration-spotlight',
            viewBox: '0 0 100 100',
            preserveAspectRatio: 'none',
            'aria-hidden': 'true',
            focusable: 'false'
        });

        var defs = svgEl('defs', {});

        // Soft feathered edge on the punched holes.
        var filter = svgEl('filter', {
            id: 'ill-soften', x: '-20%', y: '-20%', width: '140%', height: '140%'
        });
        filter.appendChild(svgEl('feGaussianBlur', { stdDeviation: '0.9' }));
        defs.appendChild(filter);

        // Mask: white keeps the dark overlay, black punches a hole to the image.
        var mask = svgEl('mask', {
            id: 'ill-mask', maskUnits: 'userSpaceOnUse',
            x: '0', y: '0', width: '100', height: '100'
        });
        mask.appendChild(svgEl('rect', { width: '100', height: '100', fill: '#fff' }));
        holesGroup = svgEl('g', { filter: 'url(#ill-soften)' });
        mask.appendChild(holesGroup);
        defs.appendChild(mask);
        svg.appendChild(defs);

        dimRect = svgEl('rect', {
            'class': 'illustration-dim',
            x: '0', y: '0', width: '100', height: '100',
            fill: '#0d0a08', opacity: '0', mask: 'url(#ill-mask)'
        });
        svg.appendChild(dimRect);

        stage.appendChild(svg);
    }

    function renderHoles(regions) {
        while (holesGroup.firstChild) {
            holesGroup.removeChild(holesGroup.firstChild);
        }
        (regions || []).forEach(function (r) {
            var shape;
            if (r.kind === 'ellipse') {
                shape = svgEl('ellipse', { cx: r.cx, cy: r.cy, rx: r.rx, ry: r.ry, fill: '#000' });
            } else {
                var attrs = { x: r.x, y: r.y, width: r.w, height: r.h, fill: '#000' };
                if (r.rx != null) {
                    attrs.rx = r.rx;
                }
                shape = svgEl('rect', attrs);
            }
            holesGroup.appendChild(shape);
        });
    }

    // ===== Active-step caption =====

    function appendSpan(parent, className, text, attrs) {
        if (!text) {
            return;
        }
        var span = document.createElement('span');
        span.className = className;
        span.textContent = text;   // textContent: notes/glosses are never HTML
        if (attrs) {
            for (var key in attrs) {
                if (Object.prototype.hasOwnProperty.call(attrs, key)) {
                    span.setAttribute(key, attrs[key]);
                }
            }
        }
        parent.appendChild(span);
    }

    function renderActiveCaption(step) {
        if (!activeStepEl) {
            return;
        }
        activeStepEl.innerHTML = '';
        if (!step) {
            appendSpan(activeStepEl, 'illustration-active-step__title', scene.title || '');
            return;
        }
        appendSpan(activeStepEl, 'illustration-active-step__ref', step.ref);
        var word = document.createElement('span');
        word.className = 'illustration-active-step__word';
        appendSpan(word, 'illustration-active-step__hebrew', step.hebrew, { lang: 'he', dir: 'rtl' });
        appendSpan(word, 'illustration-active-step__translit', step.translit);
        activeStepEl.appendChild(word);
        appendSpan(activeStepEl, 'illustration-active-step__gloss', step.gloss);
        appendSpan(activeStepEl, 'illustration-active-step__note', step.note);
    }

    // ===== Step selection =====

    // Steps arrive sorted by start_verse. The active step is the last one that
    // has started by this verse, so verses in the gap between two steps hold the
    // earlier step, and verses before the first step yield -1 (overview).
    function stepIndexForVerse(verse) {
        var idx = -1;
        for (var i = 0; i < steps.length; i++) {
            if (steps[i].start_verse <= verse) {
                idx = i;
            } else {
                break;
            }
        }
        return idx;
    }

    function scrollListToActive(idx) {
        // Scroll ONLY the step list (its own overflow container on desktop);
        // never the page — the reader stays in control of the document scroll.
        if (!stepsList || idx < 0 || !stepEls[idx]) {
            return;
        }
        var el = stepEls[idx];
        var top = el.offsetTop;
        var bottom = top + el.offsetHeight;
        var viewTop = stepsList.scrollTop;
        var viewBottom = viewTop + stepsList.clientHeight;
        if (top < viewTop) {
            stepsList.scrollTop = top;
        } else if (bottom > viewBottom) {
            stepsList.scrollTop = bottom - stepsList.clientHeight;
        }
    }

    function setActiveStep(idx, options) {
        options = options || {};
        if (idx === activeIndex) {
            return;
        }
        activeIndex = idx;
        var step = idx >= 0 ? steps[idx] : null;

        renderHoles(step ? step.regions : []);
        var dim = step ? (step.dim != null ? step.dim : 0.55) : 0;
        dimRect.setAttribute('opacity', String(dim));

        stepEls.forEach(function (el, i) {
            var on = i === idx;
            el.classList.toggle('is-active', on);
            var btn = el.querySelector('.illustration-step__button');
            if (btn) {
                if (on) {
                    btn.setAttribute('aria-current', 'step');
                } else {
                    btn.removeAttribute('aria-current');
                }
            }
        });

        renderActiveCaption(step);
        if (countEl) {
            countEl.textContent = idx >= 0 ? (idx + 1) + ' / ' + steps.length : '';
        }
        if (prevBtn) {
            prevBtn.disabled = idx <= 0;
        }
        if (nextBtn) {
            nextBtn.disabled = idx >= steps.length - 1;
        }
        if (options.scrollList !== false) {
            scrollListToActive(idx);
        }
    }

    // ===== Scroll synchronization =====

    function schedule() {
        if (rafPending) {
            return;
        }
        rafPending = true;
        window.requestAnimationFrame(function () {
            rafPending = false;
            updateFromScroll();
        });
    }

    // The "current" verse is the one straddling the horizontal center line of
    // the viewport (top <= center < bottom). In the gap between rows, fall back
    // to the last verse whose top has passed the center line. Highest verse
    // number wins ties so downward scrolling advances monotonically.
    function activeBandVerse() {
        var centerY = window.innerHeight * 0.5;
        var containing = null;
        var lastPassed = null;
        for (var key in inBand) {
            if (!Object.prototype.hasOwnProperty.call(inBand, key)) {
                continue;
            }
            var verse = parseInt(key, 10);
            var rect = inBand[key].getBoundingClientRect();
            if (rect.top <= centerY) {
                if (lastPassed === null || verse > lastPassed) {
                    lastPassed = verse;
                }
                if (rect.bottom > centerY && (containing === null || verse > containing)) {
                    containing = verse;
                }
            }
        }
        return containing !== null ? containing : lastPassed;
    }

    function updateFromScroll() {
        if (Date.now() < manualUntil) {
            return;   // a manual jump owns the active step until its scroll settles
        }
        // The last verses of a chapter may never reach the mid-viewport band on
        // tall screens, so force the final step once the page bottom is reached.
        var doc = document.documentElement;
        if (window.scrollY + window.innerHeight >= doc.scrollHeight - 4) {
            setActiveStep(steps.length - 1);
            return;
        }
        var verse = activeBandVerse();
        if (verse === null) {
            return;   // empty band mid-fast-scroll: keep the current step
        }
        setActiveStep(stepIndexForVerse(verse));
    }

    function observeVerses() {
        io = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                var verse = entry.target.getAttribute('data-verse');
                if (entry.isIntersecting) {
                    inBand[verse] = entry.target;
                } else {
                    delete inBand[verse];
                }
            });
            schedule();
        }, { rootMargin: '-42% 0px -42% 0px', threshold: 0 });
        verseRows.forEach(function (row) {
            io.observe(row);
        });
    }

    // ===== Manual controls =====

    function goToStep(idx) {
        if (idx < 0 || idx >= steps.length) {
            return;
        }
        setActiveStep(idx);
        // Own the active step until the (possibly smooth) scroll settles, so
        // scroll-sync doesn't momentarily activate a verse we pass through.
        manualUntil = Date.now() + (prefersReducedMotion ? 150 : 800);
        var step = steps[idx];
        var row = document.querySelector('.verse-row[data-verse="' + step.start_verse + '"]');
        if (!row) {
            return;
        }
        // Center the step's first verse on the viewport's mid line so that,
        // once sync resumes, that verse straddles the center and confirms this
        // exact step instead of an adjacent one.
        var rect = row.getBoundingClientRect();
        var target = rect.top + window.scrollY - (window.innerHeight * 0.5 - rect.height / 2);
        window.scrollTo({
            top: Math.max(0, target),
            behavior: prefersReducedMotion ? 'auto' : 'smooth'
        });
    }

    function bindControls() {
        panel.classList.add('is-enhanced');
        if (controls) {
            controls.hidden = false;
        }
        if (prevBtn) {
            prevBtn.addEventListener('click', function () {
                goToStep((activeIndex < 0 ? 0 : activeIndex) - 1);
            });
        }
        if (nextBtn) {
            nextBtn.addEventListener('click', function () {
                goToStep((activeIndex < 0 ? -1 : activeIndex) + 1);
            });
        }
        stepEls.forEach(function (el, i) {
            var btn = el.querySelector('.illustration-step__button');
            if (btn) {
                btn.addEventListener('click', function () {
                    goToStep(i);
                });
            }
        });
    }

    // ===== Init =====

    buildSpotlight();
    bindControls();
    observeVerses();
    updateFromScroll();   // resolve the correct step on load / mid-page reloads
    window.addEventListener('scroll', schedule, { passive: true });
    window.addEventListener('resize', schedule, { passive: true });
});
