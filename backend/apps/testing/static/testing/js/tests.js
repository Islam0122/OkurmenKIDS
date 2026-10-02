/* «Тесты» admin section — small progressive enhancements:
 *  - close open <details class="ok-menu"> on outside click / Escape;
 *  - forms with data-okt-confirm ask before submitting (deletes, finish);
 *  - forms with data-okt-guard warn about unsaved changes on leave;
 *  - drag & drop ordering of the questions table (#questions), saved via
 *    POST {order: [ids]} to its data-reorder-url (Question.order = 1..n).
 * Every action also works without JS (plain forms / links). */
(function () {
  "use strict";

  document.addEventListener("click", function (event) {
    document.querySelectorAll("details.ok-menu[open]").forEach(function (menu) {
      if (!menu.contains(event.target)) menu.removeAttribute("open");
    });
  });
  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    document.querySelectorAll("details.ok-menu[open]").forEach(function (menu) { menu.removeAttribute("open"); });
  });

  document.querySelectorAll("form[data-okt-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!window.confirm(form.getAttribute("data-okt-confirm"))) event.preventDefault();
    });
  });

  var dirty = new Set();
  document.querySelectorAll("form[data-okt-guard]").forEach(function (form) {
    form.addEventListener("input", function () { dirty.add(form); });
    form.addEventListener("change", function () { dirty.add(form); });
    form.addEventListener("submit", function () { dirty.delete(form); });
  });
  // Buttons outside the form (header «Сохранить» with form="…") submit it too.
  document.addEventListener("submit", function (event) { dirty.delete(event.target); }, true);
  window.addEventListener("beforeunload", function (event) {
    if (dirty.size) { event.preventDefault(); event.returnValue = ""; }
  });

  // -- Questions: drag & drop ---------------------------------------------
  var section = document.getElementById("questions");
  var body = section && section.querySelector("[data-okt-rows]");
  var url = section && section.getAttribute("data-reorder-url");
  if (!body || !url) return;

  var status = section.querySelector("[data-okt-status]");
  var csrf = document.querySelector("input[name=csrfmiddlewaretoken]");
  var dragged = null, snapshot = null, timer = null;

  function rows() { return Array.prototype.slice.call(body.querySelectorAll("tr[data-id]")); }

  function renumber() {
    rows().forEach(function (row, index) {
      var cell = row.querySelector("[data-okt-num]");
      if (cell) cell.textContent = String(index + 1);
    });
  }

  function say(text, kind) {
    if (!status) return;
    window.clearTimeout(timer);
    status.textContent = text;
    status.className = "okt-status is-visible is-" + kind;
    if (kind === "success") timer = window.setTimeout(function () { status.className = "okt-status"; }, 2500);
  }

  function save(previous) {
    section.classList.add("is-saving");
    fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf ? csrf.value : "" },
      body: JSON.stringify({ order: rows().map(function (row) { return row.getAttribute("data-id"); }) })
    })
      .then(function (response) {
        return response.json().catch(function () { return {}; }).then(function (data) {
          if (!response.ok) throw new Error(data.error || "Не удалось сохранить порядок.");
          say("Порядок вопросов сохранён.", "success");
        });
      })
      .catch(function (error) {
        previous.forEach(function (row) { body.appendChild(row); });
        renumber();
        say(error.message || "Не удалось сохранить порядок.", "error");
      })
      .then(function () { section.classList.remove("is-saving"); });
  }

  body.addEventListener("dragstart", function (event) {
    var row = event.target.closest && event.target.closest("tr[data-id]");
    if (!row) return;
    dragged = row;
    snapshot = rows();
    row.classList.add("is-dragging");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", row.getAttribute("data-id"));
  });
  body.addEventListener("dragover", function (event) {
    if (!dragged) return;
    event.preventDefault();
    var target = event.target.closest && event.target.closest("tr[data-id]");
    if (!target || target === dragged) return;
    var box = target.getBoundingClientRect();
    body.insertBefore(dragged, event.clientY > box.top + box.height / 2 ? target.nextSibling : target);
    renumber();
  });
  body.addEventListener("drop", function (event) { if (dragged) event.preventDefault(); });
  body.addEventListener("dragend", function () {
    if (!dragged) return;
    dragged.classList.remove("is-dragging");
    var previous = snapshot;
    var changed = rows().some(function (row, index) { return row !== previous[index]; });
    dragged = null;
    snapshot = null;
    if (changed) save(previous);
  });
})();
