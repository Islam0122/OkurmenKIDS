/* Survey workspace helpers: native <dialog> open/close, copy-link button,
   <details> menus closing on outside click, double-submit protection. */
(function () {
  "use strict";

  document.addEventListener("click", function (e) {
    var opener = e.target.closest("[data-okfb-open]");
    if (opener) {
      var dialog = document.getElementById(opener.dataset.okfbOpen);
      if (dialog && dialog.showModal) dialog.showModal();
      return;
    }
    var dismiss = e.target.closest("[data-okfb-dismiss]");
    if (dismiss) {
      var d = dismiss.closest("dialog");
      if (d) d.close();
      return;
    }
    document.querySelectorAll("details.ok-menu[open]").forEach(function (menu) {
      if (!menu.contains(e.target)) menu.removeAttribute("open");
    });
  });

  // Click on the dimmed backdrop closes a dialog.
  document.querySelectorAll("dialog.ok-modal").forEach(function (dialog) {
    dialog.addEventListener("click", function (e) {
      if (e.target === dialog) dialog.close();
    });
  });

  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    document.querySelectorAll("details.ok-menu[open]").forEach(function (m) { m.removeAttribute("open"); });
  });

  document.querySelectorAll("[data-okfb-copy]").forEach(function (button) {
    button.addEventListener("click", function () {
      var input = document.getElementById(button.dataset.okfbCopy);
      var label = button.querySelector("span");
      function done() {
        if (!label) return;
        var old = label.textContent;
        label.textContent = "Скопировано";
        setTimeout(function () { label.textContent = old; }, 1800);
      }
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(input.value).then(done, function () { input.select(); });
      } else {
        input.select();
        try { document.execCommand("copy"); done(); } catch (err) { /* user can copy manually */ }
      }
    });
  });

  document.querySelectorAll(".okfb form[method='post']").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      var btn = e.submitter || form.querySelector('button[type="submit"]');
      if (btn) setTimeout(function () { btn.disabled = true; }, 0);
    });
  });
})();
