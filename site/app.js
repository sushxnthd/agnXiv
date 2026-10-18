const container = document.getElementById("jobs");

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"
  })[character]);
}

function field(text, label) {
  const safe = label.replace(/[-/\\^$*+?.()|[\]{}]/g, "\\$&");
  const match = String(text || "").match(
    new RegExp("\\*\\*" + safe + ":\\*\\*\\s*([^\\n]+)", "i")
  );
  return match ? match[1].replace(/`/g, "").trim() : "";
}

function evidenceState(comment, issueState) {
  if (!comment) return issueState === "open" ? "RUNNING" : "INCONCLUSIVE";
  const verdict = field(comment.body, "Verdict").toUpperCase();
  if (verdict === "VERIFIED") return "REPRODUCED";
  if (verdict === "PARTIALLY_VERIFIED") return "PARTIALLY_REPRODUCED";
  if (verdict === "CONTRADICTED") return "RESULT_DIVERGENCE";
  if (verdict === "UNABLE_TO_VERIFY") return "INCONCLUSIVE";
  const status = field(comment.body, "Status").toLowerCase();
  if (status === "needs_review") return "EVIDENCE_INCOMPLETE";
  if (status === "failed") return "EXECUTION_BLOCKED";
  return issueState === "open" ? "RUNNING" : "INCONCLUSIVE";
}

function stateClass(state) {
  if (state === "REPRODUCED") return "verified";
  if (state === "RESULT_DIVERGENCE") return "failed";
  return "review";
}

async function enrichedIssue(issue) {
  try {
    const response = await fetch(issue.comments_url + "?per_page=100");
    const comments = response.ok ? await response.json() : [];
    const comment = [...comments].reverse().find((item) =>
      item.body && item.body.includes("## AgnXiv result")
    );
    return { issue, state: evidenceState(comment, issue.state) };
  } catch (error) {
    return { issue, state: issue.state === "open" ? "RUNNING" : "INCONCLUSIVE" };
  }
}

async function loadJobs() {
  try {
    const response = await fetch(
      "https://api.github.com/repos/sushxnthd/agnXiv/issues?state=all&per_page=30",
      { headers: { Accept: "application/vnd.github+json" } }
    );
    if (!response.ok) throw new Error("GitHub API unavailable");
    const issues = (await response.json())
      .filter((item) => !item.pull_request && item.title.startsWith("[AgnXiv Verify]"))
      .slice(0, 7);

    if (!issues.length) {
      container.innerHTML = '<div class="loading">No public verification runs yet.</div>';
      return;
    }

    const records = await Promise.all(issues.map(enrichedIssue));
    container.innerHTML = records.map(({ issue, state }) => {
      const title = issue.title.replace("[AgnXiv Verify]", "").trim() || "Verification request";
      const date = new Date(issue.created_at).toLocaleDateString(undefined, {
        year:"numeric",month:"short",day:"numeric"
      });
      return '<a class="run-row" href="./result.html?issue=' + issue.number + '">' +
        '<div><div class="run-title">' + esc(title) + '</div>' +
        '<div class="run-meta">AX-GH-' + String(issue.number).padStart(5,"0") +
        ' · @' + esc(issue.user.login) + '</div></div>' +
        '<div class="run-date">' + date + '</div>' +
        '<div class="run-state"><span class="badge ' + stateClass(state) + '">' +
        esc(state) + '</span></div></a>';
    }).join("");
  } catch (error) {
    container.innerHTML = '<div class="loading">Public runs are temporarily unavailable.</div>';
  }
}

loadJobs();
