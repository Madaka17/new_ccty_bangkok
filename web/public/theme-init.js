// Light or dark before the first paint: the viewer's saved choice (src/lib/theme.js), else dark.
// A file of its own, not inline in index.html: the site's Content-Security-Policy (script-src 'self') blocks
// inline scripts.
(function () {
  var t;
  try { t = localStorage.getItem('theme'); } catch (e) {}
  if (t !== 'light' && t !== 'dark') t = 'dark';
  document.documentElement.classList.toggle('dark', t === 'dark');
  document.documentElement.style.colorScheme = t;
})();
