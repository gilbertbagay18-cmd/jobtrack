document.addEventListener("click", function (e) {
  var btn = e.target.closest(".eye");
  if (!btn) return;
  var input = document.getElementById(btn.dataset.target);
  var show = input.type === "password";
  input.type = show ? "text" : "password";
  btn.classList.toggle("on", show);
  btn.setAttribute("aria-pressed", show);
  btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
});

document.addEventListener("change", function (e) {
  if (e.target.matches("[data-autosubmit]")) e.target.form.submit();
});
document.addEventListener("submit", function (e) {
  var msg = e.target.dataset.confirm;
  if (msg && !window.confirm(msg)) e.preventDefault();
});

document.addEventListener("click", function (e) {
  var o = e.target.closest("[data-open]");
  if (o) document.getElementById(o.dataset.open).showModal();
  var c = e.target.closest("[data-close]");
  if (c) c.closest("dialog").close();
  document.querySelectorAll("details.menu[open]").forEach(function (d) {
    if (!d.contains(e.target)) d.open = false;
  });
});
document.addEventListener("keydown", function (e) {
  if (e.key === "Escape") document.querySelectorAll("details.menu[open]").forEach(function (d) { d.open = false; });
});
