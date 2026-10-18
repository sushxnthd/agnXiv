const root = document.getElementById("result-root");
const params = new URLSearchParams(window.location.search);
const issueNumber = Number(params.get("issue"));

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"
  })[char]);
}

function extract(text, label) {
  const safe = label.replace(/[-/\\^$*+?.()|[\]{}]/g, "\\$&");
  const pattern = new RegExp("\\*\\*" + safe + ":\\*\\*\\s*([^\\n]+)", "i");
  const match = String(text || "").match(pattern);
  return match ? match[1].replace(/`/g, "").trim() : null;
}

function section(text, heading) {
  const safe = heading.replace(/[-/\\^$*+?.()|[\]{}]/g, "\\$&");
  const match = String(text || "").match(
    new RegExp("^###\\s+" + safe + "\\s*$\\n+([^#]+?)(?=^###\\s+|$)", "im")
  );
  return match ? match[1].trim().replace(/^_No response_$/i, "") : "";
}

function blockers(text) {
  const marker = "### Why AgnXiv stopped";
  const start = text.indexOf(marker);
  if (start < 0) return [];
  return text.slice(start + marker.length)
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.startsWith("- "))
    .map((line) => line.slice(2));
}

function evidenceState(verdict, status, issueState) {
  const rawVerdict = String(verdict || "").toUpperCase();
  if (rawVerdict === "VERIFIED") return "REPRODUCED";
  if (rawVerdict === "PARTIALLY_VERIFIED") return "PARTIALLY_REPRODUCED";
  if (rawVerdict === "CONTRADICTED") return "RESULT_DIVERGENCE";
  if (rawVerdict === "UNABLE_TO_VERIFY") return "INCONCLUSIVE";
  const rawStatus = String(status || "").toLowerCase();
  if (rawStatus === "needs_review") return "EVIDENCE_INCOMPLETE";
  if (rawStatus === "failed") return "EXECUTION_BLOCKED";
  return issueState === "open" ? "RUNNING" : "INCONCLUSIVE";
}

function badgeClass(status) {
  const upper = String(status || "").toUpperCase();
  if (upper === "REPRODUCED") return "verified";
  if (upper === "RESULT_DIVERGENCE") return "failed";
  return "review";
}

async function load() {
  if (!Number.isInteger(issueNumber) || issueNumber <= 0) {
    renderError("No verification record selected.", "Open a run from the registry or start a new verification.");
    return;
  }
  try {
    const issueUrl = "https://api.github.com/repos/sushxnthd/agnXiv/issues/" + issueNumber;
    const commentsUrl = issueUrl + "/comments?per_page=100";
    const responses = await Promise.all([fetch(issueUrl), fetch(commentsUrl)]);
    if (!responses[0].ok) throw new Error("Issue not found");
    const issue = await responses[0].json();
    const comments = responses[1].ok ? await responses[1].json() : [];
    const resultComment = [...comments].reverse().find((comment) =>
      comment.body && comment.body.includes("## AgnXiv result")
    );
    render(issue, resultComment);
  } catch (error) {
    renderError("Verification record unavailable.", "The public AgnXiv record could not be loaded right now.");
  }
}

function render(issue, comment) {
  const raw = comment ? comment.body : "";
  const status = extract(raw, "Status") || (issue.state === "open" ? "RUNNING" : "COMPLETED");
  const repository = extract(raw, "Repository") || section(issue.body, "Public GitHub repository") || "Unknown repository";
  const gitRef = extract(raw, "Git ref") || section(issue.body, "Git ref") || "Unknown";
  const paperId = section(issue.body, "arXiv ID");
  const commit = extract(raw, "Pinned commit");
  const automation = extract(raw, "Automation");
  const verdict = extract(raw, "Verdict");
  const claim = extract(raw, "Claim");
  const expected = extract(raw, "Expected");
  const observed = extract(raw, "Observed");
  const stopped = blockers(raw);
  const title = issue.title.replace("[AgnXiv Verify]", "").trim() || "Verification request";
  const state = evidenceState(verdict, status, issue.state);
  const stateClass = badgeClass(state);

  let primary = "";
  if (automation) {
    const match = automation.match(/[0-9.]+%/);
    const percent = match ? match[0] : automation;
    primary =
      '<section class="result-panel">' +
      '<div class="eyebrow">Evidence state</div>' +
      '<div class="big-metric compact-metric">' + esc(state) + '</div>' +
      '<p class="subtle">Automation coverage: ' + esc(automation) + '</p>' +
      '<div class="progress"><span style="width:' + esc(percent) + '"></span></div>' +
      '</section>';
  } else if (verdict) {
    primary =
      '<section class="result-panel">' +
      '<div class="eyebrow">Evidence state</div>' +
      '<div class="big-metric compact-metric">' + esc(state) + '</div>' +
      (claim ? '<p>' + esc(claim) + '</p>' : '') +
      '<p class="verifier-note">Underlying verifier verdict: <code>' + esc(verdict) + '</code></p>' +
      '</section>';
  } else {
    primary =
      '<section class="result-panel">' +
      '<div class="eyebrow">Execution</div>' +
      '<h2>Verification is still running.</h2>' +
      '<p class="subtle">This page will show the scientific record as soon as the verification worker publishes it.</p>' +
      '</section>';
  }

  const blockersHtml = stopped.length
    ? '<section class="result-panel" style="margin-top:28px"><h2>Why AgnXiv stopped</h2>' +
      '<ul class="blocker-list">' + stopped.map((item) => '<li>' + esc(item) + '</li>').join('') +
      '</ul></section>'
    : '';

  const paperFact = paperId
    ? '<div><dt>Paper</dt><dd>arXiv:' + esc(paperId) + '</dd></div>'
    : '';
  const paperAction = paperId
    ? '<a class="button ghost" href="./lookup.html?q=' + encodeURIComponent(paperId) + '">View paper evidence</a>'
    : '';

  root.innerHTML =
    '<section class="result-header">' +
      '<div><div class="eyebrow">AgnXiv attempt · AX-GH-' + issue.number + '</div>' +
      '<h1>' + esc(title) + '</h1>' +
      '<p>Submitted ' + new Date(issue.created_at).toLocaleString() + '</p></div>' +
      '<span class="badge ' + stateClass + '">' + esc(state) + '</span>' +
    '</section>' +
    '<div class="result-grid"><div>' + primary + blockersHtml + '</div>' +
      '<aside class="result-panel"><h2>Provenance</h2><dl class="fact-list">' +
        paperFact +
        '<div><dt>Repository</dt><dd>' + esc(repository) + '</dd></div>' +
        '<div><dt>Submitted ref</dt><dd>' + esc(gitRef) + '</dd></div>' +
        '<div><dt>Pinned commit</dt><dd>' + esc(commit || "resolving") + '</dd></div>' +
        (expected ? '<div><dt>Expected</dt><dd>' + esc(expected) + '</dd></div>' : '') +
        (observed ? '<div><dt>Observed</dt><dd>' + esc(observed) + '</dd></div>' : '') +
        '<div><dt>Attempt ID</dt><dd>AX-GH-' + issue.number + '</dd></div>' +
      '</dl><a class="raw-link" href="' + issue.html_url + '">Inspect execution provenance →</a></aside>' +
    '</div>' +
    '<div class="result-actions">' + paperAction +
      '<a class="button primary" href="./verify.html' + (paperId ? '?arxiv=' + encodeURIComponent(paperId) : '') + '">Add an independent attempt</a></div>';
}

function renderError(title, message) {
  root.innerHTML =
    '<div class="error-state"><div class="eyebrow">AgnXiv</div>' +
    '<h1>' + esc(title) + '</h1><p>' + esc(message) + '</p>' +
    '<a class="button primary" href="./lookup.html">Search evidence</a></div>';
}

load();
