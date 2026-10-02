/* Lightweight code editor for <textarea data-code-editor>: line numbers,
 * monospace, Tab / Shift+Tab indent, Enter keeps the indentation, and
 * closing brackets/quotes stay plain (no surprises on phones).
 * The textarea stays the real form field, so it works without JS too.
 * No third-party editor is bundled: the project serves no npm packages to
 * the admin or the student pages. */
(function () {
  "use strict";

  var INDENT = "    ";

  function enhance(textarea) {
    if (textarea.dataset.codeEditorReady) return;
    textarea.dataset.codeEditorReady = "1";

    var wrap = document.createElement("div");
    wrap.className = "okc-editor";
    var gutter = document.createElement("div");
    gutter.className = "okc-gutter";
    gutter.setAttribute("aria-hidden", "true");
    textarea.parentNode.insertBefore(wrap, textarea);
    wrap.appendChild(gutter);
    wrap.appendChild(textarea);
    textarea.classList.add("okc-input");
    textarea.setAttribute("wrap", "off");

    function renderGutter() {
      var count = textarea.value.split("\n").length;
      if (gutter.childElementCount === count) return;
      var html = "";
      for (var i = 1; i <= count; i++) html += "<span>" + i + "</span>";
      gutter.innerHTML = html;
    }

    function replaceSelection(start, end, text, caretStart, caretEnd) {
      textarea.setRangeText(text, start, end, "end");
      if (caretStart !== undefined) textarea.setSelectionRange(caretStart, caretEnd);
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    }

    textarea.addEventListener("keydown", function (event) {
      var value = textarea.value;
      var start = textarea.selectionStart, end = textarea.selectionEnd;

      if (event.key === "Tab") {
        event.preventDefault();
        var lineStart = value.lastIndexOf("\n", start - 1) + 1;
        if (start === end && !event.shiftKey) {
          replaceSelection(start, end, INDENT);
          return;
        }
        var block = value.slice(lineStart, end);
        var lines = block.split("\n");
        var changed = lines.map(function (line) {
          if (!event.shiftKey) return INDENT + line;
          var strip = line.match(/^( {1,4}|\t)/);
          return strip ? line.slice(strip[0].length) : line;
        }).join("\n");
        var delta = changed.length - block.length;
        var firstDelta = event.shiftKey ? (lines[0].length - changed.split("\n")[0].length) * -1 : INDENT.length;
        replaceSelection(lineStart, end, changed,
          Math.max(lineStart, start + (start === lineStart ? 0 : firstDelta)), end + delta);
        return;
      }

      if (event.key === "Enter" && !event.shiftKey && !event.ctrlKey && !event.metaKey) {
        var currentLineStart = value.lastIndexOf("\n", start - 1) + 1;
        var indent = value.slice(currentLineStart, start).match(/^[ \t]*/)[0];
        var before = value.slice(currentLineStart, start).trimEnd();
        if (/[:{[(]$/.test(before)) indent += INDENT;
        event.preventDefault();
        replaceSelection(start, end, "\n" + indent);
      }
    });

    textarea.addEventListener("input", renderGutter);
    textarea.addEventListener("scroll", function () { gutter.scrollTop = textarea.scrollTop; });
    renderGutter();
  }

  function init() { document.querySelectorAll("textarea[data-code-editor]").forEach(enhance); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
