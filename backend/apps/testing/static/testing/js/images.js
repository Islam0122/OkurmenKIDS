/* Student pages: an image that can't be loaded is replaced by its fallback
 * text (or simply hidden when it has none), never a broken-image icon. */
(function () {
  "use strict";

  function broken(img) {
    var figure = img.closest("[data-ex-figure]");
    if (!figure) return;
    var fallback = figure.querySelector(".ex-figure__fallback");
    img.hidden = true;
    if (fallback && fallback.textContent.trim()) fallback.hidden = false;
    else figure.hidden = true;
  }

  // error doesn't bubble — capture phase; plus images that failed before this ran.
  document.addEventListener("error", function (event) {
    if (event.target.tagName === "IMG") broken(event.target);
  }, true);
  document.querySelectorAll("[data-ex-figure] img").forEach(function (img) {
    if (img.complete && img.naturalWidth === 0 && img.getAttribute("src")) broken(img);
  });
})();
