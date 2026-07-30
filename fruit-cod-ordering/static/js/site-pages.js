(() => {
  "use strict";

  const menuButton = document.querySelector("[data-page-menu]");
  const navigation = document.querySelector("[data-page-nav]");

  function setMenuOpen(open) {
    document.body.classList.toggle("menu-open", open);
    navigation?.classList.toggle("is-open", open);
    menuButton?.setAttribute("aria-expanded", open ? "true" : "false");
    menuButton?.setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
  }

  menuButton?.addEventListener("click", () => {
    setMenuOpen(!navigation?.classList.contains("is-open"));
  });

  navigation?.addEventListener("click", (event) => {
    if (event.target.closest("a")) setMenuOpen(false);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setMenuOpen(false);
  });
})();
