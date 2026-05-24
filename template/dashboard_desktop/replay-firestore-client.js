/**
 * REPLAY dashboard data from Firestore (GitHub Pages / static host — no Python API).
 * Requires competition-firebase-config.js with valid web apiKey.
 */
(function (global) {
  "use strict";

  function hasFirestoreConfig() {
    var cfg = global.COMPETITION_FIREBASE_CONFIG;
    return cfg && cfg.projectId && cfg.apiKey && cfg.apiKey !== "YOUR_FIREBASE_WEB_API_KEY";
  }

  function getDb() {
    if (!global.firebase || !hasFirestoreConfig()) {
      return null;
    }
    if (!global.__competitionFirestoreDb) {
      if (!global.firebase.apps.length) {
        global.firebase.initializeApp(global.COMPETITION_FIREBASE_CONFIG);
      }
      global.__competitionFirestoreDb = global.firebase.firestore();
    }
    return global.__competitionFirestoreDb;
  }

  function isPublicStaticHost() {
    var host = (global.location && global.location.hostname) || "";
    return host.indexOf("github.io") >= 0 || host.indexOf("githubusercontent.com") >= 0;
  }

  function preferFirestoreBackend() {
    if (isPublicStaticHost()) return true;
    var params = new URLSearchParams(global.location.search);
    return params.get("dataBackend") === "firestore";
  }

  function docData(snap) {
    return snap.exists ? snap.data() : null;
  }

  function agentsFromReport(report) {
    if (!report || !report.agents) return [];
    return report.agents.map(function (a) {
      return {
        key: a.key,
        startAsset: a.startAsset,
        endAsset: a.endAsset,
        returnPct: a.returnPct,
        contributionLabel: a.contributionLabel,
        contributionStock: a.contributionStock,
        contributionPnl: a.contributionPnl,
        tierEval: a.tierEval,
        selfEval: a.selfEval,
        nextWeek: a.nextWeek,
      };
    });
  }

  function buildPayloadFromRunDoc(data, runId) {
    if (!data) return null;
    var payload = data.dashboard_payload;
    if (payload && payload.dataSource === "replay") {
      return payload;
    }
    var manifest = data.manifest || {};
    return {
      dataSource: "replay",
      replayRunId: runId,
      campaignId: manifest.campaign_id || data.campaign_id,
      cashAmount: 0,
      totalAssets: 0,
      agentMeta: {},
      stockCatalog: {},
      tradeHistory: { agent1: [], agent2: [], agent3: [], agent4: [] },
      notifications: [],
      weeklyReports: {},
      monthlyReports: {},
      auditSummary: {
        leakageStatus: manifest.leakage_summary || "UNVERIFIED",
        ruleViolationCount: manifest.code_audit_failures || 0,
        committeeStatus: "skipped",
        liveReady: false,
        costModel: manifest.cost_model || "costs_not_implemented",
        costsWarning: "매매 수수료·세금·제비용 미반영 — REPLAY (Firestore 직접 조회)",
      },
      teamDecisions: [],
      replayMeta: {
        tradingDate: manifest.trading_date,
        decisionAt: manifest.decision_at,
        fillDate: manifest.fill_date,
        executionMode: manifest.execution_mode,
      },
    };
  }

  function loadReplayRun(runId) {
    var db = getDb();
    if (!db || !runId) {
      return Promise.reject(new Error("firestore_unavailable"));
    }
    return db
      .collection("competition_replay_runs")
      .doc(runId)
      .get()
      .then(function (snap) {
        var payload = buildPayloadFromRunDoc(docData(snap), runId);
        if (!payload) throw new Error("replay_run_not_found");
        return payload;
      });
  }

  function loadCampaignReports(campaignId) {
    var db = getDb();
    if (!db || !campaignId) {
      return Promise.resolve({ weeklyReports: {}, monthlyReports: {}, finalReport: null });
    }
    var weekly = {};
    var monthly = {};
    var finalReport = null;

    var weeklyQ = db.collection("competition_replay_weekly_reports").where("campaign_id", "==", campaignId);
    var monthlyQ = db.collection("competition_replay_monthly_reports").where("campaign_id", "==", campaignId);
    var finalQ = db.collection("competition_replay_final_reports").where("campaign_id", "==", campaignId);

    return Promise.all([weeklyQ.get(), monthlyQ.get(), finalQ.get()])
      .then(function (results) {
        results[0].forEach(function (doc) {
          var d = doc.data();
          var key = d.week_key || doc.id;
          weekly[key] = d;
        });
        results[1].forEach(function (doc) {
          var d = doc.data();
          var key = d.month_key || doc.id;
          monthly[key] = d;
        });
        if (!results[2].empty) {
          finalReport = results[2].docs[0].data();
        }
        return { weeklyReports: weekly, monthlyReports: monthly, finalReport: finalReport };
      });
  }

  function listReplayRuns(limit) {
    var db = getDb();
    if (!db) return Promise.resolve([]);
    return db
      .collection("competition_replay_runs")
      .orderBy("trading_date", "desc")
      .limit(limit || 50)
      .get()
      .then(function (snap) {
        var runs = [];
        snap.forEach(function (doc) {
          var d = doc.data();
          var m = d.manifest || {};
          runs.push({
            replayRunId: d.replay_run_id || doc.id,
            tradingDate: m.trading_date || d.trading_date,
            leakageSummary: m.leakage_summary || d.leakage_summary,
            campaignId: m.campaign_id || d.campaign_id,
          });
        });
        return runs;
      })
      .catch(function () {
        return db
          .collection("competition_replay_runs")
          .limit(limit || 50)
          .get()
          .then(function (snap) {
            var runs = [];
            snap.forEach(function (doc) {
              var d = doc.data();
              runs.push({
                replayRunId: d.replay_run_id || doc.id,
                tradingDate: (d.manifest || {}).trading_date,
                leakageSummary: (d.manifest || {}).leakage_summary,
                campaignId: (d.manifest || {}).campaign_id,
              });
            });
            return runs;
          });
      });
  }

  function mergeReportsIntoPayload(payload, reports) {
    if (!payload) return payload;
    payload.weeklyReports = reports.weeklyReports || {};
    payload.monthlyReports = reports.monthlyReports || {};
    payload.finalReport = reports.finalReport || null;
    return payload;
  }

  global.CompetitionReplayFirestore = {
    hasFirestoreConfig: hasFirestoreConfig,
    isPublicStaticHost: isPublicStaticHost,
    preferFirestoreBackend: preferFirestoreBackend,
    loadReplayRun: loadReplayRun,
    loadCampaignReports: loadCampaignReports,
    listReplayRuns: listReplayRuns,
    mergeReportsIntoPayload: mergeReportsIntoPayload,
  };
})(window);
