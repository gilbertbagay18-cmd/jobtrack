(function () {
  var root = document.documentElement;
  var pref = root.dataset.pref || "system";
  var mq = window.matchMedia("(prefers-color-scheme: dark)");
  function apply() {
    root.dataset.theme = pref === "system" ? (mq.matches ? "dark" : "light") : pref;
  }
  apply();
  if (pref === "system") mq.addEventListener("change", apply);
})();
