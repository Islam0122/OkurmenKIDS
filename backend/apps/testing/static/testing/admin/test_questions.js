/* Test change page — drag & drop ordering of the questions table
 * (admin/testing/test/_questions.html). On drop the rows are renumbered
 * and the full id list is POSTed to TestAdmin.reorder_questions_view,
 * which stores it as Question.order = 1..n. On failure the previous
 * order is restored and the error is shown above the table. */
(function () {
  "use strict";

  function init() {
    var section = document.getElementById("questions");
    if (!section) return;
    var url = section.getAttribute("data-reorder-url");
    var body = section.querySelector("[data-ok-tq-body]");
    var status = section.querySelector("[data-ok-tq-status]");
    if (!url || !body) return;

    var csrfInput = document.querySelector("input[name=csrfmiddlewaretoken]");
    var dragged = null;
    var snapshot = null;
    var statusTimer = null;

    function rows() { return Array.prototype.slice.call(body.querySelectorAll("tr[data-id]")); }

    function renumber() {
      rows().forEach(function (row, index) {
        var cell = row.querySelector("[data-ok-tq-num]");
        if (cell) cell.textContent = String(index + 1);
      });
    }

    function showStatus(text, kind) {
      if (!status) return;
      window.clearTimeout(statusTimer);
      status.textContent = text;
      status.className = "ok-tq__status is-visible is-" + kind;
      if (kind === "success") {
        statusTimer = window.setTimeout(function () { status.className = "ok-tq__status"; }, 2500);
      }
    }

    function restore(order) {
      order.forEach(function (row) { body.appendChild(row); });
      renumber();
    }

    function save(previous) {
      var ids = rows().map(function (row) { return row.getAttribute("data-id"); });
      section.classList.add("is-saving");
      fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfInput ? csrfInput.value : "",
          "X-Requested-With": "XMLHttpRequest"
        },
        body: JSON.stringify({ order: ids })
      })
        .then(function (response) {
          return response.json().catch(function () { return {}; }).then(function (data) {
            if (!response.ok) throw new Error(data.error || "Не удалось сохранить порядок.");
            showStatus("Порядок вопросов сохранён.", "success");
          });
        })
        .catch(function (error) {
          restore(previous);
          showStatus(error.message || "Не удалось сохранить порядок.", "error");
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
      // Firefox only starts a drag when some data is set.
      event.dataTransfer.setData("text/plain", row.getAttribute("data-id"));
    });

    body.addEventListener("dragover", function (event) {
      if (!dragged) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
      var target = event.target.closest && event.target.closest("tr[data-id]");
      if (!target || target === dragged) return;
      var box = target.getBoundingClientRect();
      var after = event.clientY > box.top + box.height / 2;
      body.insertBefore(dragged, after ? target.nextSibling : target);
      renumber();
    });

    body.addEventListener("drop", function (event) {
      if (dragged) event.preventDefault();
    });

    body.addEventListener("dragend", function () {
      if (!dragged) return;
      dragged.classList.remove("is-dragging");
      var previous = snapshot;
      var changed = rows().some(function (row, index) { return row !== previous[index]; });
      dragged = null;
      snapshot = null;
      if (changed) save(previous);
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
