/* ImageUrlField (admin/testing/tests/_image_url_field.html).
 * Typing a URL shows a preview; only http(s) URLs are ever put into the
 * <img src> (never innerHTML); a picture that fails to load shows
 * «Не удалось загрузить изображение» but the value stays in the form, so a
 * temporarily unavailable image never blocks saving. Works for fields added
 * later (answer option rows cloned from a <template>) via delegation. */
(function () {
  "use strict";

  var HTTP_URL = /^https?:\/\/[^\s/$.?#][^\s]*$/i;
  var timers = new WeakMap();

  function parts(field) {
    return {
      input: field.querySelector("[data-image-url-input]"),
      clear: field.querySelector("[data-image-url-clear]"),
      error: field.querySelector("[data-image-url-error]"),
      preview: field.querySelector("[data-image-url-preview]"),
      img: field.querySelector("[data-image-url-img]"),
      fallback: field.querySelector("[data-image-url-fallback]")
    };
  }

  function update(field) {
    var p = parts(field);
    var value = p.input.value.trim();
    p.clear.hidden = !value;
    if (!value) {
      p.error.hidden = true;
      p.preview.hidden = true;
      p.img.removeAttribute("src");
      return;
    }
    if (!HTTP_URL.test(value)) {
      p.error.textContent = "Ссылка должна начинаться с http:// или https://";
      p.error.hidden = false;
      p.preview.hidden = true;
      p.img.removeAttribute("src");
      return;
    }
    p.error.hidden = true;
    p.preview.hidden = false;
    if (p.img.getAttribute("src") !== value) {
      p.img.hidden = false;
      p.fallback.hidden = true;
      p.img.setAttribute("src", value);
    }
  }

  document.addEventListener("input", function (event) {
    var field = event.target.closest && event.target.closest("[data-image-url-field]");
    if (!field || !event.target.matches("[data-image-url-input]")) return;
    window.clearTimeout(timers.get(field));
    timers.set(field, window.setTimeout(function () { update(field); }, 350));
  });
  document.addEventListener("change", function (event) {
    var field = event.target.closest && event.target.closest("[data-image-url-field]");
    if (field && event.target.matches("[data-image-url-input]")) update(field);
  });
  document.addEventListener("click", function (event) {
    var button = event.target.closest && event.target.closest("[data-image-url-clear]");
    if (!button) return;
    var field = button.closest("[data-image-url-field]");
    var input = parts(field).input;
    input.value = "";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    update(field);
    input.focus();
  });

  // load/error don't bubble — listen in the capture phase.
  document.addEventListener("error", function (event) {
    if (!event.target.matches || !event.target.matches("[data-image-url-img]")) return;
    var p = parts(event.target.closest("[data-image-url-field]"));
    if (!p.img.getAttribute("src")) return;
    p.img.hidden = true;
    p.fallback.hidden = false;
  }, true);
  document.addEventListener("load", function (event) {
    if (!event.target.matches || !event.target.matches("[data-image-url-img]")) return;
    var p = parts(event.target.closest("[data-image-url-field]"));
    p.img.hidden = false;
    p.fallback.hidden = true;
  }, true);

  function init() {
    document.querySelectorAll("[data-image-url-field]").forEach(function (field) {
      var p = parts(field);
      // An image that already failed before this script ran.
      if (p.img.getAttribute("src") && p.img.complete && p.img.naturalWidth === 0) {
        p.img.hidden = true;
        p.fallback.hidden = false;
      }
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
