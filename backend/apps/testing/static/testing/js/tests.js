/* «Тесты» admin section — small progressive enhancements:
 *  - close open <details class="ok-menu"> on outside click / Escape;
 *  - forms with data-okt-confirm ask before submitting (deletes, finish);
 *  - forms with data-okt-guard warn about unsaved changes on leave;
 *  - drag & drop ordering of the questions table (#questions), saved via
 *    POST {order: [ids]} to its data-reorder-url (Question.order = 1..n);
 *  - links with data-okt-dialog="<id>" open that import / export <dialog>
 *    (a shared questions dialog takes its test, action and template links
 *    from the link); list filters apply on change; card checkboxes feed
 *    «Экспорт → Только выбранные».
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

  // Test / question images: a URL that fails to load shows the placeholder
  // (card cover, question thumb) or hides the image (header thumb).
  function markBroken(img) {
    var wrap = img.closest("[data-okt-img-wrap]");
    if (wrap) wrap.classList.add("is-broken");
  }
  document.addEventListener("error", function (event) {
    var img = event.target;
    if (img.matches && img.matches("img[data-okt-img]")) markBroken(img);
  }, true);
  // Failed before this script ran (the error event is gone by now).
  document.querySelectorAll("img[data-okt-img]").forEach(function (img) {
    if (img.complete && !img.naturalWidth) markBroken(img);
  });

  // -- Import / export dialogs -------------------------------------------
  function resetFile(dialog) {
    dialog.querySelectorAll("[data-okt-file]").forEach(function (input) {
      input.value = "";
      var label = dialog.querySelector("[data-okt-file-name]");
      if (label) label.textContent = label.getAttribute("data-empty") || label.textContent;
    });
  }

  document.addEventListener("click", function (event) {
    var link = event.target.closest && event.target.closest("[data-okt-dialog]");
    if (!link) return;
    var dialog = document.getElementById(link.getAttribute("data-okt-dialog"));
    if (!dialog || typeof dialog.showModal !== "function") return;  // no <dialog>: follow the link
    event.preventDefault();
    var menu = link.closest("details.ok-menu");
    if (menu) menu.removeAttribute("open");
    var form = dialog.querySelector("[data-okt-io-form]");
    if (link.hasAttribute("data-okt-test") && form) {
      form.setAttribute("action", link.getAttribute("href"));
      dialog.querySelectorAll("[data-okt-io-test]").forEach(function (el) { el.textContent = link.getAttribute("data-okt-test"); });
      var base = link.getAttribute("data-okt-template");
      if (base) {
        dialog.querySelectorAll("[data-okt-io-template]").forEach(function (a) {
          a.setAttribute("href", base + "?format=" + a.getAttribute("data-okt-io-template"));
        });
      }
    }
    resetFile(dialog);
    updateSelection(true);
    dialog.showModal();
  });

  document.querySelectorAll("dialog.ok-modal").forEach(function (dialog) {
    dialog.addEventListener("click", function (event) {
      if (event.target === dialog || (event.target.closest && event.target.closest("[data-okt-close]"))) dialog.close();
    });
    var form = dialog.querySelector("[data-okt-io-form]");
    if (!form) return;
    form.addEventListener("submit", function () {
      if (form.method.toLowerCase() === "get") {
        window.setTimeout(function () { dialog.close(); }, 150);  // a download: the page stays
      } else {
        var button = form.querySelector("button[type=submit]");
        if (button) { button.disabled = true; button.lastElementChild.textContent = "Импорт…"; }
      }
    });
  });

  document.querySelectorAll("[data-okt-file]").forEach(function (input) {
    var label = input.parentElement.querySelector("[data-okt-file-name]");
    if (label) label.setAttribute("data-empty", label.textContent);
    input.addEventListener("change", function () {
      if (label) label.textContent = input.files && input.files.length ? input.files[0].name : label.getAttribute("data-empty");
      input.closest(".okt-dropzone").classList.toggle("has-file", !!(input.files && input.files.length));
    });
  });

  // -- List: filters apply on change, card selection for export -----------
  document.querySelectorAll("form[data-okt-autosubmit]").forEach(function (form) {
    form.querySelectorAll("[data-okt-autosubmit-hide]").forEach(function (el) { el.hidden = true; });
    form.querySelectorAll("select").forEach(function (select) {
      select.addEventListener("change", function () { form.submit(); });
    });
  });

  function updateSelection(preferSelected) {
    var boxes = Array.prototype.slice.call(document.querySelectorAll("[data-okt-select]"));
    if (!boxes.length) return;
    var count = 0;
    boxes.forEach(function (box) {
      var card = box.closest(".okt-card");
      if (card) card.classList.toggle("is-selected", box.checked);
      if (box.checked) count += 1;
    });
    document.querySelectorAll("[data-okt-selected-count]").forEach(function (el) {
      el.textContent = count ? "(" + count + ")" : "— отметьте карточки";
    });
    document.querySelectorAll("[data-okt-scope-selected]").forEach(function (radio) {
      radio.disabled = !count;
      if (!count && radio.checked) {
        var first = radio.form && radio.form.querySelector("input[name=scope]");
        if (first) first.checked = true;
      }
      if (count && preferSelected) radio.checked = true;
    });
  }
  document.addEventListener("change", function (event) {
    if (event.target.matches && event.target.matches("[data-okt-select]")) updateSelection(false);
  });
  updateSelection(false);

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
