/* «Сессии» admin section.
 *  - Session form: show the picked test's facts; load the picked group's
 *    students into the roster checklist; «Все студенты» locks the list.
 *  - Live parts ([data-oks-live]): re-fetch the server-rendered fragment
 *    every N seconds while the tab is visible (polling fallback — the
 *    project has no WebSocket infrastructure).
 *  - Copy buttons ([data-oks-copy]).
 * Text from the server is inserted with textContent / DOM nodes only. */
(function () {
  "use strict";

  // -- Session form ------------------------------------------------------------
  var form = document.querySelector("[data-oks-form]");
  if (form) {
    var infoNode = document.getElementById("oks-test-info");
    var testInfo = infoNode ? JSON.parse(infoNode.textContent) : {};
    var testSelect = form.querySelector("select[name=test]");
    var card = form.querySelector("[data-oks-test-card]");

    var plural = function (n, one, few, many) {
      var a = Math.abs(n) % 100, b = a % 10;
      if (a > 10 && a < 20) return many;
      if (b > 1 && b < 5) return few;
      return b === 1 ? one : many;
    };

    var showTest = function () {
      var info = testSelect && testInfo[testSelect.value];
      if (!card) return;
      card.hidden = !info;
      if (!info) return;
      card.querySelector("[data-oks-test-title]").textContent = testSelect.options[testSelect.selectedIndex].text;
      var facts = [
        info.level,
        info.questions + " " + plural(info.questions, "вопрос", "вопроса", "вопросов"),
        info.time ? info.time + " минут" : "без ограничения времени",
        "Проходной балл: " + info.passing + "%"
      ];
      if (info.subject) facts.unshift(info.subject);
      card.querySelector("[data-oks-test-facts]").textContent = facts.join(" · ");
    };
    if (testSelect) { testSelect.addEventListener("change", showTest); showTest(); }

    var roster = form.querySelector("[data-oks-roster]");
    var groupSelect = form.querySelector("select[name=group]");
    var allBox = form.querySelector("input[name=all_students]");
    var list = roster && roster.querySelector("[data-oks-roster-list]");
    var countNode = roster && roster.querySelector("[data-oks-roster-count]");

    var syncAll = function () {
      if (!list || !allBox) return;
      list.classList.toggle("is-all", allBox.checked);
      list.querySelectorAll("input[name=students]").forEach(function (box) {
        if (allBox.checked) box.checked = true;
      });
    };

    var renderStudents = function (students) {
      list.textContent = "";
      if (!students.length) {
        var empty = document.createElement("p");
        empty.className = "okt-muted";
        empty.textContent = "В группе нет активных студентов.";
        list.appendChild(empty);
      }
      students.forEach(function (s) {
        var label = document.createElement("label");
        label.className = "oks-roster__item";
        var box = document.createElement("input");
        box.type = "checkbox";
        box.name = "students";
        box.value = String(s.id);
        box.checked = true;
        var name = document.createElement("span");
        name.textContent = s.name;
        label.appendChild(box);
        label.appendChild(name);
        list.appendChild(label);
      });
      if (countNode) countNode.textContent = students.length + " " + plural(students.length, "студент", "студента", "студентов");
      syncAll();
    };

    if (groupSelect && roster) {
      var baseUrl = roster.getAttribute("data-students-url");
      groupSelect.addEventListener("change", function () {
        if (!groupSelect.value) { renderStudents([]); return; }
        fetch(baseUrl.replace(/\/0\/$/, "/" + encodeURIComponent(groupSelect.value) + "/"), { credentials: "same-origin" })
          .then(function (r) { return r.json(); })
          .then(function (data) { renderStudents(data.students || []); })
          .catch(function () { renderStudents([]); });
      });
    }
    if (allBox) allBox.addEventListener("change", syncAll);
    if (list) {
      list.addEventListener("change", function (event) {
        if (event.target.name === "students" && !event.target.checked && allBox) allBox.checked = false;
        list.classList.toggle("is-all", allBox && allBox.checked);
      });
    }
    syncAll();
  }

  // -- Live refresh ------------------------------------------------------------
  document.querySelectorAll("[data-oks-live]").forEach(function (box) {
    var url = box.getAttribute("data-oks-live");
    var every = Math.max(3, parseInt(box.getAttribute("data-oks-every"), 10) || 5) * 1000;
    var busy = false;
    var refresh = function () {
      if (busy || document.hidden) return;
      busy = true;
      fetch(url, { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
        .then(function (r) { if (!r.ok) throw new Error(); return r.text(); })
        .then(function (html) {
          // Our own server-rendered (auto-escaped) fragment.
          var doc = new DOMParser().parseFromString(html, "text/html");
          box.replaceChildren.apply(box, Array.prototype.slice.call(doc.body.childNodes));
        })
        .catch(function () { /* keep the last good state; try again next tick */ })
        .then(function () { busy = false; });
    };
    window.setInterval(refresh, every);
    document.addEventListener("visibilitychange", function () { if (!document.hidden) refresh(); });
  });

  // -- Copy --------------------------------------------------------------------
  document.addEventListener("click", function (event) {
    var button = event.target.closest && event.target.closest("[data-oks-copy]");
    if (!button) return;
    var input = document.getElementById(button.getAttribute("data-oks-copy"));
    if (!input) return;
    input.select();
    var done = function () {
      var label = button.querySelector("span");
      if (label) { var old = label.textContent; label.textContent = "Скопировано"; window.setTimeout(function () { label.textContent = old; }, 1500); }
    };
    if (navigator.clipboard) navigator.clipboard.writeText(input.value).then(done, function () { document.execCommand("copy"); done(); });
    else { document.execCommand("copy"); done(); }
  });
})();
