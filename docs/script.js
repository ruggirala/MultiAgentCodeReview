// Multi-Agent Code Review — slide deck nav.
// Keyboard (← → PageUp PageDown Space), on-screen Prev/Next, deep-link via #N,
// and a live "current / 10" counter in the bottom-left.

(function () {
  'use strict';

  const slides = Array.from(document.querySelectorAll('section.slide'));
  const total = slides.length;
  const counterEl = document.getElementById('counter-current');
  const nameEl = document.getElementById('counter-name');
  const prevBtn = document.getElementById('prev-btn');
  const nextBtn = document.getElementById('next-btn');

  // Pretty names for the bottom-left counter — matches each <h1>.
  const SLIDE_NAMES = {
    1: 'Title',
    2: 'Why this exists',
    3: 'System architecture',
    4: 'Pipeline flow',
    5: 'Under the hood',
    6: 'RAG layer',
    7: 'What the agent posts',
    8: 'Telemetry & dashboard',
    9: 'Load-test results',
    10: 'Evaluation',
    11: 'Case studies',
    12: 'Goals',
    13: 'Thank you',
  };

  function currentSlideIndex() {
    // Pick the slide whose top is closest to (and at or above) the viewport's
    // top edge. IntersectionObserver also runs, but this is the source of truth
    // when the user clicks Prev/Next.
    const scrollY = window.scrollY;
    let best = 0;
    let bestDist = Infinity;
    slides.forEach((s, i) => {
      const dist = Math.abs(s.offsetTop - scrollY);
      if (dist < bestDist) {
        bestDist = dist;
        best = i;
      }
    });
    return best;
  }

  function goTo(i) {
    if (i < 0) i = 0;
    if (i >= total) i = total - 1;
    const id = slides[i].id;
    if (window.location.hash !== '#' + id) {
      // Replace the hash so back-button history doesn't fill with every slide.
      history.replaceState(null, '', '#' + id);
    }
    slides[i].scrollIntoView({ behavior: 'smooth', block: 'start' });
    updateCounter(i);
  }

  function updateCounter(i) {
    const num = i + 1;
    counterEl.textContent = String(num);
    if (nameEl) nameEl.textContent = SLIDE_NAMES[num] || '';
  }

  // Keyboard nav
  document.addEventListener('keydown', function (ev) {
    // Don't hijack typing in inputs (none in this deck, but defensive).
    if (ev.target && ['INPUT', 'TEXTAREA'].includes(ev.target.tagName)) return;
    const i = currentSlideIndex();
    if (ev.key === 'ArrowRight' || ev.key === 'PageDown' || ev.key === ' ') {
      ev.preventDefault();
      goTo(i + 1);
    } else if (ev.key === 'ArrowLeft' || ev.key === 'PageUp') {
      ev.preventDefault();
      goTo(i - 1);
    } else if (ev.key === 'Home') {
      ev.preventDefault();
      goTo(0);
    } else if (ev.key === 'End') {
      ev.preventDefault();
      goTo(total - 1);
    }
  });

  prevBtn.addEventListener('click', function () { goTo(currentSlideIndex() - 1); });
  nextBtn.addEventListener('click', function () { goTo(currentSlideIndex() + 1); });

  // Track which slide is centered as the user scrolls — keeps counter in sync
  // with wheel/touch gestures, not just keyboard.
  if ('IntersectionObserver' in window) {
    const io = new IntersectionObserver(
      function (entries) {
        // Pick the entry with the largest intersection ratio.
        let best = null;
        entries.forEach(function (e) {
          if (!best || e.intersectionRatio > best.intersectionRatio) best = e;
        });
        if (best && best.isIntersecting) {
          const i = slides.indexOf(best.target);
          if (i >= 0) updateCounter(i);
        }
      },
      { threshold: [0.4, 0.6, 0.8] }
    );
    slides.forEach(function (s) { io.observe(s); });
  }

  // Honor deep links: open at /#5 → slide 5.
  function handleHash() {
    const m = (window.location.hash || '').match(/^#(\d+)$/);
    if (m) {
      const i = Math.max(0, Math.min(total - 1, parseInt(m[1], 10) - 1));
      goTo(i);
    } else {
      updateCounter(0);
    }
  }
  window.addEventListener('hashchange', handleHash);
  // Slight delay so the first scroll happens after layout.
  setTimeout(handleHash, 30);
})();
