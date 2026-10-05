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
