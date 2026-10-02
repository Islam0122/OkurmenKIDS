/* Question add/change form (admin/testing/question/change_form.html).
 *
 * - «Варианты ответа» inline is shown only for single/multiple choice.
 *   For text/code it is hidden — unless the question still has saved
 *   options or the inline has errors, in which case it stays visible with
 *   a note, so the admin can mark those options for deletion (the server
 *   rejects options on text/code questions, see QuestionOptionFormSet).
 * - «Язык» is flagged as required for code questions (Question.clean()
 *   enforces it on the server).
 * - Rows added with «Добавить ещё вариант» get the next «Порядок». */
(function () {
  "use strict";

  function init() {
    var config = document.querySelector(".ok-question-form");
    var typeSelect = document.getElementById("id_question_type");
    if (!config || !typeSelect) return;

    var choiceTypes = (config.getAttribute("data-choice-types") || "").split(",");
    var codeType = config.getAttribute("data-code-type");
    var group = document.getElementById("options-group");
    var card = group ? (group.closest(".card") || group) : null;
    var languageLabel = document.querySelector("label[for=id_language]");

    var note = null;
    if (group) {
      note = document.createElement("p");
      note.className = "ok-question-options-note";
      note.hidden = true;
      group.parentNode.insertBefore(note, group);
    }

    function hasSavedOptions() {
      if (!group) return false;
      var rows = group.querySelectorAll("tr.has_original");
      for (var i = 0; i < rows.length; i++) {
        var del = rows[i].querySelector("input[type=checkbox][name$='-DELETE']");
        if (!del || !del.checked) return true;
      }
      return false;
    }

    function hasErrors() {
      return !!(group && group.querySelector(".errorlist li"));
    }

    function sync() {
      var type = typeSelect.value;
      var isChoice = choiceTypes.indexOf(type) !== -1;
      if (card) {
        var keepVisible = !isChoice && (hasSavedOptions() || hasErrors());
        card.classList.toggle("ok-question-options-hidden", !isChoice && !keepVisible);
        if (note) {
          note.hidden = !keepVisible;
          note.textContent = keepVisible
            ? "Для этого типа вопроса варианты ответа не нужны — отметьте существующие варианты на удаление."
            : "";
        }
      }
      if (languageLabel) {
        languageLabel.classList.toggle("required", type === codeType);
      }
    }

    function nextOrder() {
      var max = 0;
      if (!group) return 1;
      group.querySelectorAll("tr.form-row:not(.empty-form) input[name$='-order']").forEach(function (input) {
        var value = parseInt(input.value, 10);
        if (!isNaN(value) && value > max) max = value;
      });
      return max + 1;
    }

    function relabelAddLink() {
      if (!group) return;
      var link = group.querySelector(".add-row a");
      if (link && link.textContent !== "Добавить ещё вариант") link.textContent = "Добавить ещё вариант";
    }

    typeSelect.addEventListener("change", sync);
    if (group) {
      group.addEventListener("change", function (event) {
        if (event.target.name && /-DELETE$/.test(event.target.name)) sync();
      });
    }
    document.addEventListener("formset:added", function (event) {
      if (!event.detail || event.detail.formsetName !== "options") return;
      var input = event.target.querySelector("input[name$='-order']");
      if (input) {
        input.value = "";
        input.value = String(nextOrder());
      }
    });

    sync();
    // Django's inlines.js builds the add link on its own ready handler,
    // whose timing relative to this script isn't fixed — watch for it.
    relabelAddLink();
    if (group && window.MutationObserver) {
      new MutationObserver(relabelAddLink).observe(group, { childList: true, subtree: true });
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
