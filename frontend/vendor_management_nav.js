/* Keep this launcher text-only and isolate ancestor bubble-phase portal routing. */
(() => {
  "use strict";
  const link = document.getElementById("vendor-management-nav-link");
  if (!link || link.tagName !== "A") return;
  if (link.classList.contains("vendor-management-nav-link")) {
    // Remove only the old installer's direct decorative glyph, never other icons.
    for (const icon of link.querySelectorAll(':scope > span[aria-hidden="true"]')) {
      if (icon.childElementCount === 0 && icon.textContent.trim() === "\u25a3") {
        icon.remove();
      }
    }
  }
  link.addEventListener("click", (event) => event.stopPropagation());
  link.addEventListener("auxclick", (event) => event.stopPropagation());
})();
