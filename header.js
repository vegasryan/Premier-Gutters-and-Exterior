/* The header's menus (Services, and the phone menu). Both are <details>, so they open and close without this file.
   This adds: one open at a time, close on Escape (focus goes back to the button), on a click or tap outside, when focus
   moves out, after a link in them is followed, and the phone menu closing when the screen widens past it. While the
   phone menu is open the page underneath holds still. Services inside the phone menu is a menu within a menu: opening
   it keeps the phone menu open, and Escape closes the inner one first. */
(() => {
  const root = document.documentElement;
  const menus = () => document.querySelectorAll('.site-hdr details');
  const sync = () => {
    const m = document.querySelector('.site-hdr .mnav[open]');
    root.classList.toggle('mnav-open', !!m && m.getClientRects().length > 0);
  };
  const close = (d) => { if (d.open) d.open = false; };

  document.addEventListener('toggle', (e) => {
    const d = e.target;
    if (!(d instanceof HTMLDetailsElement) || !d.closest('.site-hdr')) return;
    if (d.open) menus().forEach((x) => { if (x !== d && !x.contains(d) && !d.contains(x)) close(x); });
    sync();
  }, true);

  document.addEventListener('click', (e) => {
    menus().forEach((d) => { if (!d.contains(e.target)) close(d); });
    const a = e.target.closest('.site-hdr details a');
    if (a) menus().forEach(close);
  });

  document.addEventListener('focusin', (e) => {
    menus().forEach((d) => { if (!d.contains(e.target)) close(d); });
  });

  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    const d = [...menus()].reverse().find((x) => x.open && x.getClientRects().length);   // the innermost open one
    if (!d) return;
    close(d);
    d.querySelector('summary').focus();
  });

  const wide = matchMedia('(min-width: 1241px)');
  const onWide = () => { if (wide.matches) document.querySelectorAll('.site-hdr .mnav').forEach(close); };
  wide.addEventListener('change', onWide);
})();
