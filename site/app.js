const container = document.getElementById("jobs");

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"
  })[character]);
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

    container.innerHTML = issues.map((issue) => {
      const state = issue.state === "open" ? "RUNNING / REVIEW" : "COMPLETED";
      const title = issue.title.replace("[AgnXiv Verify]", "").trim() || "Verification request";
      const date = new Date(issue.created_at).toLocaleDateString(undefined, {
        year:"numeric",month:"short",day:"numeric"
      });
      const stateClass = issue.state === "open" ? "review" : "verified";
      return '<a class="run-row" href="./result.html?issue=' + issue.number + '">' +
        '<div><div class="run-title">' + esc(title) + '</div>' +
        '<div class="run-meta">AGN-' + String(issue.number).padStart(5,"0") +
        ' · @' + esc(issue.user.login) + '</div></div>' +
        '<div class="run-date">' + date + '</div>' +
        '<div class="run-state"><span class="badge ' + stateClass + '">' + state + '</span></div></a>';
    }).join("");
  } catch (error) {
    container.innerHTML = '<div class="loading">Public runs are temporarily unavailable.</div>';
  }
}
loadJobs();
