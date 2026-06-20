// Multi-Agent Code Review — slide deck nav.
// Keyboard (← → PageUp PageDown Space), on-screen Prev/Next, deep-link via #N,
// and a live "N / total visible" counter in the bottom-left.
//
// To hide a slide without deleting it: add data-hidden="true" to its <section>.
// CSS hides it; this script filters it out of nav so prev/next + the counter
// stay correct, and the bottom counter denominator updates automatically.

(function () {
  'use strict';

  const allSlides = Array.from(document.querySelectorAll('section.slide'));
  // Visible-only slide list — drives navigation and the counter denominator.
  const slides = allSlides.filter(function (s) {
    return s.getAttribute('data-hidden') !== 'true';
  });
  const total = slides.length;
  const counterEl = document.getElementById('counter-current');
  const counterTotalEl = document.getElementById('counter-total');
  const nameEl = document.getElementById('counter-name');
  const prevBtn = document.getElementById('prev-btn');
  const nextBtn = document.getElementById('next-btn');

  // Pretty names for the bottom-left counter — keyed by slide section id
  // (so renaming/removing slides doesn't break the lookup).
  const SLIDE_NAMES = {
    '1': 'Title',
    '2': 'Why this exists',
    '3': 'System architecture',
    '4': 'Pipeline flow',
    '5': 'Under the hood',
    '6': 'Design choices',
    '7': 'RAG layer',
    '8': 'What the agent posts',
    '9': 'Telemetry & dashboard',
    '10': 'Load-test results',
    '11': 'Evaluation',
    '12': 'Case studies',
    '13': 'Goals',
    '14': 'Thank you',
  };

  // Initialize the visible-count denominator on first load.
  if (counterTotalEl) counterTotalEl.textContent = String(total);

  function currentSlideIndex() {
    // Pick the visible slide whose top is closest to the viewport's top edge.
    const scrollY = window.scrollY;
    let best = 0;
    let bestDist = Infinity;
    slides.forEach(function (s, i) {
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
    counterEl.textContent = String(i + 1);
    if (nameEl) nameEl.textContent = SLIDE_NAMES[slides[i].id] || '';
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

  // Honor deep links: /#5 → slide whose id="5". If that slide is hidden,
  // fall back to the next visible one (or the last if none).
  function handleHash() {
    const m = (window.location.hash || '').match(/^#(\d+)$/);
    if (m) {
      const targetId = m[1];
      let idx = slides.findIndex(function (s) { return s.id === targetId; });
      if (idx < 0) {
        // Hidden — find the next visible slide whose numeric id is >= target.
        const targetNum = parseInt(targetId, 10);
        idx = slides.findIndex(function (s) { return parseInt(s.id, 10) >= targetNum; });
        if (idx < 0) idx = total - 1;
      }
      goTo(idx);
    } else {
      updateCounter(0);
    }
  }
  window.addEventListener('hashchange', handleHash);
  // Slight delay so the first scroll happens after layout.
  setTimeout(handleHash, 30);
})();
