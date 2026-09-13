/**
 * OkurmenKIDS admin — UX enhancements.
 *
 * Vanilla JS, no build step, no dependencies beyond what the admin already
 * loads (Bootstrap Icons).
 *
 * Modules:
 *   1. Force light theme
 *   2. Password visibility toggle
 *   3. MultiSelect — comfortable search + chips UI
 *   4. SearchHint — Russian, model-specific search placeholders
 *   5. EmptyState — friendly message instead of a bare "0 results"
 *   6. Actions — visually warn when a destructive bulk action is picked
 *   7. SubjectCards — checkbox card grid (Course.subjects picker)
 *   8. PhotoField — instant preview + "remove photo" state
 *   9. StudentBulkAdd — dynamic add/remove rows for the bulk-add formset
 *   10. Group Workspace — search/select-all for the "add existing students" modal
 */

(function () {
  "use strict";

  /* ------------------------------------------------------------------ */
  /* 1. Force light theme                                                 */
  /* ------------------------------------------------------------------ */

  function initLightTheme() {
    document.documentElement.setAttribute("data-theme", "light");

    try {
      window.localStorage.setItem(
        "okurmenkids-theme",
        "light"
      );
    } catch (e) {
      // Storage may be unavailable in private browsing mode.
    }
  }

  /* ------------------------------------------------------------------ */
  /* 2. Password visibility toggle                                       */
  /* ------------------------------------------------------------------ */

function addPasswordToggle(input) {
  if (input.dataset.okToggled) return;
  input.dataset.okToggled = "true";

  var inputGroup = input.closest(".input-group");

  if (!inputGroup) {
    console.warn("Password input-group not found", input);
    return;
  }

  // Find Jazzmin's existing lock/icon element
  var existingAddon = inputGroup.querySelector(
    ".input-group-append, .input-group-text, .input-group-prepend"
  );

  var btn = document.createElement("button");

  btn.type = "button";
  btn.className = "ok-password-toggle";
  btn.setAttribute("aria-label", "Показать пароль");
  btn.setAttribute("title", "Показать пароль");

  btn.innerHTML = '<i class="bi bi-eye"></i>';

  btn.addEventListener("click", function () {
    var showing = input.type === "text";

    input.type = showing ? "password" : "text";

    btn.innerHTML = showing
      ? '<i class="bi bi-eye"></i>'
      : '<i class="bi bi-eye-slash"></i>';

    btn.setAttribute(
      "aria-label",
      showing ? "Показать пароль" : "Скрыть пароль"
    );

    btn.setAttribute(
      "title",
      showing ? "Показать пароль" : "Скрыть пароль"
    );
  });

  // Put eye before the existing lock icon
  if (existingAddon) {
    inputGroup.insertBefore(btn, existingAddon);
  } else {
    inputGroup.appendChild(btn);
  }
}

  function initPasswordToggles() {
    document
      .querySelectorAll('input[type="password"]')
      .forEach(addPasswordToggle);
  }

  /* ------------------------------------------------------------------ */
  /* 3. Comfortable multi-select (search + chips)                        */
  /* ------------------------------------------------------------------ */

  function enhanceMultiSelect(select) {
    if (select.dataset.okEnhanced) return;

    select.dataset.okEnhanced = "true";

    var options = Array.prototype.slice.call(
      select.options
    );

    if (options.length === 0) return;

    select.classList.add("ok-ms-native");
    // Jazzmin's own change_form.js auto-inits vanilla Select2 on every
    // <select> not already marked as handled (its own exclusion list checks
    // for exactly this class). Without it, this same select gets a second,
    // competing enhancement — Select2's default gray-tag widget rendered
    // right alongside our chip UI below, with its oversized dropdown. This
    // class is normally added *by* Select2 after init; adding it ourselves
    // first (our script runs before jazzmin's, see change_form.html script
    // order) makes Jazzmin skip this select entirely, since it never
    // actually needs Select2 to work — it never leaves this hidden native
    // <select>, our own UI drives it.
    select.classList.add("select2-hidden-accessible");

    var wrap = document.createElement("div");
    wrap.className = "ok-multiselect";

    var chipsRow = document.createElement("div");
    chipsRow.className = "ok-ms-chips-row";

    var chips = document.createElement("div");
    chips.className = "ok-ms-chips";

    var addTrigger = document.createElement("button");
    addTrigger.type = "button";
    addTrigger.className = "ok-ms-add-trigger";
    addTrigger.innerHTML = '<i class="bi bi-plus-lg"></i><span>Добавить предмет</span>';

    chipsRow.appendChild(chips);
    chipsRow.appendChild(addTrigger);

    var dropdown = document.createElement("div");
    dropdown.className = "ok-ms-dropdown";

    var searchBar = document.createElement("div");
    searchBar.className = "ok-ms-search";
    searchBar.innerHTML =
      '<i class="bi bi-search"></i>';

    var searchInput = document.createElement("input");
    searchInput.type = "text";
    searchInput.placeholder = "Поиск...";
    searchInput.autocomplete = "off";

    searchBar.appendChild(searchInput);

    var panel = document.createElement("div");
    panel.className = "ok-multiselect-panel";

    var emptyRow = document.createElement("div");
    emptyRow.className = "ok-ms-empty";
    emptyRow.textContent = "Ничего не найдено";
    emptyRow.hidden = true;

    var footer = document.createElement("div");
    footer.className = "ok-ms-footer";

    var rows = options.map(function (opt) {
      var row = document.createElement("div");

      row.className = "ok-ms-option";
      row.setAttribute("role", "option");
      row.tabIndex = 0;
      row.dataset.value = opt.value;
      row.dataset.label = opt.text.toLowerCase();

      row.innerHTML =
        '<span></span><i class="bi bi-check-lg"></i>';

      row.querySelector("span").textContent =
        opt.text;

      function toggle() {
        opt.selected = !opt.selected;

        select.dispatchEvent(
          new Event("change", { bubbles: true })
        );

        sync();
      }

      row.addEventListener("click", toggle);

      row.addEventListener("keydown", function (evt) {
        if (
          evt.key === "Enter" ||
          evt.key === " "
        ) {
          evt.preventDefault();
          toggle();
        }
      });

      panel.appendChild(row);

      return {
        opt: opt,
        row: row,
      };
    });

    function removeChip(opt) {
      opt.selected = false;

      select.dispatchEvent(
        new Event("change", { bubbles: true })
      );

      sync();
    }

    function sync() {
      chips.innerHTML = "";

      var selectedCount = 0;

      rows.forEach(function (item) {
        var selected = item.opt.selected;

        item.row.classList.toggle(
          "is-selected",
          selected
        );

        if (selected) {
          selectedCount += 1;

          var chip = document.createElement("span");
          chip.className = "ok-ms-chip";

          var label = document.createElement("span");
          label.textContent = item.opt.text;

          var removeBtn =
            document.createElement("button");

          removeBtn.type = "button";
          removeBtn.setAttribute(
            "aria-label",
            "Убрать «" +
              item.opt.text +
              "»"
          );

          removeBtn.innerHTML =
            '<i class="bi bi-x-lg"></i>';

          removeBtn.addEventListener(
            "click",
            function () {
              removeChip(item.opt);
            }
          );

          chip.appendChild(label);
          chip.appendChild(removeBtn);

          chips.appendChild(chip);
        }
      });

      footer.innerHTML =
        "Выбрано: <strong>" +
        selectedCount +
        "</strong> из " +
        rows.length;
    }

    searchInput.addEventListener(
      "input",
      function () {
        var q = searchInput.value
          .trim()
          .toLowerCase();

        var visible = 0;

        rows.forEach(function (item) {
          var match =
            !q ||
            item.row.dataset.label.indexOf(q) !== -1;

          item.row.classList.toggle(
            "is-hidden",
            !match
          );

          if (match) visible += 1;
        });

        emptyRow.hidden = visible !== 0;
      }
    );

    function openDropdown() {
      wrap.classList.add("is-open");
      searchInput.value = "";
      searchInput.dispatchEvent(new Event("input"));
      window.setTimeout(function () {
        searchInput.focus();
      }, 0);
    }

    function closeDropdown() {
      wrap.classList.remove("is-open");
    }

    addTrigger.addEventListener("click", function (evt) {
      evt.stopPropagation();
      if (wrap.classList.contains("is-open")) {
        closeDropdown();
      } else {
        openDropdown();
      }
    });

    dropdown.addEventListener("click", function (evt) {
      evt.stopPropagation();
    });

    document.addEventListener("click", function (evt) {
      if (!wrap.contains(evt.target)) closeDropdown();
    });

    wrap.addEventListener("keydown", function (evt) {
      if (evt.key === "Escape") {
        closeDropdown();
        addTrigger.focus();
      }
    });

    dropdown.appendChild(searchBar);
    dropdown.appendChild(panel);
    panel.appendChild(emptyRow);
    dropdown.appendChild(footer);

    wrap.appendChild(chipsRow);
    wrap.appendChild(dropdown);

    select.parentNode.insertBefore(
      wrap,
      select.nextSibling
    );

    sync();
  }

  function initMultiSelects() {
    document
      .querySelectorAll(
        "select[multiple].ok-subject-select, " +
        "select[multiple].ok-multiselect-source"
      )
      .forEach(enhanceMultiSelect);
  }

  /* ------------------------------------------------------------------ */
  /* 4. Search box placeholders (Russian, per model)                     */
  /* ------------------------------------------------------------------ */

  var SEARCH_HINTS = [
    {
      match: "/users/teacher/",
      text:
        "Поиск тренера по имени, email или телефону...",
    },
    {
      match: "/users/subject/",
      text: "Поиск предмета...",
    },
    {
      match: "/users/user/",
      text: "Поиск администратора...",
    },
  ];

  function initSearchHint() {
    var input = document.getElementById("searchbar");

    if (!input) return;

    var path = window.location.pathname;

    var hint = SEARCH_HINTS.filter(function (h) {
      return path.indexOf(h.match) !== -1;
    })[0];

    input.placeholder = hint
      ? hint.text
      : "Поиск...";
  }

  /* ------------------------------------------------------------------ */
  /* 5. Friendly empty states                                             */
  /* ------------------------------------------------------------------ */

  var EMPTY_STATES = [
    {
      match: "/users/teacher/",
      icon: "bi-person-badge",
      title: "Пока нет тренеров",
      text:
        "Добавьте первого тренера, чтобы начать работу.",
    },
    {
      match: "/users/subject/",
      icon: "bi-journal-bookmark",
      title: "Пока нет предметов",
      text:
        "Добавьте предмет, чтобы назначать его тренерам и группам.",
    },
    {
      match: "/users/user/",
      icon: "bi-shield-lock",
      title: "Пока нет администраторов",
      text:
        "Добавьте учётную запись администратора.",
    },
    {
      match: "/academy/student/",
      icon: "bi-people",
      title: "Пока нет студентов",
      text:
        "Добавьте первого студента вручную или импортируйте список из Excel.",
      links: [
        { href: "/admin/academy/student/add/", icon: "bi-plus-lg", label: "Добавить студента" },
        { href: "/admin/academy/student/import/", icon: "bi-upload", label: "Импортировать Excel" },
        { href: "/admin/academy/student/template/", icon: "bi-download", label: "Скачать шаблон" },
      ],
    },
  ];

  function initEmptyState() {
    var resultsBox = document.querySelector(
      "#changelist .results"
    );

    var paginator = document.querySelector(
      "#changelist .paginator"
    );

    var hasRows = document.querySelector(
      "#result_list tbody tr"
    );

    if (
      hasRows ||
      (!resultsBox &&
        !document.getElementById("changelist"))
    ) {
      return;
    }

    var changelist = document.getElementById(
      "changelist-form"
    );

    if (
      !changelist ||
      document.getElementById("result_list")
    ) {
      return;
    }

    var path = window.location.pathname;

    var state =
      EMPTY_STATES.filter(function (s) {
        return path.indexOf(s.match) !== -1;
      })[0] || {
        icon: "bi-inbox",
        title: "Список пуст",
        text: "Пока здесь нечего показать.",
      };

    var box = document.createElement("div");
    box.className = "ok-empty-state";

    var linksHtml = "";
    if (state.links && state.links.length) {
      linksHtml =
        '<div class="ok-empty-state-actions">' +
        state.links
          .map(function (link) {
            return (
              '<a class="ok-btn-secondary ok-btn-sm" href="' +
              link.href +
              '"><i class="bi ' +
              link.icon +
              '"></i> ' +
              link.label +
              "</a>"
            );
          })
          .join("") +
        "</div>";
    }

    box.innerHTML =
      '<i class="bi ' +
      state.icon +
      '"></i>' +
      "<h4>" +
      state.title +
      "</h4>" +
      "<p>" +
      state.text +
      "</p>" +
      linksHtml;

    if (paginator) {
      paginator.replaceWith(box);
    } else {
      changelist.appendChild(box);
    }
  }

  /* ------------------------------------------------------------------ */
  /* 6. Destructive bulk-action warning                                  */
  /* ------------------------------------------------------------------ */

  function initActionWarning() {
    var select = document.querySelector(
      'select[name="action"]'
    );

    if (!select) return;

    var actionsBar = select.closest(".actions");

    function update() {
      var text =
        (select.options[select.selectedIndex] || {})
          .text || "";

      var isDestructive =
        /удал|деактив|отмен/i.test(text);

      if (actionsBar) {
        actionsBar.classList.toggle(
          "ok-action-danger",
          isDestructive
        );
      }
    }

    select.addEventListener("change", update);
    update();
  }

  /* ------------------------------------------------------------------ */
  /* 7. Subject picker — checkbox card grid (Course.subjects)            */
  /* ------------------------------------------------------------------ */

  function enhanceSubjectCards(select) {
    if (select.dataset.okCardsEnhanced) return;
    select.dataset.okCardsEnhanced = "true";

    var options = Array.prototype.slice.call(select.options);
    if (options.length === 0) return;

    select.classList.add("ok-ms-native");

    var wrap = document.createElement("div");
    wrap.className = "ok-subject-cards";

    var header = document.createElement("div");
    header.className = "ok-subject-cards-header";
    header.innerHTML =
      '<i class="bi bi-journal-bookmark"></i>' +
      "<div>" +
      '<div class="ok-subject-cards-title">Выберите предметы курса</div>' +
      '<div class="ok-subject-cards-subtitle">Предметы, которые входят в курс</div>' +
      "</div>";

    var body = document.createElement("div");
    body.className = "ok-subject-cards-body";

    var searchWrap = document.createElement("div");
    searchWrap.className = "ok-subject-cards-search";
    searchWrap.innerHTML = '<i class="bi bi-search"></i>';

    var searchInput = document.createElement("input");
    searchInput.type = "text";
    searchInput.placeholder = "Поиск предмета...";
    searchInput.autocomplete = "off";
    searchWrap.appendChild(searchInput);

    var grid = document.createElement("div");
    grid.className = "ok-subject-cards-grid";

    var emptyRow = document.createElement("div");
    emptyRow.className = "ok-subject-cards-empty";
    emptyRow.innerHTML =
      '<i class="bi bi-search"></i><span>Ничего не найдено</span>';
    emptyRow.hidden = true;

    var footer = document.createElement("div");
    footer.className = "ok-subject-cards-footer";

    var cards = options.map(function (opt) {
      var label = opt.text;

      var card = document.createElement("div");
      card.className = "ok-subject-card";
      card.setAttribute("role", "checkbox");
      card.tabIndex = 0;
card.dataset.label = label.toLowerCase();
      card.innerHTML =
  '<span class="ok-subject-card-checkbox">' +
  '<input type="checkbox" tabindex="-1" aria-hidden="true">' +
  "</span>" +
  '<span class="ok-subject-card-icon"><i class="bi bi-journal-bookmark"></i></span>' +
  '<span class="ok-subject-card-title"></span>' +
  '<span class="ok-subject-card-check"><i class="bi bi-check-lg"></i></span>';

      card.querySelector(".ok-subject-card-title").textContent = label;

      var checkbox = card.querySelector('input[type="checkbox"]');

      function toggle() {
        opt.selected = !opt.selected;
        select.dispatchEvent(new Event("change", { bubbles: true }));
        sync();
      }

      card.addEventListener("click", toggle);
      card.addEventListener("keydown", function (evt) {
        if (evt.key === "Enter" || evt.key === " ") {
          evt.preventDefault();
          toggle();
        }
      });

      grid.appendChild(card);

      return { opt: opt, card: card, checkbox: checkbox };
    });

    function sync() {
      var selectedCount = 0;

      cards.forEach(function (item) {
        var selected = item.opt.selected;

        item.card.classList.toggle("selected", selected);
        item.card.setAttribute("aria-checked", selected ? "true" : "false");
        item.checkbox.checked = selected;

        if (selected) selectedCount += 1;
      });

      footer.innerHTML =
        '<i class="bi bi-check2-circle"></i>Выбрано: <strong>' +
        selectedCount +
        "</strong> из " +
        cards.length;
    }

    searchInput.addEventListener("input", function () {
      var q = searchInput.value.trim().toLowerCase();
      var visible = 0;

      cards.forEach(function (item) {
        var match = !q || item.card.dataset.label.indexOf(q) !== -1;
        item.card.classList.toggle("is-hidden", !match);
        if (match) visible += 1;
      });

      emptyRow.hidden = visible !== 0;
    });

    body.appendChild(searchWrap);
    body.appendChild(grid);
    grid.appendChild(emptyRow);
    body.appendChild(footer);

    wrap.appendChild(header);
    wrap.appendChild(body);

    select.parentNode.insertBefore(wrap, select.nextSibling);

    sync();
  }

  function initSubjectCards() {
    document
      .querySelectorAll("select[multiple].ok-subject-cards-source")
      .forEach(enhanceSubjectCards);
  }

  /* ------------------------------------------------------------------ */
  /* 8. Photo field — instant preview + "remove photo" state              */
  /* ------------------------------------------------------------------ */

  function enhancePhotoField(field) {
    if (field.dataset.okEnhanced) return;
    field.dataset.okEnhanced = "true";

    var input = field.querySelector(".ok-photo-input");
    var preview = field.querySelector(".ok-photo-preview");
    var status = field.querySelector(".ok-photo-status");
    var filename = field.querySelector(".ok-photo-filename");
    var filenameText = field.querySelector(".ok-photo-filename-text");
    var removeCheckbox = field.querySelector(".ok-photo-remove-toggle input");
    var img = preview ? preview.querySelector("img") : null;

    if (!input || !preview || !status) return;

    // Snapshot of the server-rendered state, so unchecking "remove" (having
    // picked nothing new) can put the field back exactly as it was.
    var original = {
      hasImage: field.classList.contains("ok-photo-has-image"),
      status: status.textContent,
      filenameHidden: filename ? filename.hidden : true,
      filenameText: filenameText ? filenameText.textContent : "",
    };

    function ensureImg() {
      if (!img) {
        img = document.createElement("img");
        img.alt = "";
        preview.appendChild(img);
      }
      return img;
    }

    function showNewImage(dataUrl, name) {
      ensureImg().src = dataUrl;
      field.classList.add("ok-photo-has-image");
      field.classList.remove("ok-photo-marked-removed");
      status.textContent = "Новое изображение выбрано";
      if (filename && filenameText) {
        filenameText.textContent = name;
        filename.hidden = false;
      }
    }

    function showRemoved() {
      field.classList.remove("ok-photo-has-image");
      field.classList.add("ok-photo-marked-removed");
      status.textContent = "Фотография будет удалена после сохранения";
      if (filename) filename.hidden = true;
    }

    function restoreOriginal() {
      field.classList.toggle("ok-photo-has-image", original.hasImage);
      field.classList.remove("ok-photo-marked-removed");
      status.textContent = original.status;
      if (filename) {
        filename.hidden = original.filenameHidden;
        if (filenameText) filenameText.textContent = original.filenameText;
      }
    }

    input.addEventListener("change", function () {
      var file = input.files && input.files[0];
      if (!file) return;

      if (file.type.indexOf("image/") !== 0) {
        input.value = "";
        return;
      }

      // Uncheck "delete" once a replacement is picked — the two controls
      // shouldn't fight over which one wins on submit.
      if (removeCheckbox) removeCheckbox.checked = false;

      var reader = new FileReader();
      reader.onload = function (evt) {
        showNewImage(evt.target.result, file.name);
      };
      reader.readAsDataURL(file);
    });

    if (removeCheckbox) {
      removeCheckbox.addEventListener("change", function () {
        if (removeCheckbox.checked) {
          // A replacement file, if any was pending, is discarded — the
          // checkbox now means "delete the saved photo", not "keep the new one".
          input.value = "";
          showRemoved();
        } else {
          restoreOriginal();
        }
      });
    }
  }

  function initPhotoFields() {
    document
      .querySelectorAll(".ok-photo-field")
      .forEach(enhancePhotoField);
  }

  /* ------------------------------------------------------------------ */
  /* 9. Student bulk-add — dynamic formset rows                          */
  /* ------------------------------------------------------------------ */

  function initStudentBulkAdd() {
    var table = document.getElementById("ok-student-bulk-table");
    var template = document.getElementById("ok-student-bulk-row-template");
    var addButton = document.getElementById("ok-student-add-row");
    if (!table || !template || !addButton) return;

    var body = table.querySelector("tbody");
    var totalForms = document.querySelector('input[name="form-TOTAL_FORMS"]');
    if (!body || !totalForms) return;

    addButton.addEventListener("click", function () {
      var index = parseInt(totalForms.value, 10) || 0;
      var row = template.content.firstElementChild.cloneNode(true);

      row.querySelectorAll("[name]").forEach(function (field) {
        field.name = field.name.replace("__prefix__", index);
      });
      var indexCell = row.querySelector(".ok-student-row-index");
      if (indexCell) indexCell.textContent = index + 1;

      body.appendChild(row);
      totalForms.value = index + 1;
    });

    // Removing a row just drops its inputs from the DOM (and so from the
    // POST body) instead of touching TOTAL_FORMS — the server treats a
    // missing index exactly like an all-blank row and silently skips it,
    // so indices never need to stay contiguous.
    body.addEventListener("click", function (event) {
      var button = event.target.closest(".ok-student-remove-row");
      if (!button) return;
      var row = button.closest(".ok-student-bulk-row");
      if (row) row.remove();
    });
  }

  /* ------------------------------------------------------------------ */
  /* 10. Group Workspace — "Добавить существующих студентов" modal        */
  /* ------------------------------------------------------------------ */

  // Global (not just inside this IIFE) because the modal's search input/
  // "select all" checkbox call these directly via inline on*= attributes —
  // simplest wiring for a small, single-purpose modal with no other JS.
  window.okFilterModalStudents = function (query) {
    var needle = (query || "").trim().toLowerCase();
    document.querySelectorAll(".ok-modal-student-row").forEach(function (row) {
      var haystack = row.getAttribute("data-name") || "";
      row.hidden = needle.length > 0 && haystack.indexOf(needle) === -1;
    });
  };

  window.okToggleAllModalStudents = function (checked) {
    document.querySelectorAll(".ok-modal-student-row:not([hidden]) input[type=checkbox]").forEach(
      function (checkbox) {
        checkbox.checked = checked;
      }
    );
  };

  /* ------------------------------------------------------------------ */
  /* Initialize                                                          */
  /* ------------------------------------------------------------------ */

  document.addEventListener(
    "DOMContentLoaded",
    function () {
      initLightTheme();
      initPasswordToggles();
      initMultiSelects();
      initSubjectCards();
      initPhotoFields();
      initStudentBulkAdd();
      initSearchHint();
      initEmptyState();
      initActionWarning();
    }
  );
})();
 (function () {
    function translateSelect2() {
        document.querySelectorAll(".select2-selection__rendered").forEach(function (el) {
            if (el.textContent.trim() === "- Select an option -") {
                el.textContent = "- Выберите вариант -";
            }
        });
    }

    translateSelect2();

    const observer = new MutationObserver(translateSelect2);

    observer.observe(document.body, {
        childList: true,
        subtree: true,
        characterData: true,
    });
})();