/* Theme + mode persistence for Nobat (localStorage). CSP-safe: no inline. */
(function () {
  var KEY_THEME = "nobat-theme";
  var KEY_MODE = "nobat-mode";
  var DEFAULT_THEME = "yaru-orange";
  var THEMES = ["yaru-orange", "teal"];

  function stored(key, fallback) {
    try {
      return localStorage.getItem(key) || fallback;
    } catch (_) {
      return fallback;
    }
  }

  function save(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch (_) { /* private mode / quota */ }
  }

  function preferDark() {
    try {
      return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    } catch (_) {
      return false;
    }
  }

  function apply(theme, mode) {
    if (THEMES.indexOf(theme) < 0) theme = DEFAULT_THEME;
    if (mode !== "light" && mode !== "dark") mode = preferDark() ? "dark" : "light";
    var root = document.documentElement;
    root.setAttribute("data-theme", theme);
    root.setAttribute("data-mode", mode);
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      var brand = getComputedStyle(root).getPropertyValue("--brand").trim();
      if (brand) meta.setAttribute("content", brand);
    }
    return { theme: theme, mode: mode };
  }

  // Apply before paint when possible (script in <head>, not deferred).
  var initial = apply(stored(KEY_THEME, DEFAULT_THEME), stored(KEY_MODE, ""));

  function syncControls() {
    var modeBtn = document.querySelector("[data-theme-mode]");
    if (modeBtn) {
      var dark = document.documentElement.getAttribute("data-mode") === "dark";
      modeBtn.setAttribute("aria-pressed", dark ? "true" : "false");
      modeBtn.title = dark ? "حالت روشن" : "حالت تیره";
      modeBtn.setAttribute("aria-label", dark ? "حالت روشن" : "حالت تیره");
    }
    document.querySelectorAll("[data-theme-set]").forEach(function (el) {
      var t = el.getAttribute("data-theme-set");
      var on = document.documentElement.getAttribute("data-theme") === t;
      el.setAttribute("aria-pressed", on ? "true" : "false");
      el.classList.toggle("active", on);
    });
  }

  function onReady(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn);
    } else {
      fn();
    }
  }

  onReady(function () {
    syncControls();
    var modeBtn = document.querySelector("[data-theme-mode]");
    if (modeBtn) {
      modeBtn.addEventListener("click", function (e) {
        e.preventDefault();
        var next = document.documentElement.getAttribute("data-mode") === "dark" ? "light" : "dark";
        save(KEY_MODE, next);
        apply(document.documentElement.getAttribute("data-theme") || DEFAULT_THEME, next);
        syncControls();
      });
    }
    document.querySelectorAll("[data-theme-set]").forEach(function (el) {
      el.addEventListener("click", function (e) {
        e.preventDefault();
        var t = el.getAttribute("data-theme-set");
        save(KEY_THEME, t);
        apply(t, document.documentElement.getAttribute("data-mode") || initial.mode);
        syncControls();
      });
    });
  });
})();
