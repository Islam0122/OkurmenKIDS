/* Student portal — preparation page: «Начать экзамен» stays disabled until
 * «Я ознакомился(ась) с правилами экзамена» is ticked (the server checks the
 * same field again). No Exam Mode restrictions here: they start only on the
 * attempt page (exam_mode.js). */
(function () {
  "use strict";
  var form = document.querySelector("[data-sp-start]");
  if (!form) return;
  var rules = form.querySelector("[data-sp-rules]");
  var button = form.querySelector("[data-sp-start-btn]");
  function sync() { button.disabled = !rules.checked; }
  rules.addEventListener("change", sync);
  sync();
  form.addEventListener("submit", function (event) {
    if (!rules.checked) { event.preventDefault(); return; }
    button.disabled = true;  // no double start
  });
})();
