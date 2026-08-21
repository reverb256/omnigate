// omnigate — Apple-fluid reveals (dependency-free)
// IntersectionObserver adds .is-visible when a .reveal enters the viewport.
// Reduced motion is handled in CSS (@media prefers-reduced-motion), so JS
// only needs to make things visible if the observer never fires (SSR/no-JS).
(function () {
  'use strict';
  var reveals = document.querySelectorAll('.reveal');
  if (!reveals.length) return;

  // Respect reduced motion: make everything visible immediately, no motion.
  if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    reveals.forEach(function (el) { el.classList.add('is-visible'); });
    return;
  }

  if (!('IntersectionObserver' in window)) {
    reveals.forEach(function (el) { el.classList.add('is-visible'); });
    return;
  }

  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (entry.isIntersecting) {
        entry.target.classList.add('is-visible');
        io.unobserve(entry.target); // 1:1, one-shot — never re-triggers
      }
    });
  }, { threshold: 0.12 });

  reveals.forEach(function (el) { io.observe(el); });

  // Fix "back button isn't working": when the browser restores the page from
  // the back-forward cache (bfcache) or reloads at a scroll position, the
  // observer may not re-fire for elements already in view. Show everything
  // so back-navigation never lands on a half-revealed page.
  window.addEventListener('pageshow', function (event) {
    // event.persisted === true means restored from bfcache — the DOM state
    // (including .is-visible classes) was frozen, but re-reveal defensively.
    // On a normal reload, force-reveal everything in the viewport so the
    // user's scroll position shows content, not blanks.
    reveals.forEach(function (el) {
      var rect = el.getBoundingClientRect();
      if (rect.top < window.innerHeight && rect.bottom > 0) {
        el.classList.add('is-visible');
        io.unobserve(el);
      }
    });
  });
})();
