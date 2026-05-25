/**
 * SIMPLE_REPLAY — load public JSON from docs/simple-replay-data (GitHub Pages).
 */
(function (global) {
  "use strict";

  function dataRoot() {
    var path = global.location.pathname || "";
    var marker = "/template/dashboard_desktop";
    var idx = path.indexOf(marker);
    if (idx >= 0) {
      return path.slice(0, idx) + "/docs/simple-replay-data";
    }
    return "/docs/simple-replay-data";
  }

  function fetchJson(relativePath) {
    return fetch(dataRoot() + relativePath).then(function (r) {
      if (!r.ok) throw new Error("missing " + relativePath);
      return r.json();
    });
  }

  function preferPagesJson() {
    var host = (global.location && global.location.hostname) || "";
    if (host.indexOf("github.io") >= 0) return true;
    return new URLSearchParams(global.location.search).get("dataBackend") === "pages";
  }

  function loadIndex() {
    return fetchJson("/index.json");
  }

  function listCompletedRuns() {
    return loadIndex().then(function (idx) {
      return (idx.runs || []).filter(function (r) {
        return r && r.runId;
      });
    });
  }

  function loadRunDashboard(runId) {
    return fetchJson("/runs/" + encodeURIComponent(runId) + "/dashboard.json");
  }

  global.CompetitionSimpleReplayPages = {
    preferPagesJson: preferPagesJson,
    loadIndex: loadIndex,
    listCompletedRuns: listCompletedRuns,
    loadRunDashboard: loadRunDashboard,
  };
})(typeof window !== "undefined" ? window : globalThis);
