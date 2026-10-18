const form = document.getElementById("verify-form");
const modeInput = document.getElementById("mode");
const arxivInput = document.getElementById("arxiv");
const repoInput = document.getElementById("repository");
const refInput = document.getElementById("git-ref");
const specInput = document.getElementById("spec-path");
const modal = document.getElementById("submit-modal");
const githubSubmit = document.getElementById("github-submit");

function normalizeArxiv(value) {
  return value.trim()
    .replace(/^https?:\/\/(www\.)?arxiv\.org\/(abs|pdf)\//i, "")
    .replace(/\.pdf$/i, "");
}

function normalizeRepo(value) {
  return value.trim()
    .replace(/^https?:\/\/github\.com\//i, "")
    .replace(/\.git$/i, "")
    .replace(/^\/+|\/+$/g, "");
}

function setMode(mode) {
  modeInput.value = mode;
  document.querySelectorAll(".mode-option").forEach((button) => {
    button.classList.toggle("active", button.dataset.mode === mode);
  });
  document.querySelectorAll(".auto-field").forEach((node) => node.classList.toggle("hidden", mode !== "auto"));
  document.querySelectorAll(".manifest-field").forEach((node) => node.classList.toggle("hidden", mode !== "manifest"));
  arxivInput.required = mode === "auto";
  specInput.required = mode === "manifest";
  updatePreflight();
}

function validRepo(value) {
  return /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(normalizeRepo(value));
}

function validArxiv(value) {
  return /^(?:[a-z-]+\/\d{7}|\d{4}\.\d{4,5})(?:v\d+)?$/i.test(normalizeArxiv(value));
}

function setCheck(id, statusId, ok, waiting, goodText, badText) {
  const icon = document.getElementById(id);
  const status = document.getElementById(statusId);
  icon.className = "check " + (waiting ? "neutral" : ok ? "good" : "bad");
  icon.textContent = waiting ? "○" : ok ? "●" : "×";
  status.textContent = waiting ? "Waiting" : ok ? goodText : badText;
}

function updatePreflight() {
  const mode = modeInput.value;
  const repo = repoInput.value.trim();
  const arxiv = arxivInput.value.trim();
  setCheck("repo-check", "repo-status", validRepo(repo), !repo, "Looks valid", "Check repository");
  if (mode === "auto") {
    setCheck("paper-check", "paper-status", validArxiv(arxiv), !arxiv, "Looks valid", "Check arXiv ID");
  } else {
    setCheck("paper-check", "paper-status", Boolean(specInput.value.trim()), !specInput.value.trim(), "Manifest set", "Add manifest path");
  }
}

function requestBody() {
  const mode = modeInput.value;
  const repo = normalizeRepo(repoInput.value);
  const arxiv = normalizeArxiv(arxivInput.value);
  const ref = refInput.value.trim() || "main";
  const spec = specInput.value.trim();
  const modeLabel = mode === "auto"
    ? "Auto-verify from arXiv + repository"
    : "Verify an agnxiv.json manifest";
  return [
    "### Mode", "", modeLabel, "",
    "### Public GitHub repository", "", repo, "",
    "### Git ref", "", ref, "",
    "### arXiv ID", "", mode === "auto" ? arxiv : "_No response_", "",
    "### Verification manifest path", "", mode === "manifest" ? spec : "_No response_", "",
    "### Acknowledgement", "",
    "- [x] I understand that public research code may execute inside AgnXiv's isolated no-network verification sandbox.", ""
  ].join("\n");
}

function escapeHtml(value) {
  return value.replace(/[&<>"']/g, (char) => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"
  })[char]);
}

function openPreparedRequest() {
  const mode = modeInput.value;
  const repo = normalizeRepo(repoInput.value);
  const arxiv = normalizeArxiv(arxivInput.value);
  const ref = refInput.value.trim() || "main";
  const spec = specInput.value.trim();

  if (!validRepo(repo)) {
    repoInput.focus();
    updatePreflight();
    return;
  }
  if (mode === "auto" && !validArxiv(arxiv)) {
    arxivInput.focus();
    updatePreflight();
    return;
  }
  if (mode === "manifest" && (!spec || spec.startsWith("/") || spec.split("/").includes(".."))) {
    specInput.focus();
    return;
  }

  const label = mode === "auto" ? (arxiv || "paper") : (spec || "manifest");
  const title = "[AgnXiv Verify] " + repo + " · " + label;
  const url = new URL("https://github.com/sushxnthd/agnXiv/issues/new");
  url.searchParams.set("title", title);
  url.searchParams.set("body", requestBody());
  githubSubmit.href = url.toString();

  const values = [
    ["Mode", mode === "auto" ? "AUTO_VERIFY" : "VERIFY_SPEC"],
    ["Repository", repo],
    ["Git ref", ref],
    [mode === "auto" ? "Paper" : "Manifest", mode === "auto" ? arxiv : spec]
  ];
  document.getElementById("request-summary").innerHTML = values.map((entry) =>
    "<div><span>" + entry[0] + "</span><b>" + escapeHtml(entry[1]) + "</b></div>"
  ).join("");

  modal.classList.remove("hidden");
}

document.querySelectorAll(".mode-option").forEach((button) => {
  button.addEventListener("click", () => setMode(button.dataset.mode));
});
[arxivInput, repoInput, refInput, specInput].forEach((input) => input.addEventListener("input", updatePreflight));
form.addEventListener("submit", (event) => {
  event.preventDefault();
  openPreparedRequest();
});
document.getElementById("load-demo").addEventListener("click", () => {
  setMode("auto");
  arxivInput.value = "1403.6652";
  repoInput.value = "phanein/deepwalk";
  refInput.value = "6e6dff245e4692e9bea47e9017c1034e51afbf29";
  updatePreflight();
  window.scrollTo({ top: 0, behavior: "smooth" });
});
["modal-close", "modal-cancel"].forEach((id) => {
  document.getElementById(id).addEventListener("click", () => modal.classList.add("hidden"));
});
modal.addEventListener("click", (event) => {
  if (event.target === modal) modal.classList.add("hidden");
});

const initialArxiv = new URLSearchParams(window.location.search).get("arxiv");
if (initialArxiv) {
  arxivInput.value = normalizeArxiv(initialArxiv);
}
updatePreflight();
