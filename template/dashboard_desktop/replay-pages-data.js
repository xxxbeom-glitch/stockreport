/**
 * REPLAY dashboard — load public JSON from docs/replay-data (GitHub Pages).
 */
(function (global) {
  "use strict";

  function replayPublicDataRoot() {
    var path = global.location.pathname || "";
    var marker = "/template/dashboard_desktop";
    var idx = path.indexOf(marker);
    if (idx >= 0) {
      return path.slice(0, idx) + "/docs/replay-data";
    }
    return "/docs/replay-data";
  }

  function fetchPublicJson(relativePath) {
    var url = replayPublicDataRoot() + relativePath;
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error("missing " + relativePath);
      return r.json();
    });
  }

  function preferPagesJson() {
    var host = (global.location && global.location.hostname) || "";
    if (host.indexOf("github.io") >= 0) return true;
    var params = new URLSearchParams(global.location.search);
    return params.get("dataBackend") === "pages";
  }

  function loadIndex() {
    return fetchPublicJson("/index.json");
  }

  function loadRunDashboard(runId) {
    return fetchPublicJson("/runs/" + encodeURIComponent(runId) + "/dashboard.json");
  }

  function loadCampaignReport(campaignId, reportType, reportKey) {
    if (reportType === "final") {
      return fetchPublicJson("/campaigns/" + encodeURIComponent(campaignId) + "/final.json");
    }
    return fetchPublicJson(
      "/campaigns/" +
        encodeURIComponent(campaignId) +
        "/" +
        reportType +
        "/" +
        encodeURIComponent(reportKey) +
        ".json"
    );
  }

  function loadCampaignBundle(campaignId) {
    return loadIndex().then(function (idx) {
      var camp = (idx.campaigns || {})[campaignId];
      if (!camp) {
        return { weeklyReports: {}, monthlyReports: {}, finalReport: null };
      }
      var weekly = {};
      var monthly = {};
      var tasks = [];
      (camp.weekly || []).forEach(function (wk) {
        tasks.push(
          loadCampaignReport(campaignId, "weekly", wk).then(function (rep) {
            weekly[wk] = rep;
          })
        );
      });
      (camp.monthly || []).forEach(function (mk) {
        tasks.push(
          loadCampaignReport(campaignId, "monthly", mk).then(function (rep) {
            monthly[mk] = rep;
          })
        );
      });
      var finalP = Promise.resolve(null);
      if (camp.hasFinal) {
        finalP = loadCampaignReport(campaignId, "final", "final");
      }
      return Promise.all(tasks).then(function () {
        return finalP.then(function (finalReport) {
          return { weeklyReports: weekly, monthlyReports: monthly, finalReport: finalReport };
        });
      });
    });
  }

  function listRunsFromIndex() {
    return loadIndex().then(function (idx) {
      return (idx.runs || []).map(function (r) {
        return {
          replayRunId: r.replayRunId,
          tradingDate: r.tradingDate,
          campaignId: r.campaignId,
          leakageSummary: r.leakageSummary,
        };
      });
    });
  }

  function mergeReports(payload, reports) {
    payload.weeklyReports = reports.weeklyReports || {};
    payload.monthlyReports = reports.monthlyReports || {};
    payload.finalReport = reports.finalReport || null;
    return payload;
  }

  global.CompetitionReplayPages = {
    preferPagesJson: preferPagesJson,
    replayPublicDataRoot: replayPublicDataRoot,
    loadRunDashboard: loadRunDashboard,
    loadCampaignBundle: loadCampaignBundle,
    listRunsFromIndex: listRunsFromIndex,
    mergeReports: mergeReports,
  };
})(window);
