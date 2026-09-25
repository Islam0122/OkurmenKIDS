/* Public survey — progressive enhancement only. The form works without
   this file; every rule here is re-checked on the server. */
(function () {
  "use strict";
  var form = document.getElementById("fb-form");
  if (!form) return;
  document.documentElement.classList.add("fb-js");

  var offersChoice = form.dataset.offersChoice === "1";
  var childModes = { open: form.dataset.childOpen, anonymous: form.dataset.childAnonymous };

  function currentVisibility() {
    var checked = form.querySelector('input[name="visibility"]:checked');
    if (checked) return checked.value;
    var hidden = form.querySelector('input[type="hidden"][name="visibility"]');
    return hidden ? hidden.value : "";
  }

  // Show only the identity fields that apply to the chosen visibility.
  function syncIdentity() {
    var vis = currentVisibility();
    form.querySelectorAll("[data-show-for]").forEach(function (el) {
      el.hidden = offersChoice ? vis !== el.dataset.showFor : false;
    });
    var child = form.querySelector("[data-child-field]");
    if (child) {
      var mode = vis ? childModes[vis] : (childModes.open !== "not_collected" ? childModes.open : childModes.anonymous);
      child.hidden = mode === "not_collected";
      var req = child.querySelector("[data-child-req]");
      var opt = child.querySelector("[data-child-opt]");
      if (req) req.hidden = mode !== "required";
      if (opt) opt.hidden = mode === "required";
    }
  }

  // Multiple choice: disable further boxes once max_selections is reached.
  function syncLimits() {
    form.querySelectorAll('[data-question][data-type="multiple_choice"]').forEach(function (q) {
      var boxes = q.querySelectorAll('input[type="checkbox"]');
      if (!boxes.length || !boxes[0].dataset.max) return;
      var max = parseInt(boxes[0].dataset.max, 10);
      var count = q.querySelectorAll('input[type="checkbox"]:checked').length;
      boxes.forEach(function (b) { b.disabled = !b.checked && count >= max; });
    });
  }

  function isAnswered(q) {
    if (q.dataset.type === "text") {
      var field = q.querySelector("textarea, input");
      return field && field.value.trim().length > 0;
    }
    return !!q.querySelector("input:checked");
  }

  var progress = document.getElementById("fb-progress");
  var fill = document.getElementById("fb-progress-fill");
  var label = document.getElementById("fb-progress-label");
  var questions = Array.prototype.slice.call(form.querySelectorAll("[data-question]"));

  function syncProgress() {
    if (!progress || questions.length < 3) return;
    progress.hidden = false;
    var done = questions.filter(isAnswered).length;
    fill.style.width = Math.round((done / questions.length) * 100) + "%";
    label.textContent = done + " из " + questions.length;
  }

  form.addEventListener("input", function () { syncIdentity(); syncLimits(); syncProgress(); });
  form.addEventListener("change", function () { syncIdentity(); syncLimits(); syncProgress(); });

  // Friendly client-side check for required questions (server re-validates).
  form.addEventListener("submit", function (event) {
    var firstMissing = null;
    questions.forEach(function (q) {
      var missing = q.dataset.required === "1" && !isAnswered(q);
      q.classList.toggle("has-error", missing);
      var msg = q.querySelector(".fb-error[data-client]");
      if (missing && !msg) {
        msg = document.createElement("p");
        msg.className = "fb-error";
        msg.dataset.client = "1";
        msg.textContent = "Это обязательный вопрос.";
        q.appendChild(msg);
      } else if (!missing && msg) {
        msg.remove();
      }
      if (missing && !firstMissing) firstMissing = q;
    });
    if (firstMissing) {
      event.preventDefault();
      firstMissing.scrollIntoView({ behavior: "smooth", block: "center" });
      var input = firstMissing.querySelector("input, textarea");
      if (input) input.focus({ preventScroll: true });
      return;
    }
    var button = document.getElementById("fb-submit");
    if (button) {
      // Guard against double taps on slow connections.
      setTimeout(function () { button.disabled = true; button.textContent = "Отправляем…"; }, 0);
    }
  });

  syncIdentity();
  syncLimits();
  syncProgress();

  var errors = document.getElementById("fb-errors");
  if (errors) {
    var firstError = form.querySelector(".has-error");
    (firstError || errors).scrollIntoView({ block: "center" });
    errors.focus({ preventScroll: true });
  }
})();
