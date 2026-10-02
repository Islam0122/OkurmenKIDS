/* Question editor (admin/testing/tests/question_form.html).
 *  - The type switch shows only the sections for that type
 *    (elements with data-okt-for="type1 type2"); hidden inputs are disabled
 *    so a single-choice question never posts checkbox values and back.
 *  - Answer options: add / remove / move up-down / drag; correctness is a
 *    radio (one variant) or checkbox (several). Before submit every row's
 *    marker value is set to its current index, which is what the server
 *    reads (option_correct / option_correct_single).
 *  - Code tests: add / remove rows. */
(function () {
  "use strict";

  var form = document.querySelector("[data-okt-qform]");
  if (!form) return;

  var optionsList = form.querySelector("[data-okt-options]");
  var testsList = form.querySelector("[data-okt-tests]");
  var optionTemplate = form.querySelector("template[data-okt-option-template]");
  var testTemplate = form.querySelector("template[data-okt-test-template]");

  function currentType() {
    var checked = form.querySelector("input[name=question_type]:checked");
    return checked ? checked.value : "";
  }

  function syncType() {
    var type = currentType();
    form.setAttribute("data-type", type);
    form.querySelectorAll("[data-okt-for]").forEach(function (el) {
      var visible = el.getAttribute("data-okt-for").split(" ").indexOf(type) !== -1;
      el.hidden = !visible;
      if (el.matches("input, select, textarea")) el.disabled = !visible;
    });
    form.querySelectorAll(".okt-typeswitch__item").forEach(function (item) {
      item.classList.toggle("is-active", item.querySelector("input").checked);
    });
  }

  function options() { return Array.prototype.slice.call(optionsList.querySelectorAll("[data-okt-option]")); }

  function renumberOptions() {
    options().forEach(function (row, index) {
      row.querySelectorAll("input[name=option_correct], input[name=option_correct_single]").forEach(function (input) {
        input.value = String(index);
      });
      var text = row.querySelector("input[name=option_text]");
      if (text) text.placeholder = "Вариант " + (index + 1);
    });
  }

  function addOption() {
    var row = optionTemplate.content.firstElementChild.cloneNode(true);
    optionsList.appendChild(row);
    renumberOptions();
    syncType();
    row.querySelector("input[name=option_text]").focus();
  }

  function addTest() {
    var row = testTemplate.content.firstElementChild.cloneNode(true);
    testsList.appendChild(row);
    row.querySelector("textarea").focus();
  }

  form.addEventListener("change", function (event) {
    if (event.target.name === "question_type") syncType();
  });

  form.addEventListener("click", function (event) {
    var button = event.target.closest("button");
    if (!button || !form.contains(button)) return;
    if (button.hasAttribute("data-okt-add-option")) { addOption(); return; }
    if (button.hasAttribute("data-okt-add-test")) { addTest(); return; }
    var option = button.closest("[data-okt-option]");
    var test = button.closest("[data-okt-test]");
    if (button.hasAttribute("data-okt-remove")) {
      if (option) { option.remove(); renumberOptions(); }
      else if (test) test.remove();
      return;
    }
    var move = button.getAttribute("data-okt-move");
    if (move && option) {
      var sibling = move === "up" ? option.previousElementSibling : option.nextElementSibling;
      if (sibling) {
        optionsList.insertBefore(option, move === "up" ? sibling : sibling.nextElementSibling);
        renumberOptions();
        button.focus();
      }
    }
  });

  // Drag options by their grip.
  var dragged = null;
  optionsList.addEventListener("mousedown", function (event) {
    var grip = event.target.closest(".okt-option__grip");
    var row = grip && grip.closest("[data-okt-option]");
    if (row) row.setAttribute("draggable", "true");
  });
  optionsList.addEventListener("dragstart", function (event) {
    dragged = event.target.closest("[data-okt-option]");
    if (!dragged) return;
    dragged.classList.add("is-dragging");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", "");
  });
  optionsList.addEventListener("dragover", function (event) {
    if (!dragged) return;
    event.preventDefault();
    var target = event.target.closest("[data-okt-option]");
    if (!target || target === dragged) return;
    var box = target.getBoundingClientRect();
    optionsList.insertBefore(dragged, event.clientY > box.top + box.height / 2 ? target.nextSibling : target);
  });
  optionsList.addEventListener("dragend", function () {
    if (!dragged) return;
    dragged.classList.remove("is-dragging");
    dragged.removeAttribute("draggable");
    dragged = null;
    renumberOptions();
  });

  form.addEventListener("submit", renumberOptions);

  renumberOptions();
  syncType();
})();
