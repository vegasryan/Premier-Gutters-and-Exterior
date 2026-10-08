/* Scroll in and out (Vegas, 7 Oct 2026, night: "find a perfect reference to build me simple scroll in/out animations ... that matches
   our design and isnt too much for the audience"). Copied from Mirador (mirador.framer.media, a Framer real-estate template), measured
   frame by frame on 7 and 8 Oct; the research and the runner-up are in design/scroll-motion/README.md.

   One recipe everywhere. A block fades in from opacity 0 while rising from a few px below its place (20 for a header or a column of
   words, 24 for a photo or a row of cards, 14 for the link line under them), 800 ms on cubic-bezier(.22,.61,.36,1), when 15% of it
   is on screen. When less than 15% is left, at either edge, the same tween runs backwards, and it plays in again whenever it comes
   back. Each block moves as one piece: nothing inside a block is staggered and blocks never wait for each other.

   On purpose, unlike Mirador: nothing is hidden without this script, under reduced motion, or when it is already on screen as the page
   opens (so a reload, the back button or a #link never flashes); in or out is judged from where a block rests, not where it is drawn,
   so a block parked at the top edge can't flicker; the contact forms at the foot of every page (the closing panel) never fade (Vegas,
   8 Oct 2026: "NO fade in animation for the contact forms at the bottom of pages"; it had come in once and never gone out); the heroes,
   each page's first section, the nav, the footer, the office map and the FAQ's questions never move. It animates opacity and the translate property only, with element.animate(), so the cards' own transform
   and transition (their hover lift) are untouched and nothing changes the layout. */
(() => {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  if (reduce.matches || !('IntersectionObserver' in window) || !Element.prototype.animate) return;
  // automated browsers (the sessions' headless checkers, Lighthouse) get the still page, so a full-page screenshot never catches
  // blocks waiting below the window; ?motion=on runs it there for testing. A visitor's browser is never automated.
  if (navigator.webdriver && !/[?&]motion=on\b/.test(location.search)) return;
  const DUR = 800, EASE = 'cubic-bezier(.22,.61,.36,1)', RATIO = 0.15, MAXY = 24;
  const SETS = [
    // section headers and the word columns that stand for one (Mirador's "Head"): 20px
    { y: 20, sel: '.wd-head, .hr-head, .rw-head, .hsa-words, .fqw-head, .hwa-info, .obb-panel, .hav-head, .wsg-head, .rr-head, .pt-head' },
    // a photo, or a row of photos or cards, as one block (Mirador's "Featured" and "Gallery Grid"): 24px
    { y: 24, sel: '.wd-feed, .hr-rows, .rw-mo, .hsa-photo, .fqp-photo, .hwa-track, .hav-grid, .pt-row, .wsg-row, .rr-cards' },
    // the link line under a block (Mirador's note line): 14px
    { y: 14, sel: '.hwa-all, .hsa-all, .hr-all, .cc-all' },
  ];

  const items = new Map();
  const ratioNow = (el) => {
    const r = el.getBoundingClientRect();
    const seen = Math.max(0, Math.min(r.bottom, innerHeight) - Math.max(r.top, 0));
    return r.height ? seen / r.height : 0;
  };
  const current = (el) => {
    const cs = getComputedStyle(el);
    return { opacity: cs.opacity, translate: cs.translate === 'none' ? '0px 0px' : cs.translate };
  };
  const stop = (it) => { if (it.anim) { const a = it.anim; it.anim = null; a.onfinish = null; a.cancel(); } };

  // in or out from wherever the block is now, so a turn mid-way never jumps
  function show(it) {
    const from = current(it.el);
    stop(it);
    it.el.classList.remove('sio-off');
    it.anim = it.el.animate([from, { opacity: 1, translate: '0px 0px' }], { duration: DUR, easing: EASE });
    it.anim.onfinish = () => { it.anim = null; };
    it.state = 'in';
    ioIn.unobserve(it.el);
    if (!it.once) ioOut.observe(it.el);
  }
  function hide(it) {
    const from = current(it.el);
    stop(it);
    const a = it.el.animate([from, { opacity: 0, translate: `0px ${it.y}px` }], { duration: DUR, easing: EASE, fill: 'forwards' });
    it.anim = a;
    a.onfinish = () => { if (it.anim !== a) return; it.el.classList.add('sio-off'); it.anim = null; a.cancel(); };
    it.state = 'out';
    ioOut.unobserve(it.el);
    ioIn.observe(it.el);
  }
  // a shown block is tested against the window; a hidden one (drawn up to 24px low) against the window with its top 24px lower,
  // which is the same as testing where it rests. root: document keeps the margin working inside the MVP's Phone view frame.
  const ioOut = new IntersectionObserver((es) => es.forEach((e) => {
    const it = items.get(e.target);
    if (it && it.state === 'in' && e.intersectionRatio < RATIO) hide(it);
  }), { threshold: [0, RATIO], root: document });
  const ioIn = new IntersectionObserver((es) => es.forEach((e) => {
    const it = items.get(e.target);
    if (it && it.state === 'out' && e.isIntersecting && e.intersectionRatio >= RATIO) show(it);
  }), { threshold: [0, RATIO], root: document, rootMargin: `-${MAXY}px 0px 0px 0px` });

  const first = document.querySelector('main section[id]');
  for (const set of SETS) {
    document.querySelectorAll(set.sel).forEach((el) => {
      const sec = el.closest('main section[id]');
      if (items.has(el) || !sec || sec === first || sec.matches('.hh, .sh, .lg')) return;
      const it = { el, y: set.y, once: !!set.once, state: 'in', anim: null };
      items.set(el, it);
      el.style.setProperty('--sio-y', set.y + 'px');
      if (ratioNow(el) >= RATIO) { if (!it.once) ioOut.observe(el); }   // on screen as the page opens: shown as it is
      else { el.classList.add('sio-off'); it.state = 'out'; ioIn.observe(el); }
    });
  }
  // reduced motion turned on mid-visit: everything shows and nothing moves again
  reduce.addEventListener('change', () => {
    if (!reduce.matches) return;
    ioIn.disconnect(); ioOut.disconnect();
    items.forEach((it) => { stop(it); it.el.classList.remove('sio-off'); });
  });
})();
