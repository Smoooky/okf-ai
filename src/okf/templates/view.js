/* okf-ai pages: theme, filters and search, copying commands, the site's navigation drawer. */
(function () {
  "use strict";
  var root = document.documentElement;

  /* Theme: the system's by default; the toggle is remembered when storage works. */
  function current() {
    var set = root.getAttribute("data-theme");
    if (set) return set;
    return window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  var themeButton = document.getElementById("theme");
  function labelTheme() {
    if (!themeButton) return;
    var next = current() === "dark" ? "светлую" : "тёмную";
    themeButton.setAttribute("aria-label", "Включить " + next + " тему");
    themeButton.title = "Включить " + next + " тему";
  }
  if (themeButton) {
    themeButton.addEventListener("click", function () {
      var theme = current() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", theme);
      try { localStorage.setItem("okf-theme", theme); } catch (e) { /* private mode: not remembered */ }
      labelTheme();
    });
    labelTheme();
  }

  /* Filters: level tiles and chips share one state; search; tags on the site's home page. */
  var items = Array.prototype.slice.call(document.querySelectorAll("[data-level]"));
  var levelButtons = Array.prototype.slice.call(document.querySelectorAll("[data-filter]"));
  var tagButtons = Array.prototype.slice.call(document.querySelectorAll("[data-tag]"));
  var search = document.getElementById("q");
  var empty = document.getElementById("empty");
  var levels = { broken: true, recheck: true, verified: true, unverified: true };
  var tag = null;

  function apply() {
    var text = search ? search.value.trim().toLowerCase() : "";
    var shown = 0;
    items.forEach(function (item) {
      var hay = (item.getAttribute("data-search") || item.textContent).toLowerCase();
      var tags = " " + (item.getAttribute("data-tags") || "") + " ";
      var ok = levels[item.getAttribute("data-level")] && (!text || hay.indexOf(text) >= 0) &&
        (!tag || tags.indexOf(" " + tag + " ") >= 0);
      item.hidden = !ok;
      if (ok) shown++;
    });
    document.querySelectorAll("[data-group]").forEach(function (group) {
      group.hidden = !group.querySelector("[data-level]:not([hidden])");
    });
    levelButtons.forEach(function (button) {
      button.setAttribute("aria-pressed", levels[button.getAttribute("data-filter")] ? "true" : "false");
    });
    if (empty) empty.hidden = shown > 0 || !items.length;
  }
  levelButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      var level = button.getAttribute("data-filter");
      if (button.hasAttribute("data-solo")) {
        var only = Object.keys(levels).every(function (k) { return levels[k] === (k === level); });
        Object.keys(levels).forEach(function (k) { levels[k] = only ? true : k === level; });
      } else {
        levels[level] = !levels[level];
      }
      apply();
    });
  });
  tagButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      var value = button.getAttribute("data-tag");
      tag = tag === value ? null : value;
      tagButtons.forEach(function (b) { b.setAttribute("aria-pressed", b.getAttribute("data-tag") === tag ? "true" : "false"); });
      apply();
    });
  });
  if (search) {
    search.addEventListener("input", apply);
    search.addEventListener("keydown", function (event) {
      if (event.key === "Escape") { search.value = ""; apply(); search.blur(); }
    });
  }
  document.addEventListener("keydown", function (event) {
    var typing = /^(INPUT|TEXTAREA|SELECT)$/.test((event.target || {}).tagName || "");
    if (event.key === "/" && !typing && search) { event.preventDefault(); search.focus(); search.select(); }
  });

  /* The site's sidebar search filters the navigation. */
  var navSearch = document.getElementById("nav-q");
  if (navSearch) {
    navSearch.addEventListener("input", function () {
      var text = navSearch.value.trim().toLowerCase();
      document.querySelectorAll(".nav-group li").forEach(function (li) {
        li.hidden = !!text && li.textContent.toLowerCase().indexOf(text) < 0;
      });
      document.querySelectorAll(".nav-group").forEach(function (group) {
        group.hidden = !group.querySelector("li:not([hidden])");
      });
    });
  }

  /* Copy a command, with feedback. */
  function copied(button) {
    var label = button.textContent;
    button.textContent = "Скопировано";
    button.classList.add("done");
    setTimeout(function () { button.textContent = label; button.classList.remove("done"); }, 1600);
  }
  document.querySelectorAll("[data-copy]").forEach(function (button) {
    button.addEventListener("click", function () {
      var text = button.getAttribute("data-copy");
      var area = document.createElement("textarea");
      area.value = text; area.setAttribute("readonly", ""); area.style.position = "fixed"; area.style.opacity = "0";
      document.body.appendChild(area); area.select();
      var ok = false;
      try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
      document.body.removeChild(area);
      if (ok) { copied(button); return; }
      function manual() {  /* no clipboard here: select the command so Ctrl+C copies it */
        var code = button.previousElementSibling, range = document.createRange();
        range.selectNodeContents(code);
        var selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
        button.textContent = "Нажмите Ctrl+C";
      }
      if (!navigator.clipboard || !navigator.clipboard.writeText) { manual(); return; }
      var done = false;
      navigator.clipboard.writeText(text).then(function () { done = true; copied(button); }, function () { done = true; manual(); });
      setTimeout(function () { if (!done) manual(); }, 1200);
    });
  });

  /* The site's navigation drawer on narrow screens. */
  var site = document.querySelector(".site");
  var menu = document.getElementById("menu");
  function closeNav() { if (site) site.classList.remove("nav-open"); if (menu) menu.setAttribute("aria-expanded", "false"); }
  if (menu && site) {
    menu.addEventListener("click", function () {
      var open = !site.classList.contains("nav-open");
      site.classList.toggle("nav-open", open);
      menu.setAttribute("aria-expanded", open ? "true" : "false");
      if (open && navSearch) navSearch.focus();
    });
    var scrim = document.querySelector(".scrim");
    if (scrim) scrim.addEventListener("click", closeNav);
    document.addEventListener("keydown", function (event) { if (event.key === "Escape") closeNav(); });
  }

  /* Printing shows everything: groups open, filters off. */
  window.addEventListener("beforeprint", function () {
    document.querySelectorAll("details").forEach(function (d) { d.setAttribute("data-was-open", d.open ? "1" : "0"); d.open = true; });
  });
  window.addEventListener("afterprint", function () {
    document.querySelectorAll("details[data-was-open]").forEach(function (d) { d.open = d.getAttribute("data-was-open") === "1"; });
  });

  apply();
})();
