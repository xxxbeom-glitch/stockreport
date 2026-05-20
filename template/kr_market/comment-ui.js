/**
 * UI comment rules (05_UI_COMMENT_RULES.md)
 * - max 2 lines, memo tone, no 입니다/합니다, ellipsis via CSS
 */
(function () {
  "use strict";

  var FORMAL_RE = /(습니다|입니다|합니다|됩니다|겠습니다|이에요|예요|해요)([.?!]?\s*)/g;
  var BUY_RE = /(매수하세요|반드시 사야|무조건 갑니다|지금 안 사면 끝|확실히 오릅니다|꼭 사야|지금 사야|들어가세요|진입하세요)/g;
  var MAX_LINES = 2;

  function toMemoTone(text) {
    var raw = String(text || "").trim();
    if (!raw) return "";
    raw = raw.replace(BUY_RE, "");
    raw = raw.replace(FORMAL_RE, ". ");
    raw = raw.replace(/\s+/g, " ").replace(/\.+/g, ".").trim();
    return raw.replace(/^\.+|\.+$/g, "").trim();
  }

  function clampLines(text) {
    var memo = toMemoTone(text);
    if (!memo) return "";
    var lines = memo.split(/\n/).map(function (l) {
      return l.trim();
    }).filter(Boolean);
    if (lines.length === 1 && lines[0].length > 96) {
      lines = lines[0].split(/(?<=[.!?])\s+/).map(function (p) {
        return p.trim();
      }).filter(Boolean);
    }
    return lines.slice(0, MAX_LINES).join("\n");
  }

  function applyComment(el) {
    if (!el || el.dataset.commentApplied === "1") return;
    var source = el.getAttribute("data-comment") || el.textContent || "";
    var formatted = clampLines(source);
    if (!formatted) return;
    el.textContent = "";
    formatted.split("\n").forEach(function (line, i) {
      if (i > 0) el.appendChild(document.createElement("br"));
      el.appendChild(document.createTextNode(line));
    });
    el.dataset.commentApplied = "1";
    el.setAttribute("aria-label", formatted.replace(/\n/g, " "));
  }

  function initUiComments() {
    document.querySelectorAll(".ai-comment").forEach(applyComment);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initUiComments);
  } else {
    initUiComments();
  }
})();
