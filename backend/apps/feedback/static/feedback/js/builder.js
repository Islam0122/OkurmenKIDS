/* Survey question builder (admin). Talks to the admin JSON API
   (/api/v1/feedback/…) with the Django session + CSRF token; every rule is
   enforced server-side in apps/feedback/services/builder.py — this file
   only renders state and shows the server's validation errors.
   All user text is inserted with textContent, never innerHTML. */
(function () {
  "use strict";

  var root = document.getElementById("okfb-builder");
  if (!root) return;

  var surveyId = root.dataset.surveyId;
  var api = root.dataset.apiBase;
  var csrf = root.dataset.csrf;

  var list = document.getElementById("okfb-questions");
  var empty = document.getElementById("okfb-empty");
  var addBottom = document.getElementById("okfb-add-bottom");
  var countEl = document.getElementById("okfb-count");
  var statusEl = document.getElementById("okfb-status");

  var editor = document.getElementById("okfb-editor");
  var form = document.getElementById("okfb-editor-form");
  var optionList = document.getElementById("okfb-options");
  var deleteDialog = document.getElementById("okfb-delete-dialog");

  var TYPE_LABELS = { text: "Текст", single_choice: "Один вариант", multiple_choice: "Несколько вариантов" };
  var TYPE_ICONS = { text: "bi-textarea-t", single_choice: "bi-ui-radios", multiple_choice: "bi-ui-checks" };

  var questions = [];
  var editing = null; // question object being edited, or null for a new one
  var busy = false;

  // -- HTTP ------------------------------------------------------------------

  function request(method, path, body) {
    var opts = {
      method: method,
      credentials: "same-origin",
      headers: { "Accept": "application/json", "X-CSRFToken": csrf },
    };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    return fetch(api + path, opts).then(function (res) {
      if (res.status === 204) return { ok: true, data: null };
      return res.json().then(
        function (data) { return { ok: res.ok, status: res.status, data: data }; },
        function () { return { ok: res.ok, status: res.status, data: {} }; }
      );
    });
  }

  function flash(message, isError) {
    statusEl.textContent = message;
    statusEl.classList.toggle("is-error", !!isError);
    statusEl.classList.add("is-visible");
    clearTimeout(flash._t);
    flash._t = setTimeout(function () { statusEl.classList.remove("is-visible"); }, 4000);
  }

  function firstMessage(data) {
    if (!data) return "Не удалось сохранить.";
    if (typeof data === "string") return data;
    if (Array.isArray(data)) return firstMessage(data[0]);
    var key = Object.keys(data)[0];
    return key ? firstMessage(data[key]) : "Не удалось сохранить.";
  }

  function load() {
    return request("GET", "surveys/" + surveyId + "/").then(function (res) {
      if (!res.ok) { flash("Не удалось загрузить вопросы.", true); return; }
      questions = res.data.questions || [];
      render();
    }, function () { flash("Нет соединения с сервером.", true); });
  }

  // -- Rendering -------------------------------------------------------------

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function icon(name) { return el("i", "bi " + name); }

  function iconButton(iconName, label, onClick, extraClass) {
    var b = el("button", "okfb-icon-btn" + (extraClass ? " " + extraClass : ""));
    b.type = "button";
    b.setAttribute("aria-label", label);
    b.title = label;
    b.appendChild(icon(iconName));
    b.addEventListener("click", onClick);
    return b;
  }

  function render() {
    list.textContent = "";
    countEl.textContent = questions.length ? "· " + questions.length : "";
    empty.hidden = questions.length > 0;
    addBottom.hidden = questions.length === 0;

    questions.forEach(function (q, index) {
      var card = el("li", "okfb-qcard");
      card.dataset.id = q.id;
      card.draggable = true;

      var handle = el("span", "okfb-handle");
      handle.setAttribute("aria-hidden", "true");
      handle.title = "Перетащите, чтобы изменить порядок";
      handle.appendChild(icon("bi-grip-vertical"));
      card.appendChild(handle);

      var body = el("div", "okfb-qbody");
      var head = el("div", "okfb-qhead");
      head.appendChild(el("span", "okfb-qnum", String(index + 1)));
      var badge = el("span", "ok-badge ok-badge-info okfb-type-badge");
      badge.appendChild(icon(TYPE_ICONS[q.question_type]));
      badge.appendChild(document.createTextNode(" " + TYPE_LABELS[q.question_type]));
      head.appendChild(badge);
      head.appendChild(el("span", "ok-badge " + (q.is_required ? "ok-badge-warning" : "ok-badge-muted"),
        q.is_required ? "Обязательный" : "Необязательный"));
      if (q.has_answers) {
        var lock = el("span", "okfb-locked");
        lock.title = "На вопрос уже есть ответы";
        lock.appendChild(icon("bi-lock"));
        lock.appendChild(document.createTextNode(" есть ответы"));
        head.appendChild(lock);
      }
      body.appendChild(head);
      body.appendChild(el("div", "okfb-qtext", q.text));
      if (q.help_text) body.appendChild(el("div", "okfb-qhelp", q.help_text));

      if (q.question_type === "text") {
        var bits = [q.is_multiline ? "Многострочный ответ" : "Однострочный ответ"];
        if (q.min_length) bits.push("мин. " + q.min_length + " симв.");
        if (q.max_length) bits.push("макс. " + q.max_length + " симв.");
        body.appendChild(el("div", "okfb-qmeta", bits.join(" · ")));
      } else {
        var ul = el("ul", "okfb-qoptions");
        (q.options || []).forEach(function (o) {
          var li = el("li");
          li.appendChild(icon(q.question_type === "single_choice" ? "bi-circle" : "bi-square"));
          li.appendChild(document.createTextNode(" " + o.text));
          ul.appendChild(li);
        });
        body.appendChild(ul);
        if (q.question_type === "multiple_choice" && (q.min_selections || q.max_selections)) {
          var sel = [];
          if (q.min_selections) sel.push("минимум " + q.min_selections);
          if (q.max_selections) sel.push("максимум " + q.max_selections);
          body.appendChild(el("div", "okfb-qmeta", "Выбор: " + sel.join(", ")));
        }
      }
      card.appendChild(body);

      var actions = el("div", "okfb-qactions");
      var up = iconButton("bi-arrow-up", "Переместить выше", function () { move(index, -1); });
      up.disabled = index === 0;
      var down = iconButton("bi-arrow-down", "Переместить ниже", function () { move(index, 1); });
      down.disabled = index === questions.length - 1;
      actions.appendChild(up);
      actions.appendChild(down);
      actions.appendChild(iconButton("bi-pencil", "Редактировать", function () { openEditor(q); }));
      actions.appendChild(iconButton("bi-copy", "Дублировать", function () { duplicate(q); }));
      var del = iconButton("bi-trash", q.has_answers ? "Нельзя удалить: есть ответы" : "Удалить", function () { confirmDelete(q); }, "is-danger");
      del.disabled = !!q.has_answers;
      actions.appendChild(del);
      card.appendChild(actions);

      card.addEventListener("dblclick", function (e) {
        if (!e.target.closest("button")) openEditor(q);
      });
      bindDrag(card);
      list.appendChild(card);
    });
  }

  // -- Reordering --------------------------------------------------------------

  function saveOrder(ids) {
    if (busy) return;
    busy = true;
    request("POST", "surveys/" + surveyId + "/questions/reorder/", { order: ids }).then(function (res) {
      busy = false;
      if (!res.ok) { flash(firstMessage(res.data), true); load(); return; }
      questions = res.data.questions;
      render();
      flash("Порядок вопросов сохранён.");
    }, function () { busy = false; flash("Нет соединения с сервером.", true); load(); });
  }

  function move(index, delta) {
    var target = index + delta;
    if (target < 0 || target >= questions.length) return;
    var ids = questions.map(function (q) { return q.id; });
    var tmp = ids[index]; ids[index] = ids[target]; ids[target] = tmp;
    saveOrder(ids);
    // Keep keyboard focus on the moved card's same arrow.
    setTimeout(function () {
      var card = list.querySelector('[data-id="' + tmp + '"] button[aria-label="' + (delta < 0 ? "Переместить выше" : "Переместить ниже") + '"]');
      if (card && !card.disabled) card.focus();
    }, 300);
  }

  var dragged = null;
  function bindDrag(card) {
    card.addEventListener("dragstart", function (e) {
      dragged = card;
      card.classList.add("is-dragging");
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", card.dataset.id);
    });
    card.addEventListener("dragend", function () {
      card.classList.remove("is-dragging");
      if (!dragged) return;
      dragged = null;
      var ids = Array.prototype.map.call(list.querySelectorAll(".okfb-qcard"), function (c) { return Number(c.dataset.id); });
      var before = questions.map(function (q) { return q.id; });
      if (ids.join(",") !== before.join(",")) saveOrder(ids);
    });
    card.addEventListener("dragover", function (e) {
      if (!dragged || dragged === card) return;
      e.preventDefault();
      var rect = card.getBoundingClientRect();
      var after = e.clientY > rect.top + rect.height / 2;
      list.insertBefore(dragged, after ? card.nextSibling : card);
    });
  }

  // -- Editor -----------------------------------------------------------------

  function clearErrors() {
    form.querySelectorAll(".okfb-err").forEach(function (e) { e.textContent = ""; });
    var detail = document.getElementById("okfb-err-detail");
    detail.hidden = true;
    detail.textContent = "";
    form.querySelectorAll(".has-error").forEach(function (e) { e.classList.remove("has-error"); });
  }

  function showErrors(data) {
    clearErrors();
    var shown = false;
    Object.keys(data || {}).forEach(function (key) {
      var slot = form.querySelector('[data-err="' + key + '"]');
      var message = firstMessage(data[key]);
      if (slot) {
        slot.textContent = message;
        if (slot.parentElement) slot.parentElement.classList.add("has-error");
        shown = true;
      } else {
        var detail = document.getElementById("okfb-err-detail");
        detail.hidden = false;
        detail.textContent = message;
        shown = true;
      }
    });
    if (!shown) {
      var d = document.getElementById("okfb-err-detail");
      d.hidden = false;
      d.textContent = "Не удалось сохранить вопрос.";
    }
    var first = form.querySelector(".has-error input, .has-error textarea");
    if (first) first.focus();
  }

  function currentType() {
    var checked = form.querySelector('input[name="question_type"]:checked');
    return checked ? checked.value : "single_choice";
  }

  function syncTypeSections() {
    var type = currentType();
    form.querySelectorAll(".okfb-type-section").forEach(function (section) {
      section.hidden = section.dataset.forTypes.split(" ").indexOf(type) === -1;
    });
    if (type !== "text" && optionList.children.length === 0) {
      addOptionRow(null, "");
      addOptionRow(null, "");
    }
  }

  function renumberOptions() {
    var rows = optionList.querySelectorAll("li");
    rows.forEach(function (row, i) {
      row.querySelector("input").setAttribute("aria-label", "Вариант " + (i + 1));
      row.querySelector("[data-up]").disabled = i === 0;
      row.querySelector("[data-down]").disabled = i === rows.length - 1;
    });
  }

  function addOptionRow(id, text, locked) {
    var row = el("li", "okfb-option-row");
    if (id) row.dataset.id = id;
    var input = el("input", "ok-input");
    input.type = "text";
    input.maxLength = 200;
    input.value = text || "";
    input.placeholder = "Текст варианта";
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        e.preventDefault();
        var next = row.nextElementSibling;
        if (next) next.querySelector("input").focus();
        else addOptionRow(null, "").querySelector("input").focus();
      }
    });
    row.appendChild(input);

    var up = iconButton("bi-arrow-up", "Выше", function () {
      if (row.previousElementSibling) optionList.insertBefore(row, row.previousElementSibling);
      renumberOptions();
      up.focus();
    });
    up.dataset.up = "1";
    var down = iconButton("bi-arrow-down", "Ниже", function () {
      if (row.nextElementSibling) optionList.insertBefore(row.nextElementSibling, row);
      renumberOptions();
      down.focus();
    });
    down.dataset.down = "1";
    var remove = iconButton("bi-x-lg", locked ? "Нельзя удалить: вопрос уже получал ответы" : "Удалить вариант", function () {
      row.remove();
      renumberOptions();
    }, "is-danger");
    remove.disabled = !!locked;
    row.appendChild(up);
    row.appendChild(down);
    row.appendChild(remove);
    optionList.appendChild(row);
    renumberOptions();
    return row;
  }

  function setNumber(name, value) {
    form.elements[name].value = value === null || value === undefined ? "" : value;
  }

  function readNumber(name) {
    var raw = form.elements[name].value.trim();
    return raw === "" ? null : Number(raw);
  }

  function openEditor(q) {
    editing = q || null;
    clearErrors();
    form.reset();
    optionList.textContent = "";
    var locked = !!(q && q.has_answers);
    document.getElementById("okfb-editor-title").lastChild.textContent = q ? " Редактировать вопрос" : " Новый вопрос";
    document.getElementById("okfb-locked-note").hidden = !locked;

    var type = q ? q.question_type : "single_choice";
    form.querySelectorAll('input[name="question_type"]').forEach(function (r) {
      r.checked = r.value === type;
      r.disabled = locked && r.value !== type;
    });
    form.elements.text.value = q ? q.text : "";
    form.elements.help_text.value = q ? q.help_text : "";
    form.elements.is_required.checked = q ? q.is_required : true;
    form.elements.is_multiline.checked = q ? q.is_multiline : true;
    setNumber("min_length", q && q.min_length);
    setNumber("max_length", q && q.max_length);
    setNumber("min_selections", q && q.min_selections);
    setNumber("max_selections", q && q.max_selections);
    if (q && q.options) {
      q.options.forEach(function (o) { addOptionRow(o.id, o.text, locked); });
    }
    syncTypeSections();
    editor.showModal();
    form.elements.text.focus();
  }

  function payload() {
    var type = currentType();
    var data = {
      text: form.elements.text.value.trim(),
      help_text: form.elements.help_text.value.trim(),
      question_type: type,
      is_required: form.elements.is_required.checked,
      is_multiline: form.elements.is_multiline.checked,
      min_length: type === "text" ? readNumber("min_length") : null,
      max_length: type === "text" ? readNumber("max_length") : null,
      min_selections: type === "multiple_choice" ? readNumber("min_selections") : null,
      max_selections: type === "multiple_choice" ? readNumber("max_selections") : null,
      options: [],
    };
    if (type !== "text") {
      optionList.querySelectorAll("li").forEach(function (row) {
        var item = { text: row.querySelector("input").value.trim() };
        if (row.dataset.id) item.id = Number(row.dataset.id);
        data.options.push(item);
      });
    }
    return data;
  }

  form.addEventListener("change", function (e) {
    if (e.target.name === "question_type") syncTypeSections();
  });

  document.getElementById("okfb-add-option").addEventListener("click", function () {
    addOptionRow(null, "").querySelector("input").focus();
  });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    if (busy) return;
    var data = payload();
    if (!data.text) { showErrors({ text: "Введите текст вопроса." }); return; }
    var saveBtn = document.getElementById("okfb-save");
    busy = true;
    saveBtn.disabled = true;
    var call = editing
      ? request("PUT", "questions/" + editing.id + "/", data)
      : request("POST", "surveys/" + surveyId + "/questions/", data);
    call.then(function (res) {
      busy = false;
      saveBtn.disabled = false;
      if (!res.ok) { showErrors(res.data); return; }
      editor.close();
      flash(editing ? "Вопрос сохранён." : "Вопрос добавлен.");
      load();
    }, function () {
      busy = false;
      saveBtn.disabled = false;
      showErrors({ detail: "Нет соединения с сервером." });
    });
  });

  // -- Duplicate / delete ----------------------------------------------------

  function duplicate(q) {
    if (busy) return;
    busy = true;
    request("POST", "questions/" + q.id + "/duplicate/").then(function (res) {
      busy = false;
      if (!res.ok) { flash(firstMessage(res.data), true); return; }
      flash("Копия вопроса добавлена.");
      load();
    }, function () { busy = false; flash("Нет соединения с сервером.", true); });
  }

  var pendingDelete = null;
  function confirmDelete(q) {
    pendingDelete = q;
    document.getElementById("okfb-delete-text").textContent = "«" + q.text + "» будет удалён без возможности восстановления.";
    deleteDialog.showModal();
  }

  document.getElementById("okfb-delete-confirm").addEventListener("click", function () {
    if (!pendingDelete || busy) return;
    busy = true;
    request("DELETE", "questions/" + pendingDelete.id + "/").then(function (res) {
      busy = false;
      deleteDialog.close();
      if (!res.ok) { flash(firstMessage(res.data), true); return; }
      flash("Вопрос удалён.");
      load();
    }, function () { busy = false; deleteDialog.close(); flash("Нет соединения с сервером.", true); });
  });

  // -- Wiring ------------------------------------------------------------------

  document.querySelectorAll("[data-okfb-add]").forEach(function (b) {
    b.addEventListener("click", function () { openEditor(null); });
  });

  load();
})();
