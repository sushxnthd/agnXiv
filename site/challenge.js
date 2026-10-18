const params = new URLSearchParams(window.location.search);
const targetIssue = Number(params.get("issue"));
const form = document.getElementById("challenge-form");
const modal = document.getElementById("challenge-modal");
let target = null;

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"
  })[char]);
}

function extract(text, label) {
  const safe = label.replace(/[-/\\^$*+?.()|[\]{}]/g, "\\$&");
  const match = String(text || "").match(
    new RegExp("\\*\\*" + safe + ":\\*\\*\\s*([^\\n]+)", "i")
  );
  return match ? match[1].replace(/`/g, "").trim() : "";
}

function section(text, heading) {
  const safe = heading.replace(/[-/\\^$*+?.()|[\]{}]/g, "\\$&");
  const match = String(text || "").match(
    new RegExp("^###\\s+" + safe + "\\s*$\\n+([^#]+?)(?=^###\\s+|$)", "im")
  );
  return match ? match[1].trim().replace(/^_No response_$/i, "") : "";
}

async function loadTarget() {
  const box = document.getElementById("challenge-target");
  if (!Number.isInteger(targetIssue) || targetIssue <= 0) {
    box.innerHTML = '<strong>No target attempt selected.</strong><span>Open a verification record and choose Challenge this attempt.</span>';
    form.querySelector('button[type="submit"]').disabled = true;
    return;
  }

  try {
    const issueUrl = "https://api.github.com/repos/sushxnthd/agnXiv/issues/" + targetIssue;
    const responses = await Promise.all([
      fetch(issueUrl),
      fetch(issueUrl + "/comments?per_page=100")
    ]);
    if (!responses[0].ok) throw new Error("target unavailable");
    const issue = await responses[0].json();
    const comments = responses[1].ok ? await responses[1].json() : [];
    const resultComment = [...comments].reverse().find((item) =>
      item.body && item.body.includes("## AgnXiv result")
    );
    const raw = resultComment ? resultComment.body : "";
    target = {
      issue: targetIssue,
      attemptId: "AX-GH-" + targetIssue,
      paper: section(issue.body, "arXiv ID"),
      claim: extract(raw, "Claim"),
      repository: extract(raw, "Repository") || section(issue.body, "Public GitHub repository"),
      expected: extract(raw, "Expected")
    };
    box.innerHTML =
      '<div><div class="eyebrow">Target attempt</div><strong>' + esc(target.attemptId) + '</strong>' +
      '<p>' + esc(target.paper ? "arXiv:" + target.paper : target.repository) + '</p>' +
      (target.claim ? '<p class="challenge-claim">' + esc(target.claim) + '</p>' : '') + '</div>' +
      '<a href="./result.html?issue=' + targetIssue + '">Open record →</a>';
  } catch (error) {
    box.innerHTML = '<strong>Target attempt unavailable.</strong><span>The public record could not be loaded.</span>';
    form.querySelector('button[type="submit"]').disabled = true;
  }
}

function normalizeRepo(value) {
  return value.trim()
    .replace(/^https?:\/\/github\.com\//i, "")
    .replace(/\.git$/i, "")
    .replace(/^\/+|\/+$/g, "");
}

function validRepo(value) {
  return /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(normalizeRepo(value));
}

function buildBody() {
  const repository = normalizeRepo(document.getElementById("challenge-repository").value);
  const ref = document.getElementById("challenge-ref").value.trim();
  const observed = document.getElementById("challenge-observed").value.trim();
  const evidenceUrl = document.getElementById("challenge-evidence-url").value.trim();
  const rationale = document.getElementById("challenge-rationale").value.trim();

  return [
    "### Target AgnXiv attempt", "", target.attemptId, "",
    "### Paper", "", target.paper || "_No response_", "",
    "### Target claim", "", target.claim || "_See target attempt_", "",
    "### Target reported result", "", target.expected || "_See target attempt_", "",
    "### Challenger evidence repository", "", repository, "",
    "### Challenger Git ref", "", ref, "",
    "### Challenger observed result", "", observed, "",
    "### Evidence URL", "", evidenceUrl || "_No response_", "",
    "### What diverged?", "", rationale, "",
    "### Acknowledgement", "",
    "- [x] This challenge reports an evidence-specific divergence and does not allege misconduct or universal falsity.", ""
  ].join("\n");
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!target) return;
  const repository = normalizeRepo(document.getElementById("challenge-repository").value);
  const ref = document.getElementById("challenge-ref").value.trim();
  const observed = document.getElementById("challenge-observed").value.trim();
  const rationale = document.getElementById("challenge-rationale").value.trim();
  if (!validRepo(repository) || !ref || !observed || !rationale) return;

  const url = new URL("https://github.com/sushxnthd/agnXiv/issues/new");
  url.searchParams.set("title", "[AgnXiv Challenge] " + target.attemptId);
  url.searchParams.set("body", buildBody());
  document.getElementById("challenge-submit").href = url.toString();

  document.getElementById("challenge-summary").innerHTML =
    '<div><span>Target</span><b>' + esc(target.attemptId) + '</b></div>' +
    '<div><span>Paper</span><b>' + esc(target.paper || "See target") + '</b></div>' +
    '<div><span>Evidence</span><b>' + esc(repository + "@" + ref) + '</b></div>' +
    '<div><span>Observed</span><b>' + esc(observed) + '</b></div>';
  modal.classList.remove("hidden");
});

["challenge-modal-close","challenge-cancel"].forEach((id) => {
  document.getElementById(id).addEventListener("click", () => modal.classList.add("hidden"));
});
modal.addEventListener("click", (event) => {
  if (event.target === modal) modal.classList.add("hidden");
});

loadTarget();
