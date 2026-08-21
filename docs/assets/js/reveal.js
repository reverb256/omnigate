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
})();
