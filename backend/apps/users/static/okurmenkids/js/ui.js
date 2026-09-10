/**
 * OkurmenKIDS admin — small UX touches.
 *
 * Currently just one thing: add a show/hide toggle to every password field
 * rendered anywhere in the admin (login form, Add Trainer, change-password
 * page), per the design spec's "password visibility toggle" requirement.
 * No framework, no build step — plain DOM, runs once on load.
 */
(function () {
  "use strict";

  function addToggle(input) {
    if (input.dataset.okToggled) return;
    input.dataset.okToggled = "true";

    var wrap = document.createElement("div");
    wrap.className = "ok-password-wrap";
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);

    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ok-password-toggle";
    btn.setAttribute("aria-label", "Показать пароль");
    btn.innerHTML = '<i class="bi bi-eye"></i>';

    btn.addEventListener("click", function () {
      var showing = input.type === "text";
      input.type = showing ? "password" : "text";
      btn.innerHTML = showing
        ? '<i class="bi bi-eye"></i>'
        : '<i class="bi bi-eye-slash"></i>';
      btn.setAttribute("aria-label", showing ? "Показать пароль" : "Скрыть пароль");
    });

    wrap.appendChild(btn);
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll('input[type="password"]').forEach(addToggle);
  });
})();
