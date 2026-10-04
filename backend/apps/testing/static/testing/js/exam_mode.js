/* EXAM MODE — the student portal's attempt page (testing/student/attempt.html).
 *
 * What it does:
 *   - one question at a time, «Назад» / «Следующий», the numbered navigation
 *     panel (не отвечен / отвечен / текущий / пропущен), «Вопрос N из M»;
 *   - the countdown (HH:MM:SS), re-synced with the server's remaining time on
 *     every autosave; at 00:00 the form is sent with timed_out=1;
 *   - autosave: changed answers go to PATCH …/answers/ (debounced, plus a
 *     heartbeat every 15 s); offline, they wait in localStorage and are sent
 *     when the connection is back;
 *   - restrictions while the exam is active: copy / cut / paste, context menu,
 *     selecting question text, Ctrl+A outside answer fields, DevTools
 *     shortcuts, tab switches (visibilitychange), leaving fullscreen (when the
 *     test requires it) and leaving the page (beforeunload). Each attempt is
 *     reported to …/events/; the server counts them and decides — e.g. it
 *     ends the exam once tab switches exceed the test's limit.
 *
 * None of this is security: a browser can't stop DevTools, a second device
 * or a determined student. The server owns the deadline, the answers and the
 * verdict; this file only prevents casual mistakes and makes them visible.
 * Everything is switched off once the exam is submitted. */
