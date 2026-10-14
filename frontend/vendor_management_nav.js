/* Only isolate the companion link from ancestor bubble-phase portal routing. */
(() => {
  "use strict";
  const link = document.getElementById("vendor-management-nav-link");
  if (!link || link.tagName !== "A") return;
  link.addEventListener("click", (event) => event.stopPropagation());
  link.addEventListener("auxclick", (event) => event.stopPropagation());
})();
