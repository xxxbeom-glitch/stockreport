/**
 * kr_trading UI — Firebase weeklyRecommendations 우선 로드
 * 폴백: /data/mock_trading/trading_data.json
 */
(function () {
  "use strict";

  var DEFAULT_WEEK_ID = "2026-W21";
  var DISPLAY_API = new URL("/api/trading-display", location.origin).href;
  var FALLBACK_DATA_URL = new URL(
    "/data/mock_trading/trading_data.json",
    location.origin
  ).href;
  var STATE_API = new URL("/api/trading-state", location.origin).href;
  var LS_PREFIX = "kr_trading_state_";

  var pageData = null;
  var weekId = DEFAULT_WEEK_ID;

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

  function lsKey() {
    return LS_PREFIX + weekId;
  }

  function readLocalStates() {
    try {
      var raw = localStorage.getItem(lsKey());
      if (!raw) return {};
      var doc = JSON.parse(raw);
      var map = {};
      (doc.holdings || []).forEach(function (row) {
        var t = String(row.ticker || "").padStart(6, "0");
        if (t && row.status) map[t] = row.status;
      });
      return map;
    } catch (_) {
      return {};
    }
  }

  function writeLocalStates(holdings) {
    var payload = {
      week_id: weekId,
      updated_at: new Date().toISOString(),
      holdings: holdings.map(function (h) {
        return { ticker: h.ticker, status: h.status };
      }),
    };
    try {
      localStorage.setItem(lsKey(), JSON.stringify(payload));
    } catch (e) {
      /* ignore quota */
    }
    return payload;
  }

  function postServerState(holdings) {
    var payload = writeLocalStates(holdings);
    return fetch(STATE_API, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (res) {
        return res.json();
      })
      .catch(function () {
        return { ok: false, offline: true };
      });
  }

  function fetchServerState() {
    var url = STATE_API + "?week_id=" + encodeURIComponent(weekId);
    return fetch(url)
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function (body) {
        return body.state || {};
      })
      .catch(function () {
        return null;
      });
  }

  function normalizeDisplayStatus(value) {
    var s = (value || "").trim();
    if (s === "익절" || s === "익절 완료") return "익절";
    if (s === "진행 중" || s === "투자 진행 중") return "진행 중";
    return "—";
  }

  function applyStates(holdings, stateMap) {
    holdings.forEach(function (h) {
      var t = String(h.ticker || "").padStart(6, "0");
      if (stateMap[t]) {
        h.status = normalizeDisplayStatus(stateMap[t]);
      } else {
        h.status = normalizeDisplayStatus(h.status);
      }
    });
  }

  function mergeStateMaps(localMap, serverMap) {
    var out = {};
    Object.keys(localMap || {}).forEach(function (k) {
      out[k] = localMap[k];
    });
    Object.keys(serverMap || {}).forEach(function (k) {
      out[k] = serverMap[k];
    });
    return out;
  }

  function serverStateToMap(stateDoc) {
    var map = {};
    (stateDoc.holdings || []).forEach(function (row) {
      var t = String(row.ticker || "").padStart(6, "0");
      if (t && row.status) map[t] = row.status;
    });
    return map;
  }

  function renderPageMeta(meta) {
    var title = document.querySelector(".page-title");
    if (title && meta.title) title.textContent = meta.title;

    var spans = document.querySelectorAll(".page-meta span");
    if (spans.length >= 3) {
      if (meta.market) spans[0].textContent = meta.market;
      if (meta.weekday_label) spans[1].textContent = meta.weekday_label;
      if (meta.updated_at) spans[2].textContent = meta.updated_at;
      if (meta.week_id && spans.length >= 3) {
        spans[1].textContent = (meta.weekday_label || "") + " · " + meta.week_id;
      }
    }
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

  function kvAgent(h) {
    var block = el("div", "kv kv--agent");
    block.appendChild(el("span", "kv__label", "에이전트"));
    var valueWrap = el("div", "kv__value kv__value--agents");
    var icons = el("div", "agent-icon-list");
    var names = agentNames(h);
    names.forEach(function (name) {
      var item = el("span", "agent-icon-item");
      item.setAttribute("aria-label", name);
      item.setAttribute("title", name);
      item.appendChild(el("span", "agent-icon-placeholder", ""));
      icons.appendChild(item);
    });
    if (!names.length) {
      icons.appendChild(el("span", "agent-icon-empty", "—"));
    }
    valueWrap.appendChild(icons);
    block.appendChild(valueWrap);
    return block;
  }

  function renderHoldings(container, items) {
    container.innerHTML = "";
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
      row1.appendChild(kv("진입가", formatWon(h.buy_amount)));
      row1.appendChild(kv("목표가", formatWon(h.target_price)));
      grid.appendChild(row1);

      var row2 = el("div", "stock-card__grid-row");
      row2.appendChild(kvAgent(h));
      row2.appendChild(kv("진행상태", normalizeDisplayStatus(h.status)));
      grid.appendChild(row2);
      card.appendChild(grid);

      var reason = el("div", "reason-box reason-box--plain");
      reason.appendChild(el("div", "reason-box__title", "왜 추천됐어요?"));
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

  function renderAgents(container, items) {
    container.innerHTML = "";
    (items || []).forEach(function (a) {
      var card = el("article", "card card--pad agent-card");
      var top = el("div", "agent-card__top");
      var identity = el("div", "agent-card__identity");
      identity.appendChild(el("h3", "agent-card__name", a.name || ""));
      identity.appendChild(el("span", "agent-card__model", a.model_id || ""));
      top.appendChild(identity);
      top.appendChild(
        el(
          "span",
          "agent-card__return " + trendClass(a.cumulative_return_pct),
          formatReturnPct(a.cumulative_return_pct)
        )
      );
      card.appendChild(top);

      var holdings = el("div", "agent-card__holdings kv");
      holdings.appendChild(el("span", "kv__label", "추천 종목"));
      var names = Array.isArray(a.pick_names) ? a.pick_names.join(", ") : "";
      holdings.appendChild(el("span", "kv__value", names));
      card.appendChild(holdings);

      container.appendChild(card);
    });
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
    var rankTable = document.querySelector(".rank-table");
    var holdingsList = document.querySelector(".holdings-list");
    var agentsList = document.querySelector(".agents-list");
    if (!rankTable || !holdingsList || !agentsList) {
      showError("렌더링 컨테이너를 찾지 못했습니다.");
      return;
    }

    function fetchDisplayData() {
      var url =
        DISPLAY_API + "?week_id=" + encodeURIComponent(weekId || DEFAULT_WEEK_ID);
      return fetch(url)
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
        weekId =
          (data.pageMeta && data.pageMeta.week_id) ||
          (data.recommendations && data.recommendations.week_id) ||
          weekId;
        var holdings = (data.holdings || []).slice();

        return fetchServerState().then(function (serverDoc) {
          var localMap = readLocalStates();
          var serverMap = serverDoc ? serverStateToMap(serverDoc) : {};
          var merged = mergeStateMaps(serverMap, localMap);
          applyStates(holdings, merged);
          return holdings;
        });
      })
      .then(function (holdings) {
        var data = pageData;
        renderPageMeta(data.pageMeta || {});
        var rankings =
          (data.rankings && data.rankings.length
            ? data.rankings
            : buildRankingsFromHoldings(holdings)) || [];
        renderRankings(rankTable, rankings);
        renderHoldings(holdingsList, holdings);
        renderAgents(agentsList, data.agents || []);

        var expected = Number(
          (data.recommendations && data.recommendations.ticker_count) ||
            (data.pageMeta && data.pageMeta.recommendation_count) ||
            15
        );
        if (holdings.length !== expected) {
          showError(
            "추천 종목 수 불일치: JSON " +
              expected +
              "종 기대, 화면 " +
              holdings.length +
              "종"
          );
        }
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
