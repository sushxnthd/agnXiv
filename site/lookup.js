const form = document.getElementById("lookup-form");
const input = document.getElementById("lookup-query");
const result = document.getElementById("lookup-result");

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"
  })[char]);
}

function normalizeArxiv(value) {
  return value.trim()
    .replace(/^https?:\/\/(www\.)?arxiv\.org\/(abs|pdf)\//i, "")
    .replace(/\.pdf$/i, "");
}

function issueNumberFromRecord(value) {
  const match = value.trim().match(/^(?:AX-GH-)?(\d+)$/i);
  return match ? Number(match[1]) : null;
}

function section(body, heading) {
  const safe = heading.replace(/[-/\\^$*+?.()|[\]{}]/g, "\\$&");
  const match = String(body || "").match(
    new RegExp("^###\\s+" + safe + "\\s*$\\n+([^#]+?)(?=^###\\s+|$)", "im")
  );
  return match ? match[1].trim().replace(/^_No response_$/i, "") : "";
}

function field(text, label) {
  const safe = label.replace(/[-/\\^$*+?.()|[\]{}]/g, "\\$&");
  const match = String(text || "").match(
    new RegExp("\\*\\*" + safe + ":\\*\\*\\s*(?:\\*\\*)?([^\\n*]+)", "i")
  );
  return match ? match[1].replace(/`/g, "").trim() : "";
}

function evidenceState(comment, issue) {
  if (!comment) return issue.state === "open" ? "RUNNING" : "INCONCLUSIVE";
  const verdict = field(comment.body, "Verdict").toUpperCase();
  if (verdict === "VERIFIED") return "REPRODUCED";
  if (verdict === "PARTIALLY_VERIFIED") return "PARTIALLY_REPRODUCED";
  if (verdict === "CONTRADICTED") return "RESULT_DIVERGENCE";
  if (verdict === "UNABLE_TO_VERIFY") return "INCONCLUSIVE";
  const status = field(comment.body, "Status").toLowerCase();
  if (status === "needs_review") return "EVIDENCE_INCOMPLETE";
  if (status === "failed") return "EXECUTION_BLOCKED";
  return issue.state === "open" ? "RUNNING" : "INCONCLUSIVE";
}

function badgeClass(state) {
  if (state === "REPRODUCED") return "verified";
  if (state === "RESULT_DIVERGENCE") return "failed";
  return "review";
}

async function loadIssueAttempt(issue) {
  const response = await fetch(issue.comments_url + "?per_page=100");
  const comments = response.ok ? await response.json() : [];
  const comment = [...comments].reverse().find((item) =>
    item.body && item.body.includes("## AgnXiv result")
  );
  const state = evidenceState(comment, issue);
  return {
    number: issue.number,
    state,
    created: issue.created_at,
    repository: comment ? field(comment.body, "Repository") : section(issue.body, "Public GitHub repository"),
    gitRef: comment ? field(comment.body, "Git ref") : section(issue.body, "Git ref"),
    commit: comment ? field(comment.body, "Pinned commit") : "",
    automation: comment ? field(comment.body, "Automation") : "",
    expected: comment ? field(comment.body, "Expected") : "",
    observed: comment ? field(comment.body, "Observed") : ""
  };
}

function renderNoRecord(arxiv) {
  result.classList.remove("hidden");
  result.innerHTML =
    '<div class="lookup-empty"><div class="eyebrow">No public evidence yet</div>' +
    '<h2>AgnXiv has not recorded a verification attempt for ' + esc(arxiv) + '.</h2>' +
    '<p>This is an absence of evidence, not evidence of failure. You can start the first public attempt.</p>' +
    '<a class="button primary" href="./verify.html?arxiv=' + encodeURIComponent(arxiv) + '">Verify this paper</a></div>';
}

function renderRecord(arxiv, attempts, challenges) {
  const counts = attempts.reduce((acc, attempt) => {
    acc[attempt.state] = (acc[attempt.state] || 0) + 1;
    return acc;
  }, {});
  let overall = "UNRESOLVED";
  if (counts.RESULT_DIVERGENCE && counts.REPRODUCED) overall = "MIXED_EVIDENCE";
  else if (counts.RESULT_DIVERGENCE) overall = "RESULT_DIVERGENCE";
  else if (counts.REPRODUCED) overall = "REPRODUCED";

  result.classList.remove("hidden");
  result.innerHTML =
    '<div class="lookup-record-head"><div><div class="eyebrow">Living evidence record</div>' +
    '<h2>arXiv:' + esc(arxiv) + '</h2><p>' + attempts.length + ' public AgnXiv attempt' +
    (attempts.length === 1 ? '' : 's') + '</p></div>' +
    '<span class="badge ' + badgeClass(overall) + '">' + esc(overall) + '</span></div>' +
    '<div class="lookup-stats">' +
      '<div><strong>' + (counts.REPRODUCED || 0) + '</strong><span>reproduced</span></div>' +
      '<div><strong>' + (counts.RESULT_DIVERGENCE || 0) + '</strong><span>divergence</span></div>' +
      '<div><strong>' + ((counts.EVIDENCE_INCOMPLETE || 0) + (counts.INCONCLUSIVE || 0) + (counts.EXECUTION_BLOCKED || 0)) + '</strong><span>unresolved</span></div>' +
      '<div><strong>' + challenges.length + '</strong><span>challenges</span></div>' +
    '</div>' +
    '<div class="attempt-list">' + attempts.map((attempt) =>
      '<a class="attempt-row" href="./result.html?issue=' + attempt.number + '">' +
        '<div><div class="attempt-id">AX-GH-' + attempt.number + '</div>' +
        '<strong>' + esc(attempt.repository || "Unknown repository") + '</strong>' +
        '<span>' + new Date(attempt.created).toLocaleString() + '</span></div>' +
        '<div class="attempt-details">' +
          (attempt.automation ? '<span>' + esc(attempt.automation) + '</span>' : '') +
          (attempt.commit ? '<code>' + esc(attempt.commit.slice(0, 10)) + '</code>' : '') +
          '<span class="badge ' + badgeClass(attempt.state) + '">' + esc(attempt.state) + '</span>' +
        '</div></a>'
    ).join("") + '</div>' +
    '<div class="lookup-actions"><a class="button primary" href="./verify.html?arxiv=' + encodeURIComponent(arxiv) + '">Add an independent attempt</a></div>';
}

async function search(query) {
  const issueNumber = issueNumberFromRecord(query);
  if (issueNumber && !query.includes(".")) {
    window.location.href = "./result.html?issue=" + issueNumber;
    return;
  }

  const arxiv = normalizeArxiv(query);
  if (!arxiv) return;

  result.classList.remove("hidden");
  result.innerHTML = '<div class="lookup-loading"><div class="spinner"></div><p>Searching public AgnXiv evidence…</p></div>';

  try {
    const response = await fetch("https://api.github.com/repos/sushxnthd/agnXiv/issues?state=all&per_page=100");
    if (!response.ok) throw new Error("registry unavailable");
    const allIssues = (await response.json()).filter((item) => !item.pull_request);
    const issues = allIssues.filter((item) =>
      item.title.startsWith("[AgnXiv Verify]") &&
      normalizeArxiv(section(item.body, "arXiv ID")) === arxiv
    );
    const challenges = allIssues.filter((item) =>
      item.title.startsWith("[AgnXiv Challenge]") &&
      normalizeArxiv(section(item.body, "Paper")) === arxiv
    );
    if (!issues.length) {
      renderNoRecord(arxiv);
      return;
    }
    const attempts = await Promise.all(issues.map(loadIssueAttempt));
    attempts.sort((a, b) => new Date(b.created) - new Date(a.created));
    renderRecord(arxiv, attempts, challenges);
  } catch (error) {
    result.innerHTML = '<div class="lookup-empty"><h2>Registry temporarily unavailable.</h2><p>The public evidence index could not be loaded right now.</p></div>';
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  search(input.value);
});

const initial = new URLSearchParams(window.location.search).get("q");
if (initial) {
  input.value = initial;
  search(initial);
}
