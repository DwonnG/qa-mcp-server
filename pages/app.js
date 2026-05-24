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

  // ---- Mobile hamburger menu ---------------------------------------------
  // Below 768px the desktop .nav-links bar is hidden and replaced by a
  // slide-down panel. Open/close via the toggle button, ESC key, or by
  // tapping a link inside the panel. Mirrors the portfolio's main.js so
  // the chrome behaves identically across all four DwonnG sites.
  var navToggle = document.querySelector(".nav-toggle");
  var mobileMenu = document.getElementById("mobile-menu");
  if (navToggle && mobileMenu) {
    var setMenuOpen = function (open) {
      navToggle.setAttribute("aria-expanded", String(open));
      navToggle.setAttribute(
        "aria-label",
        open ? "Close navigation menu" : "Open navigation menu",
      );
      mobileMenu.setAttribute("aria-hidden", String(!open));
      mobileMenu.classList.toggle("is-open", open);
      document.body.classList.toggle("menu-open", open);
    };
    navToggle.addEventListener("click", function () {
      var isOpen = navToggle.getAttribute("aria-expanded") === "true";
      setMenuOpen(!isOpen);
    });
    var menuLinks = mobileMenu.querySelectorAll("a");
    for (var i = 0; i < menuLinks.length; i++) {
      menuLinks[i].addEventListener("click", function () {
        setMenuOpen(false);
      });
    }
    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") return;
      if (navToggle.getAttribute("aria-expanded") !== "true") return;
      setMenuOpen(false);
      navToggle.focus();
    });
    // If the viewport grows past the mobile breakpoint while the menu is
    // open (e.g. rotating a tablet), close it so the desktop nav takes
    // over cleanly. Matches the @media rule in styles.css.
    var desktopMq = window.matchMedia("(min-width: 768px)");
    var onDesktop = function (e) {
      if (e.matches) setMenuOpen(false);
    };
    if (typeof desktopMq.addEventListener === "function") {
      desktopMq.addEventListener("change", onDesktop);
    } else if (typeof desktopMq.addListener === "function") {
      desktopMq.addListener(onDesktop);
    }
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
