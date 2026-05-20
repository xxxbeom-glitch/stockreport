(function () {
  var ALL = "전체섹터";

  function normalize(value) {
    return (value || "").trim();
  }

  function applyFilter(select, cards, emptyEl) {
    if (!select || !cards.length) return;

    var chosen = normalize(select.value);
    var showAll = !chosen || chosen === ALL;
    var visible = 0;

    cards.forEach(function (card) {
      var key = normalize(card.getAttribute("data-sector"));
      var show = showAll || key === chosen;
      card.classList.toggle("is-filter-hidden", !show);
      if (show) visible += 1;
    });

    if (emptyEl) {
      emptyEl.hidden = visible > 0;
    }

    if (!showAll && visible > 0) {
      var first = cards.find(function (c) {
        return !c.classList.contains("is-filter-hidden");
      });
      if (first && first.scrollIntoView) {
        first.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "start" });
      }
    }
  }

  function bind(selectId, trackSelector, emptyId) {
    var select = document.getElementById(selectId);
    var track = document.querySelector(trackSelector);
    if (!select || !track) return;

    var cards = Array.prototype.slice.call(track.querySelectorAll("[data-sector]"));
    var emptyEl = emptyId ? document.getElementById(emptyId) : null;

    select.addEventListener("change", function () {
      applyFilter(select, cards, emptyEl);
    });
  }

  function bindM7Tabs() {
    var track = document.querySelector(".m7-tab-track");
    var panels = document.querySelectorAll(".m7-panel");
    if (!track || !panels.length) return;

    var tabs = Array.prototype.slice.call(track.querySelectorAll(".m7-tab"));

    function activate(tabId) {
      tabs.forEach(function (tab) {
        var isActive = tab.getAttribute("data-m7-tab") === tabId;
        tab.classList.toggle("is-active", isActive);
        tab.setAttribute("aria-selected", isActive ? "true" : "false");
        tab.tabIndex = isActive ? 0 : -1;
      });
      panels.forEach(function (panel) {
        var show = panel.getAttribute("data-m7-panel") === tabId;
        panel.classList.toggle("is-panel-hidden", !show);
        panel.hidden = !show;
      });
    }

    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        activate(tab.getAttribute("data-m7-tab"));
      });
      tab.addEventListener("keydown", function (e) {
        var idx = tabs.indexOf(tab);
        if (e.key === "ArrowRight") {
          e.preventDefault();
          tabs[(idx + 1) % tabs.length].focus();
        } else if (e.key === "ArrowLeft") {
          e.preventDefault();
          tabs[(idx - 1 + tabs.length) % tabs.length].focus();
        } else if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          activate(tab.getAttribute("data-m7-tab"));
        }
      });
    });

    var initial = tabs.find(function (t) {
      return t.classList.contains("is-active");
    });
    activate(
      initial
        ? initial.getAttribute("data-m7-tab")
        : tabs[0].getAttribute("data-m7-tab")
    );
  }

  document.addEventListener("DOMContentLoaded", function () {
    bind("sector-filter", "#sectors .sector-track", "sector-filter-empty");
    bind("stock-filter", "#stocks .stock-list-vertical", "stock-filter-empty");
    bindM7Tabs();
  });
})();
