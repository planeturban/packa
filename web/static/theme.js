function _setTheme(t) {
  localStorage.setItem('theme', t);
  if (t === 'system') delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = t;
  document.querySelectorAll('.theme-btn').forEach(function(b) {
    b.classList.toggle('active', b.dataset.t === t);
  });
}
// Mark active button on load
var _t = localStorage.getItem('theme') || 'system';
document.querySelectorAll('.theme-btn').forEach(function(b) {
  b.classList.toggle('active', b.dataset.t === _t);
});
