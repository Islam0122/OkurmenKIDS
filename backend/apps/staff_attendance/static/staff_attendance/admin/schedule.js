/* Личное расписание сотрудника (Django admin).
 * Только удобство ввода: Select2-поиск сотрудника, карточки дней, показ строк
 * выбранных дней, копирование часов, подсчёт часов. Все значения проверяет сервер. */
(function () {
  "use strict";

  var DAY_NAMES = ["понедельник", "вторник", "среду", "четверг", "пятницу", "субботу", "воскресенье"];

  function minutes(value) {
    var m = /^(\d{1,2}):(\d{2})/.exec(value || "");
    return m ? parseInt(m[1], 10) * 60 + parseInt(m[2], 10) : null;
  }

  function formatHours(total) {
    var h = Math.floor(total / 60), m = total % 60;
    return m ? h + " ч " + m + " мин" : h + " ч";
  }

  var SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

  // [0,1,2,3,4] → ["Пн–Пт"], [0,2,4] → ["Пн","Ср","Пт"] — как format_days в admin.py.
  function compressDays(days) {
    var out = [], run = [];
    function flush() {
      if (run.length >= 3) out.push(SHORT[run[0]] + "–" + SHORT[run[run.length - 1]]);
      else run.forEach(function (d) { out.push(SHORT[d]); });
      run = [];
    }
    days.slice().sort().forEach(function (d) {
      if (run.length && d !== run[run.length - 1] + 1) flush();
      run.push(d);
    });
    flush();
    return out;
  }

  function initEmployeeSelect(form) {
    var $ = window.django && window.django.jQuery;
    var select = form.querySelector("[data-employee-select]");
    if (!$ || !select || !$.fn.select2) return;
    var holder = select.closest("[data-current-user]");
    var current = holder ? holder.getAttribute("data-current-user") : "";

    function card(item) {
      if (item.loading) return $("<span>").text(item.text);
      if (!item.id) return item.text;
      var $root = $('<div class="ok-ws-opt">');
      $("<div class=\"ok-ws-opt-name\">").text(item.full_name || item.text).appendTo($root);
      var meta = [item.position, item.department].filter(Boolean).join(" · ");
      if (meta) $("<div class=\"ok-ws-opt-meta\">").text(meta).appendTo($root);
      if (item.has_schedule) $("<div class=\"ok-ws-opt-flag\">").text("Уже есть личное расписание").appendTo($root);
      return $root;
    }

    $(select).select2({
      width: "100%",
      language: "ru",
      placeholder: select.getAttribute("data-placeholder"),
      allowClear: false,
      minimumInputLength: 0,
      ajax: {
        url: select.getAttribute("data-search-url"),
        dataType: "json",
        delay: 250,
        data: function (params) { return { term: params.term || "", page: params.page || 1, current: current }; }
      },
      templateResult: card,
      templateSelection: function (item) {
        if (!item.id) return item.text;
        if (!item.full_name) return item.text;
        return [item.full_name, item.position, item.department].filter(Boolean).join(" · ");
      }
    });
  }

  function init(form) {
    initEmployeeSelect(form);

    var dayInputs = Array.prototype.slice.call(form.querySelectorAll('input[name="work_days"]'));
    var hoursRows = form.querySelectorAll("[data-hours-row]");
    var breakRows = form.querySelectorAll("[data-break-row]");
    var emptyNote = form.querySelector("[data-hours-empty]");
    var copyBtn = form.querySelector("[data-copy-hours]");
    var copyLabel = form.querySelector("[data-copy-label]");
    var weekTotal = form.querySelector("[data-week-total]");
    var summary = form.querySelector("[data-ws-summary]");

    function field(day, part) { return form.elements["d" + day + "_" + part]; }
    function selected() {
      return dayInputs.filter(function (i) { return i.checked; }).map(function (i) { return parseInt(i.value, 10); });
    }
    function breakMode() {
      var checked = form.querySelector('input[name="break_mode"]:checked');
      return checked ? checked.value : "none";
    }
    function sourceDay(days) { return days.indexOf(0) !== -1 ? 0 : days[0]; }

    function breakFor(day, mode) {
      if (mode === "same") return [minutes(form.elements.break_start.value), minutes(form.elements.break_end.value)];
      if (mode === "per_day") return [minutes(field(day, "break_start").value), minutes(field(day, "break_end").value)];
      return [null, null];
    }

    function refresh() {
      var days = selected();
      var mode = breakMode();
      dayInputs.forEach(function (input) {
        var cardEl = input.closest("[data-day-card]");
        if (cardEl) cardEl.classList.toggle("is-on", input.checked);
      });
      Array.prototype.forEach.call(hoursRows, function (row) {
        row.hidden = days.indexOf(parseInt(row.getAttribute("data-hours-row"), 10)) === -1;
      });
      Array.prototype.forEach.call(breakRows, function (row) {
        row.hidden = days.indexOf(parseInt(row.getAttribute("data-break-row"), 10)) === -1;
      });
      if (emptyNote) emptyNote.hidden = days.length > 0;
      Array.prototype.forEach.call(form.querySelectorAll("[data-break-panel]"), function (panel) {
        panel.hidden = panel.getAttribute("data-break-panel") !== mode;
      });

      var src = sourceDay(days);
      if (copyBtn) {
        copyBtn.disabled = days.length < 2;
        copyLabel.textContent = "Скопировать " + (src === undefined ? "понедельник" : DAY_NAMES[src]) + " на все дни";
      }

      var total = 0, complete = true, spans = {};
      days.forEach(function (day) {
        var start = minutes(field(day, "start").value), end = minutes(field(day, "end").value);
        var row = form.querySelector('[data-hours-row="' + day + '"] [data-duration]');
        var b = breakFor(day, mode);
        var brk = (b[0] !== null && b[1] !== null && b[1] > b[0]) ? b[1] - b[0] : 0;
        var bcell = form.querySelector('[data-break-row="' + day + '"] [data-break-duration]');
        if (bcell) bcell.textContent = brk ? brk + " мин" : "—";
        if (start === null || end === null || end <= start) {
          complete = false;
          if (row) { row.textContent = end !== null && start !== null ? "ошибка" : "—"; row.classList.add("is-bad"); }
          return;
        }
        var worked = end - start - brk;
        total += worked;
        if (row) { row.textContent = formatHours(worked); row.classList.remove("is-bad"); }
        spans[field(day, "start").value + "–" + field(day, "end").value] = true;
      });

      if (weekTotal) {
        weekTotal.textContent = days.length
          ? "Итого за неделю: " + formatHours(total) + (mode !== "none" ? " (без перерывов)" : "") +
            (complete ? "" : " — проверьте часы, отмеченные как «ошибка» или «—»")
          : "";
      }
      if (summary) {
        var labels = compressDays(days);
        var keys = Object.keys(spans);
        summary.textContent = days.length
          ? labels.join(", ") + " · " + (keys.length === 1 ? keys[0] : "часы по дням") + " · " + formatHours(total) + "/нед"
          : "Дни не выбраны";
      }
    }

    // Пресеты дней.
    Array.prototype.forEach.call(form.querySelectorAll("[data-days-preset]"), function (btn) {
      btn.addEventListener("click", function () {
        var preset = btn.getAttribute("data-days-preset");
        var set = preset ? preset.split(",") : [];
        dayInputs.forEach(function (input) { input.checked = set.indexOf(input.value) !== -1; });
        refresh();
      });
    });

    // Копирование часов понедельника (или первого рабочего дня) на остальные выбранные дни.
    if (copyBtn) {
      copyBtn.addEventListener("click", function () {
        var days = selected();
        var src = sourceDay(days);
        if (src === undefined) return;
        var parts = ["start", "end"];
        if (breakMode() === "per_day") parts.push("break_start", "break_end");
        days.forEach(function (day) {
          if (day === src) return;
          parts.forEach(function (part) { field(day, part).value = field(src, part).value; });
        });
        refresh();
        copyBtn.classList.add("is-done");
        setTimeout(function () { copyBtn.classList.remove("is-done"); }, 1200);
      });
    }

    form.addEventListener("change", refresh);
    form.addEventListener("input", refresh);
    refresh();
  }

  function boot() {
    var form = document.querySelector("[data-ws-form]");
    if (form) init(form);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
