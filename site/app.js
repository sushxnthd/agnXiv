const container = document.getElementById("jobs");

async function loadJobs() {
  try {
    const response = await fetch(
      "https://api.github.com/repos/sushxnthd/agnXiv/issues?state=all&per_page=20",
      { headers: { Accept: "application/vnd.github+json" } }
    );
    if (!response.ok) throw new Error("GitHub API unavailable");
    const issues = (await response.json())
      .filter((item) => !item.pull_request && item.title.startsWith("[AgnXiv Verify]"))
      .slice(0, 6);

    if (!issues.length) {
      container.innerHTML = '<p class="muted">No public verification requests yet.</p>';
      return;
    }

    container.innerHTML = issues.map((issue) => {
      const state = issue.state === "open" ? "RUNNING / REVIEW" : "COMPLETED";
      const date = new Date(issue.created_at).toLocaleDateString(undefined, {
        year: "numeric", month: "short", day: "numeric"
      });
      return `
        <a class="job" href="${issue.html_url}">
          <div>
            <div class="job-title">${escapeHtml(issue.title.replace("[AgnXiv Verify]", "").trim() || "Verification request")}</div>
            <div class="job-meta">#${issue.number} · ${date} · @${escapeHtml(issue.user.login)}</div>
          </div>
          <span class="state">${state}</span>
        </a>`;
    }).join("");
  } catch (error) {
    container.innerHTML = '<p class="muted">Recent requests are available directly on GitHub.</p>';
  }
}

function escapeHtml(value) {
  return value.replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  })[character]);
}

loadJobs();
