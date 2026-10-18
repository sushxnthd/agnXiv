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
  const match = text.match(pattern);
  return match ? match[1].replace(/`/g, "").trim() : null;
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

function badgeClass(status) {
  const upper = String(status || "").toUpperCase();
  if (upper.includes("VERIFIED") && !upper.includes("UNABLE")) return "verified";
  if (upper.includes("CONTRADICTED") || upper.includes("FAILED")) return "failed";
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
    renderError("Verification record unavailable.", "The GitHub-backed public record could not be loaded right now.");
  }
}

function render(issue, comment) {
  const raw = comment ? comment.body : "";
  const status = extract(raw, "Status") || (issue.state === "open" ? "RUNNING / REVIEW" : "COMPLETED");
  const repository = extract(raw, "Repository") || "Unknown repository";
  const gitRef = extract(raw, "Git ref") || "Unknown";
  const commit = extract(raw, "Pinned commit");
  const automation = extract(raw, "Automation");
  const verdict = extract(raw, "Verdict");
  const claim = extract(raw, "Claim");
  const expected = extract(raw, "Expected");
  const observed = extract(raw, "Observed");
  const stopped = blockers(raw);
  const title = issue.title.replace("[AgnXiv Verify]", "").trim() || "Verification request";
  const stateClass = badgeClass(verdict || status);

  let primary = "";
  if (automation) {
    const match = automation.match(/[0-9.]+%/);
    const percent = match ? match[0] : automation;
    primary =
      '<section class="result-panel">' +
      '<div class="eyebrow">Automation coverage</div>' +
      '<div class="big-metric">' + esc(percent) + '</div>' +
      '<p class="subtle">' + esc(automation) + '</p>' +
      '<div class="progress"><span style="width:' + esc(percent) + '"></span></div>' +
      '</section>';
  } else if (verdict) {
    primary =
      '<section class="result-panel">' +
      '<div class="eyebrow">Claim verdict</div>' +
      '<div class="big-metric">' + esc(verdict) + '</div>' +
      (claim ? '<p>' + esc(claim) + '</p>' : '') +
      '</section>';
  } else {
    primary =
      '<section class="result-panel">' +
      '<div class="eyebrow">Execution</div>' +
      '<h2>Verification is still running.</h2>' +
      '<p class="subtle">This page will show the scientific record as soon as the GitHub-hosted worker publishes it.</p>' +
      '</section>';
  }

  const blockersHtml = stopped.length
    ? '<section class="result-panel" style="margin-top:28px"><h2>Why AgnXiv stopped</h2>' +
      '<ul class="blocker-list">' + stopped.map((item) => '<li>' + esc(item) + '</li>').join('') +
      '</ul></section>'
    : '';

  root.innerHTML =
    '<section class="result-header">' +
      '<div><div class="eyebrow">AgnXiv verification #' + issue.number + '</div>' +
      '<h1>' + esc(title) + '</h1>' +
      '<p>Submitted ' + new Date(issue.created_at).toLocaleString() + '</p></div>' +
      '<span class="badge ' + stateClass + '">' + esc(verdict || status) + '</span>' +
    '</section>' +
    '<div class="result-grid"><div>' + primary + blockersHtml + '</div>' +
      '<aside class="result-panel"><h2>Provenance</h2><dl class="fact-list">' +
        '<div><dt>Repository</dt><dd>' + esc(repository) + '</dd></div>' +
        '<div><dt>Submitted ref</dt><dd>' + esc(gitRef) + '</dd></div>' +
        '<div><dt>Pinned commit</dt><dd>' + esc(commit || "resolving") + '</dd></div>' +
        (expected ? '<div><dt>Expected</dt><dd>' + esc(expected) + '</dd></div>' : '') +
        (observed ? '<div><dt>Observed</dt><dd>' + esc(observed) + '</dd></div>' : '') +
        '<div><dt>Public record</dt><dd>GitHub issue #' + issue.number + '</dd></div>' +
      '</dl><a class="raw-link" href="' + issue.html_url + '">Inspect raw GitHub record →</a></aside>' +
    '</div>' +
    '<div style="margin-top:28px"><a class="button primary" href="./verify.html">Start another verification</a></div>';
}

function renderError(title, message) {
  root.innerHTML =
    '<div class="error-state"><div class="eyebrow">AgnXiv</div>' +
    '<h1>' + esc(title) + '</h1><p>' + esc(message) + '</p>' +
    '<a class="button primary" href="./verify.html">Start a verification</a></div>';
}

load();
