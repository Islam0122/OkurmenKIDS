/* Public survey — step flow on top of a plain server-rendered form.
   Progressive enhancement only: without this file the whole form is shown
   and posts as one page. Field names, values and the POST are unchanged;
   every rule checked here is re-checked on the server
   (apps/feedback/services/submission.py), which stays authoritative. */
(function () {
  "use strict";

  var form = document.getElementById("fb-form");
  if (!form) return;

  var isStudent = form.dataset.student === "1";
  var isPreview = form.dataset.preview === "1";
  var offersChoice = form.dataset.offersChoice === "1";
  var childModes = { open: form.dataset.childOpen, anonymous: form.dataset.childAnonymous };

  var T = isStudent ? {
    required: "Пожалуйста, ответь на этот обязательный вопрос.",
    name: "Пожалуйста, укажи своё имя.",
    visibility: "Пожалуйста, выбери, как отправить отзыв.",
    child: "Пожалуйста, укажи имя ребёнка.",
    offline: "Нет подключения к интернету. Твои ответы сохранены на этой странице — проверь соединение и попробуй снова.",
    fix: "Пожалуйста, проверь отмеченные ответы.",
  } : {
    required: "Пожалуйста, ответьте на этот обязательный вопрос.",
    name: "Пожалуйста, укажите ваше имя.",
    visibility: "Пожалуйста, выберите, как отправить отзыв.",
    child: "Пожалуйста, укажите имя ребёнка.",
    offline: "Нет подключения к интернету. Ваши ответы сохранены на этой странице — проверьте соединение и попробуйте снова.",
    fix: "Пожалуйста, проверьте отмеченные ответы.",
  };

  var steps = Array.prototype.slice.call(form.querySelectorAll(".fb-step"));
  var questionSteps = steps.filter(function (s) { return s.dataset.step === "question"; });
  var reviewStep = form.querySelector('[data-step="review"]');
  var current = 0;
  var returnToReview = false;
  var submitting = false;

  var progress = document.getElementById("fb-progress");
  var progressLabel = document.getElementById("fb-progress-label");
  var progressPct = document.getElementById("fb-progress-pct");
  var progressBar = document.getElementById("fb-progress-bar");
  var progressFill = document.getElementById("fb-progress-fill");
  var alertBox = document.getElementById("fb-errors");
  var alertText = document.getElementById("fb-errors-text");
  var retryButton = alertBox.querySelector('[data-action="retry"]');
  var btnBack = form.querySelector('[data-action="back"]');
  var btnNext = form.querySelector('[data-action="next"]');
  var btnSubmit = document.getElementById("fb-submit");
  var nav = document.getElementById("fb-nav");

  // -- Helpers -----------------------------------------------------------------

  function plural(n, one, few, many) {
    var m10 = n % 10, m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return one;
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
    return many;
  }

  function visibility() {
    var checked = form.querySelector('input[name="visibility"]:checked');
    if (checked) return checked.value;
    var hidden = form.querySelector('input[type="hidden"][name="visibility"]');
    return hidden ? hidden.value : "";
  }

  function childMode() {
    var vis = visibility();
    if (vis) return childModes[vis];
    // Nothing chosen yet: show the field if either mode collects it.
    return childModes.open !== "not_collected" ? childModes.open : childModes.anonymous;
  }

  function textField(step) { return step.querySelector("textarea, input.fb-input"); }
  function checked(step) { return step.querySelectorAll(".fb-option-input:checked"); }

  function isAnswered(step) {
    if (step.dataset.type === "text") {
      var f = textField(step);
      return !!f && f.value.trim().length > 0;
    }
    return checked(step).length > 0;
  }

  function setError(scope, key, message) {
    var slot = scope.querySelector('[data-error-for="' + key + '"]');
    var holder = slot ? (slot.closest(".fb-group") || slot.closest(".fb-question")) : null;
    if (slot) {
      slot.textContent = message || "";
      slot.hidden = !message;
    }
    if (holder) holder.classList.toggle("has-error", !!message);
    var fields = holder ? holder.querySelectorAll("input:not([type=hidden]), textarea") : [];
    Array.prototype.forEach.call(fields, function (f) {
      if (f.type === "radio" || f.type === "checkbox") return;
      if (message) {
        f.setAttribute("aria-invalid", "true");
        if (slot && slot.id) f.setAttribute("aria-describedby", slot.id);
      } else {
        f.removeAttribute("aria-invalid");
      }
    });
  }

  // -- Validation (friendly, client-side; the server re-validates) ------------

  function validateIdentity(step) {
    var first = null;
    if (offersChoice) {
      var missing = !visibility();
      setError(step, "visibility", missing ? T.visibility : "");
      if (missing) first = first || step.querySelector('input[name="visibility"]');
    }
    var name = step.querySelector('input[name="respondent_name"]');
    if (name) {
      var needName = visibility() === "open" && !name.value.trim();
      setError(step, "respondent_name", needName ? T.name : "");
      if (needName) first = first || name;
    }
    var child = step.querySelector('input[name="child_name"]');
    if (child) {
      var needChild = childMode() === "required" && !child.value.trim();
      setError(step, "child_name", needChild ? T.child : "");
      if (needChild) first = first || child;
    }
    return first;
  }

  function validateQuestion(step) {
    var name = (step.querySelector("[name]") || {}).name;
    var message = "";
    if (step.dataset.required === "1" && !isAnswered(step)) {
      message = T.required;
    } else if (step.dataset.type === "text" && step.dataset.minLength) {
      var len = textField(step).value.trim().length;
      var min = parseInt(step.dataset.minLength, 10);
      if (len > 0 && len < min) {
        message = "Минимум " + min + " " + plural(min, "символ", "символа", "символов") + " — сейчас " + len + ".";
      }
    } else if (step.dataset.type === "multiple_choice" && step.dataset.minSelections) {
      var count = checked(step).length;
      var minSel = parseInt(step.dataset.minSelections, 10);
      if (count > 0 && count < minSel) message = "Выберите минимум " + minSel + ".";
    }
    setError(step, name, message);
    return message ? (step.querySelector(".fb-option-input, textarea, input.fb-input")) : null;
  }

  function validateStep(step) {
    if (step.dataset.step === "identity") return validateIdentity(step);
    if (step.dataset.step === "question") return validateQuestion(step);
    return null;
  }

  // -- Step display ------------------------------------------------------------

  function updateProgress(step) {
    var kind = step.dataset.step;
    var total = questionSteps.length;
    var label, pct;
    if (kind === "identity") {
      label = isStudent ? "Сначала пара слов о тебе" : "Сначала пара слов о вас";
      pct = 0;
    } else if (kind === "question") {
      var n = questionSteps.indexOf(step) + 1;
      label = "Вопрос " + n + " из " + total;
      pct = Math.round((n / total) * 100);
    } else {
      label = "Все вопросы пройдены";
      pct = 100;
    }
    progressLabel.textContent = label;
    progressPct.textContent = pct + "%";
    progressFill.style.width = pct + "%";
    progressBar.setAttribute("aria-valuenow", String(pct));
    progressBar.setAttribute("aria-valuetext", label + ", " + pct + "%");
  }

  function show(index, opts) {
    opts = opts || {};
    current = Math.max(0, Math.min(index, steps.length - 1));
    var step = steps[current];
    steps.forEach(function (s, i) { s.classList.toggle("is-current", i === current); });

    var kind = step.dataset.step;
    var isIntro = kind === "intro";
    var isReview = kind === "review";
    progress.hidden = isIntro;
    nav.hidden = isIntro;
    btnBack.hidden = isIntro;
    btnNext.hidden = isReview;
    btnSubmit.hidden = !isReview;
    btnNext.textContent = returnToReview && !isReview ? "К проверке ответов" :
      (steps[current + 1] && steps[current + 1].dataset.step === "review" ? "Проверить ответы" : "Далее");
    if (!isIntro) updateProgress(step);
    if (isReview) buildReview();

    if (opts.scroll !== false) {
      var top = form.getBoundingClientRect().top + window.pageYOffset - 8;
      window.scrollTo({ top: Math.max(0, top), behavior: "auto" });
    }
    if (opts.focus !== false) {
      var target = opts.focusEl || step.querySelector(".fb-qtitle, .fb-step-title, .fb-title");
      if (target) target.focus({ preventScroll: true });
    }
  }

  function navigate(index, opts) {
    form.classList.add("is-navigating");
    show(index, opts);
  }

  function goNext() {
    var step = steps[current];
    var invalid = validateStep(step);
    if (invalid) {
      invalid.focus();
      return;
    }
    if (returnToReview && reviewStep) {
      returnToReview = false;
      navigate(steps.indexOf(reviewStep));
      return;
    }
    navigate(current + 1);
  }

  function goBack() {
    returnToReview = false;
    navigate(current - 1);
  }

  // -- Review ------------------------------------------------------------------

  function addReviewItem(list, title, answer, stepIndex, missing) {
    var item = document.createElement("div");
    item.className = "fb-review-item" + (missing ? " is-missing" : "");
    var dt = document.createElement("dt");
    dt.textContent = title;
    var dd = document.createElement("dd");
    dd.textContent = answer || "Нет ответа";
    if (!answer) dd.className = "is-empty";
    var edit = document.createElement("button");
    edit.type = "button";
    edit.className = "fb-review-edit";
    edit.textContent = "Изменить";
    edit.setAttribute("aria-label", "Изменить: " + title);
    edit.addEventListener("click", function () {
      returnToReview = true;
      navigate(stepIndex);
    });
    item.appendChild(dt);
    item.appendChild(dd);
    item.appendChild(edit);
    list.appendChild(item);
  }

  function buildReview() {
    var list = document.getElementById("fb-review-list");
    list.textContent = "";
    var identity = form.querySelector('[data-step="identity"]');
    if (identity) {
      var vis = visibility();
      var name = form.querySelector('input[name="respondent_name"]');
      var who = vis === "anonymous" ? "Анонимно" :
        (vis === "open" ? "С именем" + (name && name.value.trim() ? ": " + name.value.trim() : "") : "");
      addReviewItem(list, "Как отправить отзыв", who, steps.indexOf(identity), !!validateIdentityQuiet(identity));
      var child = form.querySelector('input[name="child_name"]');
      if (child && childMode() !== "not_collected") {
        addReviewItem(list, "Имя и фамилия ребёнка", child.value.trim(), steps.indexOf(identity), false);
      }
    }
    questionSteps.forEach(function (step, i) {
      var title = String(i + 1).padStart(2, "0") + " · " + step.querySelector(".fb-qtitle").textContent.trim();
      var answer;
      if (step.dataset.type === "text") {
        answer = textField(step).value.trim();
      } else {
        answer = Array.prototype.map.call(checked(step), function (input) {
          return input.closest(".fb-option").querySelector(".fb-option-text").textContent.trim();
        }).join(", ");
      }
      addReviewItem(list, title, answer, steps.indexOf(step), step.dataset.required === "1" && !answer);
    });
  }

  // Validation without touching the visible error state (review summary).
  function validateIdentityQuiet() {
    if (offersChoice && !visibility()) return true;
    var name = form.querySelector('input[name="respondent_name"]');
    if (name && visibility() === "open" && !name.value.trim()) return true;
    var child = form.querySelector('input[name="child_name"]');
    return !!(child && childMode() === "required" && !child.value.trim());
  }

  // -- Identity fields / limits / counters ---------------------------------------------

  function syncIdentity() {
    var vis = visibility();
    form.querySelectorAll("[data-show-for]").forEach(function (el) {
      el.hidden = offersChoice ? vis !== el.dataset.showFor : false;
    });
    var child = form.querySelector("[data-child-field]");
    if (child) {
      var mode = childMode();
      child.hidden = mode === "not_collected";
      var req = child.querySelector("[data-child-req]");
      var opt = child.querySelector("[data-child-opt]");
      if (req) req.hidden = mode !== "required";
      if (opt) opt.hidden = mode === "required";
    }
  }

  function syncLimits() {
    questionSteps.forEach(function (step) {
      if (step.dataset.type !== "multiple_choice" || !step.dataset.maxSelections) return;
      var max = parseInt(step.dataset.maxSelections, 10);
      var boxes = step.querySelectorAll(".fb-option-input");
      var count = checked(step).length;
      boxes.forEach(function (b) { b.disabled = !b.checked && count >= max; });
    });
  }

  function syncCounter(field) {
    var counter = form.querySelector('[data-counter-for="' + field.id + '"]');
    if (!counter) return;
    var max = field.maxLength;
    counter.textContent = field.value.length + " / " + max;
    counter.classList.toggle("is-near", field.value.length >= max * 0.9);
  }

  // -- Submission ------------------------------------------------------------------------

  function showAlert(message, withRetry) {
    alertText.textContent = message;
    retryButton.hidden = !withRetry;
    alertBox.hidden = false;
    alertBox.focus({ preventScroll: false });
  }

  function setLoading(on) {
    submitting = on;
    btnSubmit.disabled = on;
    btnSubmit.classList.toggle("is-loading", on);
    btnSubmit.setAttribute("aria-busy", on ? "true" : "false");
    btnSubmit.querySelector(".fb-button-label").textContent = on ? "Отправляем…" : "Отправить отзыв";
    btnBack.disabled = on;
  }

  form.addEventListener("submit", function (event) {
    if (isPreview || submitting) {
      event.preventDefault();
      return;
    }
    for (var i = 0; i < steps.length; i++) {
      var invalid = validateStep(steps[i]);
      if (invalid) {
        event.preventDefault();
        show(i, { focusEl: invalid });
        showAlert(T.fix, false);
        return;
      }
    }
    if (navigator.onLine === false) {
      event.preventDefault();
      showAlert(T.offline, true);
      return;
    }
    alertBox.hidden = true;
    setLoading(true);
  });

  retryButton.addEventListener("click", function () {
    if (navigator.onLine === false) {
      showAlert(T.offline, true);
      return;
    }
    if (form.requestSubmit) form.requestSubmit(btnSubmit);
    else btnSubmit.click();
  });

  // Coming back via the browser's back/forward cache: re-enable the form.
  window.addEventListener("pageshow", function (e) { if (e.persisted) setLoading(false); });

  // -- Events --------------------------------------------------------------------------------

  form.addEventListener("click", function (e) {
    var action = e.target.closest("[data-action]");
    if (!action) return;
    if (action.dataset.action === "start") navigate(1);
    else if (action.dataset.action === "next") goNext();
    else if (action.dataset.action === "back") goBack();
  });

  // Enter in a one-line field moves on instead of submitting the whole form.
  form.addEventListener("keydown", function (e) {
    if (e.key !== "Enter" || e.target.tagName !== "INPUT" || e.target.type === "submit") return;
    if (e.target.type === "radio" || e.target.type === "checkbox") return;
    e.preventDefault();
    if (steps[current].dataset.step !== "review") goNext();
  });

  form.addEventListener("input", function (e) {
    if (e.target.tagName === "TEXTAREA" || e.target.classList.contains("fb-input")) syncCounter(e.target);
    onChange(e);
  });
  form.addEventListener("change", onChange);

  function onChange(e) {
    syncIdentity();
    syncLimits();
    // Once a step shows an error, re-check it live so the message clears
    // as soon as the answer is fixed.
    var step = e.target.closest(".fb-step");
    if (step && (step.classList.contains("has-error") || step.querySelector(".has-error"))) {
      validateStep(step);
    }
  }

  // -- Init ------------------------------------------------------------------------------------

  syncIdentity();
  syncLimits();
  form.querySelectorAll("textarea, input.fb-input").forEach(syncCounter);
  form.classList.add("fb-ready");

  if (form.dataset.hasErrors === "1") {
    // Server rejected the submission: open the first step it flagged
    // (answers are all still filled in), or the review step for a
    // form-level error such as a rate limit.
    var flagged = steps.findIndex(function (s) {
      return s.classList.contains("has-error") || s.querySelector(".has-error");
    });
    show(flagged > 0 ? flagged : steps.indexOf(reviewStep), { focus: false });
    alertBox.focus({ preventScroll: true });
  } else {
    show(0, { scroll: false, focus: false });
  }
})();
