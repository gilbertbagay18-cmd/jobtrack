(function () {
  "use strict";
  var ICONS = { success: "✅", error: "⚠️", info: "ℹ️" };
  var EMOJI = /[\u2705\u{1F389}\u{1F44B}\u{1F5D1}\uFE0F]/gu;
  var ERROR_WORDS = /\b(wrong|incorrect|invalid|expired|not|required|must|match|valid|enter|at least|mix|too many|already|failed|error)\b/i;

  function kind(msg) {
    if (ERROR_WORDS.test(msg)) return "error";
    if (/[\u2705\u{1F389}\u{1F44B}\u{1F5D1}]/u.test(msg)) return "success";
    return "info";
  }

  window.toast = function (msg, type) {
    var host = document.getElementById("toasts");
    if (!host) return;
    var t = document.createElement("div");
    t.className = "toast " + (type || kind(msg));
    t.setAttribute("role", t.classList.contains("error") ? "alert" : "status");
    var icon = document.createElement("span");
    icon.textContent = ICONS[type || kind(msg)];
    var text = document.createElement("span");
    text.textContent = msg.replace(EMOJI, "").trim();
    var x = document.createElement("button");
    x.type = "button";
    x.setAttribute("aria-label", "Dismiss");
    x.textContent = "×";
    t.appendChild(icon);
    t.appendChild(text);
    t.appendChild(x);
    host.appendChild(t);
    function bye() {
      t.classList.add("out");
      setTimeout(function () { t.remove(); }, 250);
    }
    x.addEventListener("click", bye);
    setTimeout(bye, t.classList.contains("error") ? 7000 : 4500);
  };

  var data = document.getElementById("flash-data");
  if (data) {
    JSON.parse(data.textContent).forEach(function (m) { window.toast(m); });
  }

  document.addEventListener("click", function (e) {
    var eye = e.target.closest(".eye");
    if (eye) {
      var input = document.getElementById(eye.dataset.target);
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      eye.classList.toggle("on", show);
      eye.setAttribute("aria-pressed", show);
      eye.setAttribute("aria-label", show ? "Hide password" : "Show password");
    }
    var open = e.target.closest("[data-open]");
    if (open) document.getElementById(open.dataset.open).showModal();
    var close = e.target.closest("[data-close]");
    if (close) close.closest("dialog").close();
    document.querySelectorAll("details.menu[open]").forEach(function (d) {
      if (!d.contains(e.target)) d.open = false;
    });
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      document.querySelectorAll("details.menu[open]").forEach(function (d) { d.open = false; });
    }
  });

  document.addEventListener("change", function (e) {
    if (e.target.matches("[data-autosubmit]")) e.target.form.submit();
  });

  var dlg = document.getElementById("confirm-dialog");
  var pending = null;

  document.addEventListener("submit", function (e) {
    var form = e.target;
    var msg = form.dataset.confirm;
    if (msg && dlg) {
      e.preventDefault();
      pending = form;
      document.getElementById("confirm-msg").textContent = msg;
      dlg.showModal();
      return;
    }
    var btn = form.querySelector("button[type=submit]");
    if (btn) {
      setTimeout(function () { btn.classList.add("loading"); btn.disabled = true; }, 0);
    }
  });

  if (dlg) {
    document.getElementById("confirm-yes").addEventListener("click", function () {
      dlg.close();
      if (!pending) return;
      var f = pending;
      pending = null;
      delete f.dataset.confirm;
      if (f.requestSubmit) f.requestSubmit(); else f.submit();
    });
    document.getElementById("confirm-no").addEventListener("click", function () {
      pending = null;
      dlg.close();
    });
  }

  window.addEventListener("pageshow", function () {
    document.querySelectorAll("button.loading").forEach(function (b) {
      b.disabled = false;
      b.classList.remove("loading");
    });
  });
})();
