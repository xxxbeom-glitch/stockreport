/**
 * kr_trading UI — 누적 가상매수·성과 (/api/trading-display)
 * 폴백: /data/mock_trading/trading_data.json
 */
(function () {
  "use strict";

  var DISPLAY_API = new URL("/api/trading-display", location.origin).href;
  var FALLBACK_DATA_URL = new URL(
    "/data/mock_trading/trading_data.json",
    location.origin
  ).href;
  var pageData = null;
  var allHoldings = [];
  var holdingsFilterKey = "";
  var agentCatalog = [];

  function formatWon(amount) {
    var n = Math.round(Number(amount) || 0);
    return n.toLocaleString("ko-KR") + "원";
  }

  function formatReturnPct(pct) {
    var n = Number(pct);
    if (isNaN(n)) n = 0;
    var sign = n > 0 ? "+" : n < 0 ? "-" : "";
    return sign + Math.abs(n).toFixed(2) + "%";
  }

  function formatReturnPctRank(pct) {
    var n = Number(pct);
    if (isNaN(n)) n = 0;
    var rounded = Math.round(n);
    var sign = rounded > 0 ? "+" : rounded < 0 ? "-" : "";
    return sign + String(Math.abs(rounded)) + "%";
  }

  function trendClass(pct) {
    var n = Number(pct) || 0;
    return n >= 0 ? "is-up" : "is-down";
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null && text !== "") node.textContent = text;
    return node;
  }

  function renderPageMeta(meta) {
    var title = document.querySelector(".page-title");
    if (title && meta.title) title.textContent = meta.title;

    var line = document.querySelector(".page-meta__line");
    if (!line) return;
    var parts = [];
    if (meta.market) parts.push(meta.market);
    if (meta.updated_at) parts.push(meta.updated_at);
    line.textContent = parts.join(" · ");
  }

  function formatPickCount(agent) {
    var n = Number(agent.pick_count);
    if (!isNaN(n) && n > 0) {
      return n + "개";
    }
    var names = agent.pick_names;
    n = Array.isArray(names) ? names.length : Number(agent.total_trades);
    if (isNaN(n) || n < 0) n = 0;
    return n + "개";
  }

  function agentDisplayName(agent) {
    var name = (agent.name || "").trim();
    var model = (agent.model_id || "").trim();
    if (name && model && name.toLowerCase() !== model.toLowerCase()) {
      return name;
    }
    return name || model || "—";
  }

  function renderAgentRankings(container, items) {
    container.innerHTML = "";
    if (!items || !items.length) {
      container.appendChild(
        el("p", "rank-empty", "에이전트 수익률 데이터가 없습니다.")
      );
      return;
    }

    var head = el("div", "agent-rank-table__head");
    head.setAttribute("role", "row");
    ["순위", "에이전트명", "매수종목", "수익률"].forEach(function (label) {
      var cell = el("span", null, label);
      cell.setAttribute("role", "columnheader");
      head.appendChild(cell);
    });
    container.appendChild(head);

    var sorted = items.slice().sort(function (a, b) {
      var ra = Number(a.cumulative_return_pct);
      var rb = Number(b.cumulative_return_pct);
      if (isNaN(ra)) ra = 0;
      if (isNaN(rb)) rb = 0;
      return rb - ra;
    });

    sorted.forEach(function (row, index) {
      var tr = el("div", "agent-rank-table__row");
      tr.setAttribute("role", "row");
      var pctNum = Number(row.cumulative_return_pct);
      var hasReturn =
        row.cumulative_return_pct != null &&
        row.cumulative_return_pct !== "" &&
        !isNaN(pctNum);
      tr.appendChild(el("span", null, String(index + 1)));
      tr.appendChild(el("span", "col-agent-name", agentDisplayName(row)));
      tr.appendChild(el("span", "col-pick-count", formatPickCount(row)));
      tr.appendChild(
        el(
          "span",
          hasReturn ? "col-return " + trendClass(pctNum) : "col-return",
          hasReturn ? formatReturnPctRank(pctNum) : "—"
        )
      );
      container.appendChild(tr);
    });
  }

  function renderRankings(container, items) {
    container.innerHTML = "";
    if (!items || !items.length) {
      container.appendChild(
        el("p", "rank-empty", "주간 추천 종목은 보유 종목 상세에서 확인하세요.")
      );
      return;
    }

    var head = el("div", "rank-table__head");
    head.setAttribute("role", "row");
    ["순위", "종목명", "매수금액", "평가금액", "수익률"].forEach(function (label) {
      var cell = el("span", null, label);
      cell.setAttribute("role", "columnheader");
      head.appendChild(cell);
    });
    container.appendChild(head);

    var sorted = items.slice().sort(function (a, b) {
      var ra = Number(a.return_pct);
      var rb = Number(b.return_pct);
      if (isNaN(ra)) ra = 0;
      if (isNaN(rb)) rb = 0;
      return rb - ra;
    });

    sorted.forEach(function (row, index) {
      var tr = el("div", "rank-table__row");
      tr.setAttribute("role", "row");
      var pctNum = Number(row.return_pct);
      var hasReturn =
        row.return_pct != null && row.return_pct !== "" && !isNaN(pctNum);
      tr.appendChild(el("span", null, String(index + 1)));
      tr.appendChild(el("span", "col-name", row.name || ""));
      tr.appendChild(el("span", null, formatWon(row.buy_amount)));
      tr.appendChild(
        el(
          "span",
          null,
          row.eval_amount != null ? formatWon(row.eval_amount) : "—"
        )
      );
      var ret = el(
        "span",
        hasReturn ? "col-return " + trendClass(pctNum) : "col-return",
        hasReturn ? formatReturnPctRank(pctNum) : "—"
      );
      tr.appendChild(ret);
      container.appendChild(tr);
    });
  }

  function agentNames(h) {
    var agents = h.recommending_agents;
    if (Array.isArray(agents) && agents.length) return agents;
    return (h.agent || "")
      .split(/,\s*/)
      .map(function (s) {
        return s.trim();
      })
      .filter(Boolean);
  }

  function agentModelName(agentKey) {
    var key = String(agentKey || "");
    for (var i = 0; i < agentCatalog.length; i++) {
      if (agentCatalog[i].agent_key === key) {
        return agentCatalog[i].name || key;
      }
    }
    return "";
  }

  function holdingMatchesAgentFilter(h, filterKey) {
    if (!filterKey) return true;
    var keys = h.agent_keys || [];
    if (Array.isArray(keys) && keys.indexOf(filterKey) >= 0) return true;
    var modelName = agentModelName(filterKey);
    if (!modelName) return false;
    var names = agentNames(h);
    return names.indexOf(modelName) >= 0;
  }

  function filterHoldings(holdings, filterKey) {
    if (!filterKey) return holdings.slice();
    return (holdings || []).filter(function (h) {
      return holdingMatchesAgentFilter(h, filterKey);
    });
  }

  function closeHoldingsFilterMenu(menu, btn) {
    if (!menu || !btn) return;
    menu.hidden = true;
    btn.setAttribute("aria-expanded", "false");
  }

  function setupHoldingsAgentFilter(agents, holdingsList) {
    var wrap = document.querySelector(".holdings-filter-wrap");
    if (!wrap || !holdingsList) return;

    var btn = wrap.querySelector(".holdings-filter-pill");
    var label = wrap.querySelector(".holdings-filter-pill__label");
    var menu = wrap.querySelector(".holdings-filter-menu");
    if (!btn || !label || !menu) return;

    agentCatalog = (agents || []).slice();
    menu.innerHTML = "";

    function addOption(agentKey, displayName, selected) {
      var li = el("li", "filter-menu__option");
      var opt = el("button", "filter-menu__item " + (selected ? "is-selected" : ""));
      opt.type = "button";
      opt.setAttribute("role", "option");
      opt.setAttribute("aria-selected", selected ? "true" : "false");
      opt.dataset.agentKey = agentKey;
      opt.textContent = displayName;
      opt.addEventListener("click", function () {
        holdingsFilterKey = agentKey;
        label.textContent = displayName;
        menu.querySelectorAll(".filter-menu__item").forEach(function (node) {
          var on = node.dataset.agentKey === agentKey;
          node.classList.toggle("is-selected", on);
          node.setAttribute("aria-selected", on ? "true" : "false");
        });
        renderHoldings(holdingsList, filterHoldings(allHoldings, holdingsFilterKey));
        closeHoldingsFilterMenu(menu, btn);
      });
      li.appendChild(opt);
      menu.appendChild(li);
    }

    addOption("", "전체 모델", !holdingsFilterKey);
    agentCatalog.forEach(function (a) {
      var key = a.agent_key || "";
      var name = a.name || key;
      if (!key) return;
      addOption(key, name, holdingsFilterKey === key);
    });

    if (holdingsFilterKey) {
      label.textContent = agentModelName(holdingsFilterKey) || "전체 모델";
    } else {
      label.textContent = "전체 모델";
    }

    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      var open = menu.hidden;
      document.querySelectorAll(".holdings-filter-menu").forEach(function (m) {
        m.hidden = true;
      });
      document.querySelectorAll(".holdings-filter-pill").forEach(function (b) {
        b.setAttribute("aria-expanded", "false");
      });
      if (open) {
        menu.hidden = false;
        btn.setAttribute("aria-expanded", "true");
      }
    });

    if (!wrap.dataset.boundClose) {
      wrap.dataset.boundClose = "1";
      document.addEventListener("click", function () {
        closeHoldingsFilterMenu(menu, btn);
      });
      menu.addEventListener("click", function (e) {
        e.stopPropagation();
      });
    }
  }

  function formatMilestoneDays(h, pct) {
    if (!h.virtually_bought) {
      return "—";
    }
    var keys =
      pct === 10
        ? [
            "daysTo10Percent",
            "milestone_10_days",
            "achievement_10_days",
            "pct_10_days",
          ]
        : [
            "daysTo20Percent",
            "milestone_20_days",
            "achievement_20_days",
            "pct_20_days",
          ];
    var v;
    for (var i = 0; i < keys.length; i++) {
      if (h[keys[i]] != null && h[keys[i]] !== "") {
        v = h[keys[i]];
        break;
      }
    }
    if (v == null || v === "") return "—";
    var n = Number(v);
    if (!isNaN(n)) {
      var sign = n > 0 ? "+" : n < 0 ? "-" : "";
      return sign + Math.abs(n) + "일";
    }
    var s = String(v).trim();
    if (/일$/.test(s) || /^[+-]/.test(s)) return s;
    return "+" + s + "일";
  }

  function kvAgent(h) {
    var block = el("div", "kv kv--agent");
    block.appendChild(el("span", "kv__label", "에이전트"));
    var full =
      h.recommending_agents_full ||
      h.recommending_agents ||
      agentNames(h);
    var names = Array.isArray(full)
      ? full.filter(function (x, i, arr) {
          return x && arr.indexOf(x) === i;
        })
      : [];
    var text = names.length ? names.join(", ") : (h.agent || "—");
    var value = el("span", "kv__value kv__value--agent-names", text);
    if (names.length) {
      value.setAttribute("title", names.join(", "));
    }
    block.appendChild(value);
    return block;
  }

  function renderHoldings(container, items) {
    container.innerHTML = "";
    if (!items || !items.length) {
      var emptyMsg = holdingsFilterKey
        ? "선택한 에이전트 모델 추천 종목이 없습니다."
        : "표시할 종목이 없습니다.";
      container.appendChild(el("p", "rank-empty", emptyMsg));
      return;
    }
    (items || []).forEach(function (h) {
      var priceError = h.price_status === "error";
      var card = el("article", "card card--pad stock-card");
      card.dataset.ticker = h.ticker;

      var top = el("div", "stock-card__top");
      var identity = el("div", "stock-card__identity");
      identity.appendChild(el("h3", "stock-card__name", h.name || ""));
      identity.appendChild(
        el("span", "stock-card__sector", h.sector || h.business_summary || "")
      );
      top.appendChild(identity);

      var quote = el("div", "stock-card__quote");
      if (priceError) {
        quote.appendChild(el("span", "pct-badge", "조회 실패"));
        quote.appendChild(el("span", "stock-card__price", "—"));
      } else {
        quote.appendChild(
          el(
            "span",
            "pct-badge " + trendClass(h.return_pct),
            formatReturnPct(h.return_pct)
          )
        );
        quote.appendChild(
          el(
            "span",
            "stock-card__price " + trendClass(h.return_pct),
            formatWon(
              h.current_price != null ? h.current_price : h.eval_amount
            )
          )
        );
      }
      top.appendChild(quote);
      card.appendChild(top);

      var grid = el("div", "stock-card__grid");
      var row1 = el("div", "stock-card__grid-row");
      row1.appendChild(
        kv(
          "매수금액",
          h.buy_amount != null ? formatWon(h.buy_amount) : "—"
        )
      );
      row1.appendChild(
        kv(
          "평가금액",
          h.eval_amount != null ? formatWon(h.eval_amount) : "—"
        )
      );
      grid.appendChild(row1);

      var row2 = el("div", "stock-card__grid-row");
      row2.appendChild(kv("10% 달성", formatMilestoneDays(h, 10)));
      row2.appendChild(kv("20% 달성", formatMilestoneDays(h, 20)));
      grid.appendChild(row2);

      var row3 = el("div", "stock-card__grid-row stock-card__grid-row--full");
      row3.appendChild(kvAgent(h));
      grid.appendChild(row3);
      card.appendChild(grid);

      var reason = el("div", "reason-box reason-box--plain");
      reason.appendChild(el("div", "reason-box__title", "왜 추천했어요?"));
      reason.appendChild(
        el("p", "reason-box__body", h.plain_reason || h.plainReason || "—")
      );
      card.appendChild(reason);

      container.appendChild(card);
    });
  }

  function kv(label, value) {
    var block = el("div", "kv");
    block.appendChild(el("span", "kv__label", label));
    block.appendChild(el("span", "kv__value", value));
    return block;
  }

  function showError(message) {
    var main = document.querySelector(".page-content");
    if (!main) return;
    var box = el("p", "render-error", message);
    box.style.cssText =
      "padding:12px 16px;color:#ff1212;font-size:14px;line-height:1.5;";
    main.prepend(box);
  }

  function buildRankingsFromHoldings(holdings) {
    return (holdings || []).map(function (h) {
      return {
        name: h.name,
        buy_amount: h.buy_amount,
        eval_amount: h.eval_amount,
        return_pct: h.return_pct,
      };
    });
  }

  function init() {
    var agentRankTable = document.querySelector(".agent-rank-table");
    var rankTable = document.querySelector(".rank-table");
    var holdingsList = document.querySelector(".holdings-list");
    if (!agentRankTable || !rankTable || !holdingsList) {
      showError("렌더링 컨테이너를 찾지 못했습니다.");
      return;
    }

    function fetchDisplayData() {
      return fetch(DISPLAY_API)
        .then(function (res) {
          if (!res.ok) throw new Error("display API " + res.status);
          return res.json();
        })
        .then(function (body) {
          if (!body.ok || !body.data) throw new Error("display API empty");
          return body.data;
        })
        .catch(function () {
          return fetch(FALLBACK_DATA_URL).then(function (res) {
            if (!res.ok) throw new Error("fallback HTTP " + res.status);
            return res.json();
          });
        });
    }

    fetchDisplayData()
      .then(function (data) {
        pageData = data;
        return (data.holdings || []).slice();
      })
      .then(function (holdings) {
        var data = pageData;
        allHoldings = holdings.slice();
        renderPageMeta(data.pageMeta || {});
        var rankings =
          (data.rankings && data.rankings.length
            ? data.rankings
            : buildRankingsFromHoldings(holdings)) || [];
        renderAgentRankings(agentRankTable, data.agents || []);
        renderRankings(rankTable, rankings);
        setupHoldingsAgentFilter(data.agents || [], holdingsList);
        renderHoldings(
          holdingsList,
          filterHoldings(allHoldings, holdingsFilterKey)
        );

      })
      .catch(function (err) {
        showError(
          "추천 데이터를 불러오지 못했습니다. " +
            "python scripts/serve_mock_trading.py 실행 후 " +
            location.origin +
            "/template/kr_trading/ 로 접속하세요. (" +
            err.message +
            ")"
        );
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
