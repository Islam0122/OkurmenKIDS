/* Taking a test (testing/public/take.html): one question at a time with
 * Назад / Далее, progress, required-question checks, and a countdown that
 * submits the answers itself when the time is up (timed_out=1, so required
 * questions don't block it). In the admin preview nothing is submitted. */
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
    index = Math.max(0, Math.min(i, questions.length - 1));
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

  var firstError = questions.findIndex ? questions.findIndex(function (q) { return q.querySelector(".ex-error:not([hidden])"); }) : -1;
  show(firstError > 0 ? firstError : 0);
})();
