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

  document.addEventListener("DOMContentLoaded", function () {
    bind("sector-filter", "#sectors .sector-track", "sector-filter-empty");
    bind("stock-filter", "#stocks .stock-list-vertical", "stock-filter-empty");
  });
})();