(function () {
  "use strict";

  var form = document.querySelector("[data-xm-exam]");
  if (!form) return;
  var questions = Array.prototype.slice.call(form.querySelectorAll("[data-xm-q]"));
  if (!questions.length) return;

  var $ = function (selector, root) { return (root || document).querySelector(selector); };
  var attemptId = form.getAttribute("data-attempt");
  var answersUrl = form.getAttribute("data-answers-url");
  var eventsUrl = form.getAttribute("data-events-url");
  var stateUrl = form.getAttribute("data-state-url");
  var resultUrl = form.getAttribute("data-result-url");
  var requireFullscreen = form.getAttribute("data-require-fullscreen") === "1";
  var maxSwitchesAttr = form.getAttribute("data-max-tab-switches");
  var maxSwitches = maxSwitchesAttr === "" || maxSwitchesAttr === null ? null : parseInt(maxSwitchesAttr, 10);
  var csrf = $("input[name=csrfmiddlewaretoken]", form).value;
  var pendingKey = "xm-pending-" + attemptId;

  var examActive = true;     // restrictions on; false once submitted / closed
  var submitting = false;
  var index = 0;
  var visited = {};

  // -- Answers --------------------------------------------------------------
  function qid(section) { return section.getAttribute("data-qid"); }
  function isChoice(section) { var t = section.getAttribute("data-type"); return t === "single_choice" || t === "multiple_choice"; }

  function answerOf(section) {
    if (isChoice(section)) {
      var options = [];
      section.querySelectorAll("input[name^=answer_]").forEach(function (input) { if (input.checked) options.push(input.value); });
      return { options: options };
    }
    var field = section.querySelector("textarea[name^=answer_], input[name^=answer_]");
    return { text: field ? field.value : "" };
  }

  function applyAnswer(section, answer) {
    if (!answer) return;
    if (isChoice(section)) {
      var chosen = answer.options || [];
      section.querySelectorAll("input[name^=answer_]").forEach(function (input) { input.checked = chosen.indexOf(input.value) !== -1; });
    } else {
      var field = section.querySelector("textarea[name^=answer_], input[name^=answer_]");
      if (field && typeof answer.text === "string") { field.value = answer.text; field.dispatchEvent(new Event("input")); }
    }
  }

  function isAnswered(section) {
    var a = answerOf(section);
    return a.options ? a.options.length > 0 : a.text.trim() !== "";
  }

  function answeredCount() { return questions.filter(isAnswered).length; }

  // -- Navigation -------------------------------------------------------------
  var navButtons = Array.prototype.slice.call(form.querySelectorAll("[data-xm-goto]"));
  var prevBtn = $("[data-xm-prev]", form), nextBtn = $("[data-xm-next]", form), finishBtn = $("[data-xm-finish]", form);
  var progressEl = $("[data-xm-progress]"), trackEl = $("[data-xm-track]"), answeredEl = $("[data-xm-answered]", form);

  function renderNav() {
    navButtons.forEach(function (button, n) {
      var answered = isAnswered(questions[n]);
      button.classList.toggle("is-current", n === index);
      button.classList.toggle("is-answered", answered);
      button.classList.toggle("is-skipped", !answered && visited[n] && n !== index);
      button.setAttribute("aria-current", n === index ? "step" : "false");
    });
    var count = answeredCount();
    answeredEl.textContent = count + " / " + questions.length;
    trackEl.style.width = (count / questions.length * 100) + "%";
  }

  function show(i) {
    var target = Math.max(0, Math.min(i, questions.length - 1));
    if (target !== index) visited[index] = true;
    index = target;
    questions.forEach(function (q, n) { q.hidden = n !== index; });
    var last = index === questions.length - 1;
    prevBtn.disabled = index === 0;
    nextBtn.hidden = last;
    finishBtn.hidden = !last;
    progressEl.innerHTML = "Вопрос <strong>" + (index + 1) + "</strong> из " + questions.length;
    renderNav();
    var title = questions[index].querySelector(".xm-q__text");
    if (title) { title.setAttribute("tabindex", "-1"); title.focus({ preventScroll: true }); }
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  prevBtn.addEventListener("click", function () { show(index - 1); });
  nextBtn.addEventListener("click", function () { show(index + 1); });
  navButtons.forEach(function (button) {
    button.addEventListener("click", function () { show(parseInt(button.getAttribute("data-xm-goto"), 10)); });
  });

  // -- Timer --------------------------------------------------------------------
  var timerEl = $("[data-xm-timer]");
  var secondsAttr = form.getAttribute("data-seconds-left");
  var deadline = secondsAttr === null ? null : Date.now() + parseInt(secondsAttr, 10) * 1000;

  function secondsLeft() { return deadline === null ? null : Math.max(0, Math.round((deadline - Date.now()) / 1000)); }
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function formatTime(total) {
    if (total === null) return "без лимита";
    return pad(Math.floor(total / 3600)) + ":" + pad(Math.floor(total % 3600 / 60)) + ":" + pad(total % 60);
  }
  function syncDeadline(remaining) {
    if (deadline === null || typeof remaining !== "number") return;
    var serverDeadline = Date.now() + remaining * 1000;
    if (Math.abs(serverDeadline - deadline) > 2000) deadline = serverDeadline;  // the server's clock wins
  }

  if (deadline !== null && timerEl) {
    var tick = function () {
      var left = secondsLeft();
      timerEl.textContent = formatTime(left);
      timerEl.parentNode.classList.toggle("is-low", left <= 300);
      if (left === 0) { window.clearInterval(timerHandle); autoSubmit(); }
    };
    var timerHandle = window.setInterval(tick, 1000);
    tick();
  }

  // -- Autosave -----------------------------------------------------------------
  var netEl = $("[data-xm-net]"), savedEl = $("[data-xm-saved]");
  var pending = loadPending();
  var saving = false, saveTimer = null;

  function loadPending() {
    try { return JSON.parse(window.localStorage.getItem(pendingKey) || "{}") || {}; } catch (e) { return {}; }
  }
  function storePending() {
    try {
      if (Object.keys(pending).length) window.localStorage.setItem(pendingKey, JSON.stringify(pending));
      else window.localStorage.removeItem(pendingKey);
    } catch (e) { /* storage unavailable */ }
  }
  function setOffline(offline, text) {
    netEl.hidden = !offline;
    if (offline) {
      netEl.lastChild.textContent = text || "Нет соединения — ответы сохраняются на устройстве";
      savedEl.hidden = true;
    }
  }
  function showSaved() {
    savedEl.hidden = false;
    savedEl.lastElementChild.textContent = "Сохранено " + new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  }

  function markChanged(section) {
    pending[qid(section)] = answerOf(section);
    storePending();
    renderNav();
    window.clearTimeout(saveTimer);
    saveTimer = window.setTimeout(save, 800);
  }

  function request(url, options) {
    options.credentials = "same-origin";
    options.headers = Object.assign({ "X-CSRFToken": csrf, "X-Requested-With": "XMLHttpRequest" }, options.headers || {});
    return fetch(url, options).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) { return { status: response.status, data: data }; });
    });
  }

  function handleClosed(data) {
    stopExam();
    clearPending();
    if (data && data.terminated) {
      showEnded("Экзамен завершён из-за превышения допустимого количества нарушений.", data.result_url);
    } else {
      window.location.href = (data && data.result_url) || resultUrl;
    }
  }

  function save() {
    if (saving || submitting) return Promise.resolve();
    var sent = pending;
    var snapshot = JSON.stringify(sent);
    saving = true;
    return request(answersUrl, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answers: sent, current: index + 1 }),
    }).then(function (result) {
      saving = false;
      if (result.status === 200) {
        // Drop only what was sent and hasn't changed since.
        var sentNow = JSON.parse(snapshot);
        Object.keys(sentNow).forEach(function (key) {
          if (JSON.stringify(pending[key]) === JSON.stringify(sentNow[key])) delete pending[key];
        });
        storePending();
        setOffline(false);
        if (Object.keys(sentNow).length) showSaved();
        syncDeadline(result.data.remaining_seconds);
        updateSwitches(result.data);
      } else if (result.status === 409 && result.data.closed) {
        handleClosed(result.data);
      } else if (result.status === 409) {
        setOffline(true, result.data.error || "Сессия на паузе");
      } else if (result.status === 401) {
        setOffline(true, "Сессия входа истекла — войдите снова; ответы сохранены на устройстве");
      } else {
        setOffline(true, result.data.error || "Не удалось сохранить ответ");
      }
    }).catch(function () {
      saving = false;
      setOffline(true);
    });
  }

  function clearPending() { pending = {}; storePending(); }

  form.addEventListener("input", function (event) {
    var section = event.target.closest && event.target.closest("[data-xm-q]");
    if (section) markChanged(section);
  });
  form.addEventListener("change", function (event) {
    var section = event.target.closest && event.target.closest("[data-xm-q]");
    if (section) markChanged(section);
  });
  // Heartbeat: keeps the teacher's monitoring live and the timer in sync.
  window.setInterval(function () { if (examActive && !document.hidden) save(); }, 15000);
  window.addEventListener("online", function () { setOffline(false); save(); });
  window.addEventListener("offline", function () { setOffline(true); });

  // -- Warnings, modals ---------------------------------------------------------
  var warning = $("[data-xm-warning]");
  var warningFullscreenBtn = $("[data-xm-w-fullscreen]");
  function showWarning(title, text, offerFullscreen) {
    $("[data-xm-w-title]").textContent = title;
    $("[data-xm-w-text]").textContent = text;
    warningFullscreenBtn.hidden = !offerFullscreen;
    warning.hidden = false;
    $("[data-xm-w-ok]").focus();
  }
  $("[data-xm-w-ok]").addEventListener("click", function () { warning.hidden = true; });
  warningFullscreenBtn.addEventListener("click", function () { warning.hidden = true; enterFullscreen(); });

  function showEnded(text, link) {
    $("[data-xm-ended-text]").textContent = text;
    if (link) $("[data-xm-ended-link]").href = link;
    [warning, $("[data-xm-confirm]"), $("[data-xm-start-fullscreen]")].forEach(function (el) { el.hidden = true; });
    $("[data-xm-ended]").hidden = false;
  }

  var switchesEl = $("[data-xm-switches]", form);
  var switches = parseInt(form.getAttribute("data-tab-switches") || "0", 10);
  function updateSwitches(data) {
    if (!data || typeof data.tab_switch_count !== "number") return;
    switches = data.tab_switch_count;
    switchesEl.textContent = switches + (maxSwitches === null ? "" : " / " + maxSwitches);
  }

  var toastEl = null, toastTimer = null;
  function toast(text) {
    if (!toastEl) {
      toastEl = document.createElement("div");
      toastEl.className = "sp-alert sp-alert--warn";
      toastEl.setAttribute("role", "status");
      toastEl.style.cssText = "position:fixed;left:50%;bottom:24px;transform:translateX(-50%);z-index:90;box-shadow:0 8px 24px rgba(0,0,0,.18);margin:0;max-width:calc(100% - 32px)";
      toastEl.innerHTML = '<i class="bi bi-lock" aria-hidden="true"></i><span></span>';
      document.body.appendChild(toastEl);
    }
    toastEl.lastChild.textContent = text;
    toastEl.hidden = false;
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(function () { toastEl.hidden = true; }, 2500);
  }

  // -- Event reporting ----------------------------------------------------------
  var lastSent = {};
  function report(type, force) {
    if (!examActive) return Promise.resolve(null);
    var now = Date.now();
    if (!force && lastSent[type] && now - lastSent[type] < 1500) return Promise.resolve(null);  // no flood
    lastSent[type] = now;
    return request(eventsUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event_type: type, metadata: { question: index + 1 } }),
      keepalive: true,
    }).then(function (result) {
      if (result.status === 409 && result.data.closed) { handleClosed(result.data); return null; }
      if (result.status === 200) updateSwitches(result.data);
      return result.data;
    }).catch(function () { return null; });
  }

  // -- Restrictions -----------------------------------------------------------
  function inAnswerField(target) {
    return target && target.closest && !!target.closest("textarea[name^=answer_], input[type=text][name^=answer_]");
  }
  function blocked(event, type, message) {
    if (!examActive) return;
    event.preventDefault();
    toast(message);
    report(type);
  }

  document.addEventListener("copy", function (e) { blocked(e, "COPY_ATTEMPT", "Копирование запрещено во время экзамена"); }, true);
  document.addEventListener("cut", function (e) { blocked(e, "CUT_ATTEMPT", "Вырезание запрещено во время экзамена"); }, true);
  document.addEventListener("paste", function (e) { blocked(e, "PASTE_ATTEMPT", "Вставка запрещена во время экзамена"); }, true);
  document.addEventListener("contextmenu", function (e) { blocked(e, "CONTEXT_MENU_ATTEMPT", "Контекстное меню недоступно во время экзамена"); }, true);
  document.addEventListener("drop", function (e) { blocked(e, "PASTE_ATTEMPT", "Перетаскивание текста запрещено во время экзамена"); }, true);
  document.addEventListener("dragstart", function (e) { if (examActive) e.preventDefault(); }, true);
  document.addEventListener("selectstart", function (e) {
    // Question text can't be selected; answer fields stay fully editable.
    if (examActive && !inAnswerField(e.target)) e.preventDefault();
  }, true);

  document.addEventListener("keydown", function (e) {
    if (!examActive) return;
    var key = (e.key || "").toLowerCase();
    var mod = e.ctrlKey || e.metaKey;
    if (key === "f12" || (mod && e.shiftKey && ["i", "j", "c"].indexOf(key) !== -1) || (e.metaKey && e.altKey && ["i", "j", "c"].indexOf(key) !== -1)) {
      blocked(e, "DEVTOOLS_ATTEMPT", "Инструменты разработчика недоступны во время экзамена");
      return;
    }
    if (!mod || e.altKey) return;
    if (key === "c") blocked(e, "COPY_ATTEMPT", "Копирование запрещено во время экзамена");
    else if (key === "x") blocked(e, "CUT_ATTEMPT", "Вырезание запрещено во время экзамена");
    else if (key === "v") blocked(e, "PASTE_ATTEMPT", "Вставка запрещена во время экзамена");
    else if (key === "a" && !inAnswerField(e.target)) e.preventDefault();  // Ctrl+A inside an answer still works
    else if (key === "u" || key === "p" || key === "s") e.preventDefault();  // view source / print / save page
  }, true);

  // Tab / window switch.
  var switchReport = null;
  document.addEventListener("visibilitychange", function () {
    if (!examActive) return;
    if (document.visibilityState === "hidden") {
      switchReport = report("TAB_SWITCH", true);
      return;
    }
    // Back on the page: log it, tell the student, with the count from the
    // server (or the last known one if the report hasn't come back yet).
    report("TAB_RETURN", true);
    var reported = switchReport || Promise.resolve(null);
    switchReport = null;
    var done = false;
    var shown = function (data) {
      if (done || !examActive) return;
      done = true;
      var count = data && typeof data.tab_switch_count === "number" ? data.tab_switch_count : switches;
      var limitText = "";
      if (maxSwitches !== null) {
        limitText = " Уходов: " + count + " из " + maxSwitches + " допустимых" +
          (count >= maxSwitches ? " — следующий уход завершит экзамен." : ".");
      }
      showWarning("Сиз тесттен чыгып кеттиңиз", "Бул аракет системада катталды. Вы покинули страницу экзамена — действие зафиксировано." + limitText,
        false);
      syncState();
    };
    reported.then(shown);
    window.setTimeout(function () { shown(null); }, 1500);
  });

  function syncState() {
    request(stateUrl, { method: "GET" }).then(function (result) {
      if (result.status === 409 && result.data.closed) handleClosed(result.data);
      else if (result.status === 200) { syncDeadline(result.data.remaining_seconds); updateSwitches(result.data); }
    }).catch(function () { setOffline(true); });
  }

  // Fullscreen.
  var fsSupported = !!(document.documentElement.requestFullscreen && document.fullscreenEnabled !== false);
  var fsTopBtn = $("[data-xm-fullscreen]");
  var fsModal = $("[data-xm-start-fullscreen]");
  function enterFullscreen() {
    if (!fsSupported || document.fullscreenElement) return;
    try { document.documentElement.requestFullscreen().catch(function () {}); } catch (e) { /* refused */ }
  }
  function syncFullscreenButton() { fsTopBtn.hidden = !fsSupported || !!document.fullscreenElement || !examActive; }
  // With «require_fullscreen» the questions stay covered by a lock overlay
  // until the browser is really in fullscreen (the Fullscreen API, not a
  // stretched <div>). A browser can always leave fullscreen — so the exit
  // is logged and the exam waits; it can't be made impossible.
  function lockForFullscreen() {
    $("#xm-fs-title").textContent = "Экзамен режими активдүү";
    $("[data-xm-fs-text]").textContent = "Тестти улантуу үчүн толук экран режимине кайтыңыз. (Вернитесь в полноэкранный режим, чтобы продолжить.)";
    $("[data-xm-fs-enter]").lastChild.textContent = "Толук экранга кайтуу";
    $("[data-xm-fs-skip]").hidden = true;
    fsModal.hidden = false;
  }
  if (fsSupported) {
    fsTopBtn.addEventListener("click", enterFullscreen);
    document.addEventListener("fullscreenchange", function () {
      syncFullscreenButton();
      if (!examActive) return;
      if (document.fullscreenElement) {
        report("FULLSCREEN_ENTER", true);
        fsModal.hidden = true;
        return;
      }
      if (!requireFullscreen) return;
      report("FULLSCREEN_EXIT", true);
      lockForFullscreen();
    });
    syncFullscreenButton();
    // Offer fullscreen at the start (a browser only allows it from a click).
    $("[data-xm-fs-skip]").addEventListener("click", function () { if (!requireFullscreen) fsModal.hidden = true; });
    $("[data-xm-fs-enter]").addEventListener("click", function () {
      if (!requireFullscreen) fsModal.hidden = true;  // required: the overlay goes away on «fullscreenchange» only
      enterFullscreen();
    });
    if (requireFullscreen) lockForFullscreen();
    else fsModal.hidden = false;
  }

  // Leaving the page: the browser's own confirmation, and a beacon if they go.
  window.addEventListener("beforeunload", function (event) {
    if (!examActive || submitting) return;
    event.preventDefault();
    event.returnValue = "Вы уверены, что хотите покинуть экзамен? Ваш прогресс может быть потерян.";
    return event.returnValue;
  });
  window.addEventListener("pagehide", function () {
    if (!examActive || submitting || !navigator.sendBeacon) return;
    var data = new FormData();
    data.append("csrfmiddlewaretoken", csrf);
    data.append("event_type", "PAGE_LEAVE");
    data.append("question", String(index + 1));
    navigator.sendBeacon(eventsUrl, data);
  });

  function stopExam() {
    examActive = false;
    syncFullscreenButton();
    if (document.fullscreenElement && document.exitFullscreen) document.exitFullscreen().catch(function () {});
  }

  // -- Submit -------------------------------------------------------------------
  var confirmModal = $("[data-xm-confirm]");
  var confirmOk = $("[data-xm-c-ok]");

  function openConfirm() {
    var answered = answeredCount();
    var missing = [];
    questions.forEach(function (q, n) { if (q.getAttribute("data-required") === "1" && !isAnswered(q)) missing.push(n + 1); });
    $("[data-xm-c-total]").textContent = questions.length;
    $("[data-xm-c-answered]").textContent = answered;
    $("[data-xm-c-unanswered]").textContent = questions.length - answered;
    $("[data-xm-c-time]").textContent = formatTime(secondsLeft());
    var requiredEl = $("[data-xm-c-required]");
    requiredEl.hidden = !missing.length;
    requiredEl.lastChild.textContent = missing.length ? "Ответьте на обязательные вопросы: " + missing.join(", ") + "." : "";
    confirmOk.disabled = missing.length > 0;
    questions.forEach(function (q, n) { q.querySelector("[data-xm-q-error]").hidden = missing.indexOf(n + 1) === -1; });
    confirmModal.hidden = false;
    $("[data-xm-c-cancel]").focus();
  }

  function sendForm(timedOut) {
    if (submitting) return;
    // Unsaved changes go first (a cleared answer only exists there — the
    // form can't say "nothing selected"), then the form itself.
    var flush = Object.keys(pending).length && !saving ? save() : Promise.resolve();
    var sent = false;
    var go = function () {
      if (sent) return;
      sent = true;
      submitting = true;
      $("[data-xm-timed-out]", form).value = timedOut ? "1" : "0";
      stopExam();
      clearPending();
      HTMLFormElement.prototype.submit.call(form);
    };
    examActive = false;  // no more restrictions or reports while sending
    flush.then(go, go);
    window.setTimeout(go, 3000);
  }

  function autoSubmit() {
    if (submitting || !examActive) return;
    confirmModal.hidden = true;
    sendForm(true);  // time is up: no confirmation
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    if (!submitting) openConfirm();
  });
  $("[data-xm-finish-side]", form).addEventListener("click", openConfirm);
  $("[data-xm-c-cancel]").addEventListener("click", function () { confirmModal.hidden = true; });
  confirmOk.addEventListener("click", function () { confirmModal.hidden = true; sendForm(false); });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !confirmModal.hidden) confirmModal.hidden = true;
  });

  // -- Start --------------------------------------------------------------------
  // Answers typed while offline (or not yet saved when the page closed) win
  // over the server's draft, then go to the server.
  questions.forEach(function (section) {
    if (Object.prototype.hasOwnProperty.call(pending, qid(section))) applyAnswer(section, pending[qid(section)]);
  });
  var firstUnanswered = questions.findIndex(function (q) { return !isAnswered(q); });
  show(firstUnanswered > 0 ? firstUnanswered : 0);
  if (Object.keys(pending).length) save();
  if (!navigator.onLine) setOffline(true);
})();
