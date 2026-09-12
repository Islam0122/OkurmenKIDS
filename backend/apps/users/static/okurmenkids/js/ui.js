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

    var wrap = document.createElement("div");
    wrap.className = "ok-multiselect";

    var searchBar = document.createElement("div");
    searchBar.className = "ok-ms-search";
    searchBar.innerHTML =
      '<i class="bi bi-search"></i>';

    var searchInput = document.createElement("input");
    searchInput.type = "text";
    searchInput.placeholder = "Поиск...";
    searchInput.autocomplete = "off";

    searchBar.appendChild(searchInput);

    var chips = document.createElement("div");
    chips.className = "ok-ms-chips";

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

    wrap.appendChild(searchBar);
    wrap.appendChild(chips);
    wrap.appendChild(panel);

    panel.appendChild(emptyRow);

    wrap.appendChild(footer);

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

    box.innerHTML =
      '<i class="bi ' +
      state.icon +
      '"></i>' +
      "<h4>" +
      state.title +
      "</h4>" +
      "<p>" +
      state.text +
      "</p>";

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
  /* Initialize                                                          */
  /* ------------------------------------------------------------------ */

  document.addEventListener(
    "DOMContentLoaded",
    function () {
      initLightTheme();
      initPasswordToggles();
      initMultiSelects();
      initSearchHint();
      initEmptyState();
      initActionWarning();
    }
  );
})();