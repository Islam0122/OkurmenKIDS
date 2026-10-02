/* Taking a test (testing/public/take.html): one question at a time with
 * Назад / Далее, progress, required-question checks, and a countdown that
 * submits the answers itself when the time is up (timed_out=1, so required
 * questions don't block it). In the admin preview nothing is submitted.
 *
 * Live monitoring: the page reports which question is open and how many
 * are answered (never the answers) every 15 s, on navigation and when the
 * page is closed (sendBeacon). Answers are also kept as a draft in this
 * browser (localStorage), so a student who reconnects doesn't lose them. */
(function () {
  "use strict";

  var form = document.querySelector("[data-ex-take]");
  if (!form) return;
  var questions = Array.prototype.slice.call(form.querySelectorAll("[data-ex-q]"));
  if (!questions.length) return;

  var prev = form.querySelector("[data-ex-prev]");
  var next = form.querySelector("[data-ex-next]");
  var finish = form.querySelector("[data-ex-finish]");
  var label = form.querySelector("[data-ex-progress-label]");
  var bar = form.querySelector("[data-ex-progress]");
  var preview = form.hasAttribute("data-ex-preview");
  var index = 0;
  var submitting = false;

  // Open the first question with an error from the server, if any.
  form.classList.add("is-stepped");

  function answered(section) {
    var inputs = section.querySelectorAll("input[name^=answer_], textarea[name^=answer_]");
    return Array.prototype.some.call(inputs, function (input) {
      if (input.type === "radio" || input.type === "checkbox") return input.checked;
      return input.value.trim() !== "";
    });
  }

  function show(i) {
    var changed = index !== Math.max(0, Math.min(i, questions.length - 1));
    index = Math.max(0, Math.min(i, questions.length - 1));
    if (changed || !show.reported) { show.reported = true; window.setTimeout(function () { if (typeof report === "function") { report(false); saveDraft(); } }, 0); }
    questions.forEach(function (q, n) { q.hidden = n !== index; });
    var last = index === questions.length - 1;
    prev.disabled = index === 0;
    next.hidden = last;
    finish.hidden = !last;
    label.textContent = "Вопрос " + (index + 1) + " из " + questions.length;
    bar.style.width = ((index + 1) / questions.length * 100) + "%";
    var focusTarget = questions[index].querySelector(".ex-q__title");
    if (focusTarget) { focusTarget.setAttribute("tabindex", "-1"); focusTarget.focus({ preventScroll: true }); }
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function checkRequired(section) {
    var ok = section.getAttribute("data-required") !== "1" || answered(section);
    var error = section.querySelector("[data-ex-q-error]");
    if (error) error.hidden = ok;
    return ok;
  }

  prev.addEventListener("click", function () { show(index - 1); });
  next.addEventListener("click", function () {
    if (!preview && !checkRequired(questions[index])) return;
    show(index + 1);
  });

  form.addEventListener("submit", function (event) {
    if (preview) { event.preventDefault(); return; }
    var timedOut = form.querySelector("[data-ex-timed-out]").value === "1";
    if (!timedOut) {
      for (var i = 0; i < questions.length; i++) {
        if (!checkRequired(questions[i])) { event.preventDefault(); show(i); return; }
      }
      var unanswered = questions.filter(function (q) { return !answered(q); }).length;
      var message = unanswered
        ? "Без ответа: " + unanswered + ". Всё равно завершить тест?"
        : "Завершить тест и отправить ответы?";
      if (!window.confirm(message)) { event.preventDefault(); return; }
    }
    submitting = true;
    if (finish) finish.disabled = true;
  });

  window.addEventListener("beforeunload", function (event) {
    if (!preview && !submitting) { event.preventDefault(); event.returnValue = ""; }
  });

  // -- Progress heartbeat + local draft ----------------------------------------
  var progressUrl = form.getAttribute("data-ex-progress-url");
  var draftKey = form.getAttribute("data-ex-attempt") ? "ex-draft-" + form.getAttribute("data-ex-attempt") : null;
  var csrf = form.querySelector("input[name=csrfmiddlewaretoken]");

  function answeredCount() { return questions.filter(answered).length; }

  function report(left) {
    if (!progressUrl || submitting) return;
    var data = new FormData();
    if (csrf) data.append("csrfmiddlewaretoken", csrf.value);
    data.append("current", String(index + 1));
    data.append("answered", String(answeredCount()));
    if (left) {
      data.append("left", "1");
      if (navigator.sendBeacon) navigator.sendBeacon(progressUrl, data);
      return;
    }
    fetch(progressUrl, { method: "POST", body: data, credentials: "same-origin" }).catch(function () {});
  }

  function saveDraft() {
    if (!draftKey) return;
    var values = {};
    form.querySelectorAll("input[name^=answer_], textarea[name^=answer_]").forEach(function (input) {
      if (input.type === "radio" || input.type === "checkbox") {
        if (input.checked) (values[input.name] = values[input.name] || []).push(input.value);
      } else {
        values[input.name] = input.value;
      }
    });
    try { window.localStorage.setItem(draftKey, JSON.stringify({ index: index, values: values })); } catch (e) { /* storage unavailable */ }
  }

  function restoreDraft() {
    if (!draftKey) return null;
    var draft = null;
    try { draft = JSON.parse(window.localStorage.getItem(draftKey) || "null"); } catch (e) { return null; }
    if (!draft || !draft.values) return null;
    form.querySelectorAll("input[name^=answer_], textarea[name^=answer_]").forEach(function (input) {
      var value = draft.values[input.name];
      if (value === undefined) return;
      if (input.type === "radio" || input.type === "checkbox") input.checked = value.indexOf(input.value) !== -1;
      else input.value = value;
    });
    return draft;
  }

  var draftTimer = null;
  form.addEventListener("input", function () {
    window.clearTimeout(draftTimer);
    draftTimer = window.setTimeout(function () { saveDraft(); report(false); }, 800);
  });
  form.addEventListener("change", function () { saveDraft(); });
  form.addEventListener("submit", function () {
    if (!submitting) return;  // the confirm/required checks above may still cancel
    try { if (draftKey) window.localStorage.removeItem(draftKey); } catch (e) { /* ignore */ }
  });
  if (progressUrl) {
    window.setInterval(function () { if (!document.hidden) report(false); }, 15000);
    document.addEventListener("visibilitychange", function () { report(document.hidden); });
    window.addEventListener("pagehide", function () { report(true); });
  }

  // -- Timer ----------------------------------------------------------------
  var secondsAttr = form.getAttribute("data-ex-seconds-left");
  var timerEl = form.querySelector("[data-ex-timer]");
  if (secondsAttr !== null && timerEl) {
    var deadline = Date.now() + parseInt(secondsAttr, 10) * 1000;
    var tick = function () {
      var left = Math.max(0, Math.round((deadline - Date.now()) / 1000));
      var m = Math.floor(left / 60), s = left % 60;
      timerEl.textContent = m + ":" + (s < 10 ? "0" : "") + s;
      timerEl.parentNode.classList.toggle("is-low", left <= 60);
      if (left === 0) {
        window.clearInterval(handle);
        form.querySelector("[data-ex-timed-out]").value = "1";
        submitting = true;
        HTMLFormElement.prototype.submit.call(form);
      }
    };
    var handle = window.setInterval(tick, 1000);
    tick();
  }

  var serverError = form.querySelector(".ex-alert");
  var draft = serverError ? null : restoreDraft();
  var firstError = questions.findIndex ? questions.findIndex(function (q) { return q.querySelector(".ex-error:not([hidden])"); }) : -1;
  show(firstError > 0 ? firstError : (draft && draft.index) || 0);
})();
