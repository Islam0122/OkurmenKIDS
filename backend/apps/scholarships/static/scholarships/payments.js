/*
 * «Стипендии» — payment workflow (admin/scholarships/scholarshipaward/change_list.html).
 *
 * Row data lives in data-* attributes on each <tr>; the two <dialog>s are
 * shared and filled from the row that was clicked. The server re-checks
 * everything (services.payments): a paid or not-yet-approved award is never
 * paid, whatever this script sends.
 */
(function () {
  "use strict";

  var NBSP = " ";

  function som(value) {
    var n = Math.round(value || 0);
    return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, NBSP) + NBSP + "сом";
  }

  function plural(n, one, few, many) {
    var mod10 = n % 10, mod100 = n % 100;
    if (mod10 === 1 && mod100 !== 11) return one;
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
    return many;
  }

  function fill(dialog, data) {
    dialog.querySelectorAll("[data-f]").forEach(function (el) {
      var value = data[el.getAttribute("data-f")];
      el.textContent = value ? value : "—";
    });
  }

  function init(root) {
    var payModal = document.getElementById("ok-pay-modal");
    var detailsModal = document.getElementById("ok-pay-details");
    var rows = Array.prototype.slice.call(root.querySelectorAll("[data-ok-pay-row]"));
    var all = root.querySelector("[data-ok-pay-all]");
    var bulk = root.querySelector("[data-ok-pay-bulk]");
    var countEl = root.querySelector("[data-ok-pay-count]");
    var sumEl = root.querySelector("[data-ok-pay-sum]");
    var selectionEl = root.querySelector("[data-ok-pay-selection]");

    function rowOf(el) { return el.closest("tr[data-award]"); }

    function selected() {
      return rows.filter(function (box) { return box.checked; }).map(rowOf);
    }

    function total(trs) {
      return trs.reduce(function (acc, tr) { return acc + (parseFloat(tr.dataset.amount) || 0); }, 0);
    }

    function sync() {
      var chosen = selected();
      if (countEl) countEl.textContent = chosen.length;
      if (sumEl) sumEl.textContent = som(total(chosen));
      if (bulk) bulk.disabled = chosen.length === 0;
      if (selectionEl) selectionEl.classList.toggle("has-selection", chosen.length > 0);
      rows.forEach(function (box) { rowOf(box).classList.toggle("is-selected", box.checked); });
      if (all) {
        all.checked = rows.length > 0 && chosen.length === rows.length;
        all.indeterminate = chosen.length > 0 && chosen.length < rows.length;
      }
    }

    if (all) {
      if (!rows.length) all.disabled = true;
      all.addEventListener("change", function () {
        rows.forEach(function (box) { box.checked = all.checked; });
        sync();
      });
    }
    rows.forEach(function (box) { box.addEventListener("change", sync); });

    function openPay(trs) {
      if (!payModal || !trs.length) return;
      var ids = payModal.querySelector("[data-ok-pay-ids]");
      ids.innerHTML = "";
      trs.forEach(function (tr) {
        var input = document.createElement("input");
        input.type = "hidden";
        input.name = "award";
        input.value = tr.dataset.award;
        ids.appendChild(input);
      });
      var single = trs.length === 1;
      payModal.querySelector("[data-ok-pay-single]").hidden = !single;
      var text = payModal.querySelector("[data-ok-pay-bulk-text]");
      text.hidden = single;
      payModal.querySelector("[data-ok-pay-title]").textContent = single ? "Выдача стипендии" : "Массовая выдача";
      if (single) {
        var d = trs[0].dataset;
        fill(payModal, { student: d.student, group: d.group, period: d.period, amount: d.amountLabel });
      } else {
        text.textContent = "Вы подтверждаете выплату " + trs.length + " " +
          plural(trs.length, "ученику", "ученикам", "ученикам") + " на сумму " + som(total(trs)) + "?";
      }
      payModal.querySelector("textarea[name=comment]").value = "";
      var submit = payModal.querySelector('[type="submit"]');
      submit.disabled = false;
      submit.classList.remove("is-loading");
      payModal.showModal();
    }

    root.addEventListener("click", function (evt) {
      var one = evt.target.closest("[data-ok-pay-one]");
      if (one) { openPay([rowOf(one)]); return; }
      if (evt.target.closest("[data-ok-pay-bulk]")) { openPay(selected()); return; }
      var details = evt.target.closest("[data-ok-pay-details]");
      if (details && detailsModal) {
        var tr = rowOf(details);
        fill(detailsModal, tr.dataset);
        var cancel = detailsModal.querySelector("[data-ok-cancel-form]");
        var urlHolder = root.querySelector("[data-ok-cancel-url]");
        if (cancel && urlHolder) {
          cancel.action = urlHolder.getAttribute("data-ok-cancel-url").replace(/\/0\//, "/" + tr.dataset.award + "/");
        }
        detailsModal.showModal();
      }
    });

    [payModal, detailsModal].forEach(function (dialog) {
      if (!dialog) return;
      dialog.addEventListener("click", function (evt) {
        // Close buttons, and a click on the backdrop (the dialog box itself).
        if (evt.target.closest("[data-ok-close]") || evt.target === dialog) dialog.close();
      });
    });

    // One submit only: a double click must not send the form twice.
    var form = root.querySelector("[data-ok-pay-form]");
    if (form) {
      form.addEventListener("submit", function () {
        var submit = form.querySelector('[type="submit"]');
        window.setTimeout(function () { submit.disabled = true; }, 0);
        submit.classList.add("is-loading");
      });
    }

    // Back from the redirect: highlight the row that was just paid.
    if (location.hash && /^#aw-\d+$/.test(location.hash)) {
      var target = document.getElementById(location.hash.slice(1));
      if (target) {
        target.classList.add("is-just-paid");
        target.scrollIntoView({ block: "center" });
      }
    }

    sync();
  }

  document.addEventListener("DOMContentLoaded", function () {
    var root = document.querySelector("[data-ok-pay]");
    if (root) init(root);
  });
  // Coming back via the back/forward cache: never keep stale checkboxes.
  window.addEventListener("pageshow", function (evt) {
    if (evt.persisted) window.location.reload();
  });
})();
