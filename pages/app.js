// qa-automation-lab dashboard — small client-side helpers.
// Theme toggle + scrolled-nav state. Mirrors the portfolio behavior so
// the chrome stays consistent across both sites.
(function () {
  "use strict";

  // ---- Theme toggle -------------------------------------------------------
  // The inline <head> script already set data-theme from localStorage/system
  // pref to avoid a flash of the wrong palette. The button below just lets
  // visitors flip it explicitly and persists the choice.
  var toggle = document.querySelector(".theme-toggle");
  if (toggle) {
    var syncLabel = function () {
      var current = document.documentElement.getAttribute("data-theme") || "dark";
      var next = current === "dark" ? "light" : "dark";
      toggle.setAttribute(
        "aria-label",
        "Switch to " + next + " mode",
      );
      toggle.setAttribute(
        "title",
        "Switch to " + next + " mode",
      );
    };
    syncLabel();
    toggle.addEventListener("click", function () {
      var current = document.documentElement.getAttribute("data-theme") || "dark";
      var next = current === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      try {
        localStorage.setItem("theme", next);
      } catch (_) {
        /* private mode / no storage — ignore */
      }
      syncLabel();
    });
  }

  // ---- Scrolled nav state -------------------------------------------------
  // Adds .is-scrolled to .top-nav once the page leaves the top, which
  // strengthens the nav background + border so it reads against scrolled
  // content. rAF-throttled to avoid layout thrash on scroll-heavy pages
  // (e.g. the suite detail tables).
  var nav = document.querySelector(".top-nav");
  if (nav) {
    var pending = false;
    var update = function () {
      pending = false;
      if (window.scrollY > 16) nav.classList.add("is-scrolled");
      else nav.classList.remove("is-scrolled");
    };
    update();
    window.addEventListener(
      "scroll",
      function () {
        if (pending) return;
        pending = true;
        window.requestAnimationFrame(update);
      },
      { passive: true },
    );
  }
})();
