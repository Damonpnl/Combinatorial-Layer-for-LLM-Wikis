const state = {
  concepts: [],
  filtered: [],
  left: null,
  right: null,
  result: null,
  savedDraftPath: null,
};

const sectionOrder = [
  "Fusion Summary",
  "Interaction Boundary",
  "Mechanistic Interaction",
  "Product Opportunity",
  "Non-Obviousness Reason",
  "Primary Bottleneck",
  "Specific User Or Buyer",
  "Interaction Type",
  "Grounded Points",
  "Speculative Extensions",
  "Evidence Needed Before Promotion",
  "Novelty Score",
  "Plausibility Score",
  "Promotion Readiness",
  "System Design",
  "Research Question",
  "Falsification Test",
  "Cross-Niche Implications",
  "Failure Modes",
  "Related Canonical Pages",
];

const el = {
  conceptCount: document.querySelector("#conceptCount"),
  searchInput: document.querySelector("#searchInput"),
  nicheFilter: document.querySelector("#nicheFilter"),
  typeFilter: document.querySelector("#typeFilter"),
  tagFilter: document.querySelector("#tagFilter"),
  statusFilter: document.querySelector("#statusFilter"),
  emptyState: document.querySelector("#emptyState"),
  conceptList: document.querySelector("#conceptList"),
  leftSelection: document.querySelector("#leftSelection"),
  rightSelection: document.querySelector("#rightSelection"),
  pairingInsight: document.querySelector("#pairingInsight"),
  generateButton: document.querySelector("#generateButton"),
  regenerateButton: document.querySelector("#regenerateButton"),
  copyButton: document.querySelector("#copyButton"),
  saveButton: document.querySelector("#saveButton"),
  openDraftButton: document.querySelector("#openDraftButton"),
  submitButton: document.querySelector("#submitButton"),
  statusMessage: document.querySelector("#statusMessage"),
  resultView: document.querySelector("#resultView"),
};

function optionList(values, label) {
  return [`<option value="">All ${label}</option>`, ...values.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`)].join("");
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  })[char]);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok || payload.error) {
    throw new Error(payload.error || `Request failed: ${response.status}`);
  }
  return payload;
}

function setStatus(message, isError = false) {
  el.statusMessage.textContent = message;
  el.statusMessage.classList.toggle("error", isError);
}

function hydrateFilters() {
  const niches = [...new Set(state.concepts.map((item) => item.niche))].sort();
  const types = [...new Set(state.concepts.map((item) => item.type))].sort();
  const tags = [...new Set(state.concepts.flatMap((item) => item.tags))].sort();
  const statuses = [...new Set(state.concepts.map((item) => item.status))].sort();
  el.nicheFilter.innerHTML = optionList(niches, "niches");
  el.typeFilter.innerHTML = optionList(types, "types");
  el.tagFilter.innerHTML = optionList(tags, "tags");
  el.statusFilter.innerHTML = optionList(statuses, "statuses");
}

function applyFilters() {
  const search = el.searchInput.value.trim().toLowerCase();
  const niche = el.nicheFilter.value;
  const type = el.typeFilter.value;
  const tag = el.tagFilter.value;
  const status = el.statusFilter.value;

  state.filtered = state.concepts.filter((concept) => {
    const haystack = `${concept.title} ${concept.summary} ${concept.path} ${concept.tags.join(" ")}`.toLowerCase();
    return (
      (!search || haystack.includes(search)) &&
      (!niche || concept.niche === niche) &&
      (!type || concept.type === type) &&
      (!tag || concept.tags.includes(tag)) &&
      (!status || concept.status === status)
    );
  });

  renderConceptList();
}

function renderConceptList() {
  el.conceptCount.textContent = `${state.filtered.length} canonical pages`;
  el.emptyState.hidden = state.concepts.length > 0;
  el.conceptList.innerHTML = state.filtered.map(renderConceptCard).join("");

  el.conceptList.querySelectorAll("[data-left]").forEach((button) => {
    button.addEventListener("click", () => selectConcept("left", button.dataset.left));
  });
  el.conceptList.querySelectorAll("[data-right]").forEach((button) => {
    button.addEventListener("click", () => selectConcept("right", button.dataset.right));
  });
  el.conceptList.querySelectorAll("[data-open]").forEach((button) => {
    button.addEventListener("click", () => openWikiFile(button.dataset.open));
  });
}

function renderConceptCard(concept) {
  const selectedClass = [
    state.left?.wikilink === concept.wikilink ? "selected-left" : "",
    state.right?.wikilink === concept.wikilink ? "selected-right" : "",
  ].join(" ");
  return `
    <article class="concept-card ${selectedClass}">
      <span class="badge canonical">canonical</span>
      <h3>${escapeHtml(concept.title)}</h3>
      <div class="concept-path">${escapeHtml(concept.path)}</div>
      <p class="concept-summary">${escapeHtml(concept.summary)}</p>
      <div class="tag-row">
        <span class="tag">${escapeHtml(concept.type)}</span>
        <span class="tag">${escapeHtml(concept.status)}</span>
        ${concept.tags.map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}
      </div>
      <div class="card-actions">
        <button data-left="${escapeHtml(concept.wikilink)}">Set left</button>
        <button data-right="${escapeHtml(concept.wikilink)}">Set right</button>
        <button data-open="${escapeHtml(concept.path)}">Open canonical</button>
      </div>
    </article>
  `;
}

function selectConcept(side, wikilink) {
  const concept = state.concepts.find((item) => item.wikilink === wikilink);
  state[side] = concept;
  state.result = null;
  state.savedDraftPath = null;
  renderSelections();
  renderConceptList();
  renderResult();
}

function renderSelections() {
  renderSelection(el.leftSelection, state.left, "left canonical");
  renderSelection(el.rightSelection, state.right, "right canonical");
  el.generateButton.disabled = !(state.left && state.right);
  el.regenerateButton.disabled = !(state.left && state.right);
  renderPairingInsight();
}

function renderSelection(target, concept, label) {
  if (!concept) {
    target.classList.add("muted");
    target.innerHTML = `<span class="badge canonical">${label}</span><h3>No ${label.split(" ")[0]} concept selected</h3><p>Choose a page from the list.</p>`;
    return;
  }
  target.classList.remove("muted");
  target.innerHTML = `
    <span class="badge canonical">${label}</span>
    <h3>${escapeHtml(concept.title)}</h3>
    <div class="concept-path">${escapeHtml(concept.path)}</div>
    <p>${escapeHtml(concept.summary)}</p>
    <button data-open-selected="${escapeHtml(concept.path)}">Open canonical page</button>
  `;
  target.querySelector("[data-open-selected]").addEventListener("click", () => openWikiFile(concept.path));
}

function renderPairingInsight() {
  if (!(state.left && state.right)) {
    el.pairingInsight.innerHTML = `<span class="badge draft">speculative pairing</span><h3>Why this pairing is interesting</h3><p>Select two canonical concepts to see the overlap signal.</p>`;
    return;
  }
  const sharedTags = state.left.tags.filter((tag) => state.right.tags.includes(tag));
  const sharedLinks = state.left.outgoingWikilinks.filter((link) => state.right.outgoingWikilinks.includes(link));
  const signal = [
    sharedTags.length ? `Shared tags: ${sharedTags.join(", ")}.` : "No shared tags; this is a wider cross-domain jump.",
    sharedLinks.length ? `Shared outgoing links: ${sharedLinks.slice(0, 4).join(", ")}.` : "No shared outgoing links detected, so the synthesis should be treated as more speculative.",
  ].join(" ");
  el.pairingInsight.innerHTML = `<span class="badge draft">speculative pairing</span><h3>Why this pairing is interesting</h3><p>${escapeHtml(signal)}</p>`;
}

async function generateCombination() {
  if (!(state.left && state.right)) return;
  setStatus("Combining through the local repo workflow...");
  try {
    const payload = await api("/api/combine", {
      method: "POST",
      body: JSON.stringify({ left: state.left.wikilink, right: state.right.wikilink }),
    });
    state.result = payload.result;
    state.savedDraftPath = payload.path || payload.result?.draftPath || null;
    setStatus(`Draft generated at ${state.savedDraftPath}. Canonical parents were not edited.`);
    renderResult();
  } catch (error) {
    setStatus(error.message, true);
  }
}

function renderResult() {
  const hasResult = Boolean(state.result);
  el.resultView.hidden = !hasResult;
  el.copyButton.disabled = !hasResult;
  el.saveButton.disabled = !hasResult || Boolean(state.savedDraftPath);
  el.openDraftButton.disabled = !state.savedDraftPath;
  el.submitButton.disabled = !state.savedDraftPath;
  if (!hasResult) {
    el.resultView.innerHTML = "";
    return;
  }
  el.resultView.innerHTML = `
    <div class="result-header">
      <div>
        <span class="badge draft">draft preview</span>
        <h2>${escapeHtml(state.result.title)}</h2>
        <p class="provider-note">Synthesized by ${escapeHtml(state.result.provider || "configured provider")} and saved separately from canonical pages.</p>
        <p class="provider-note">Pair score: ${escapeHtml(state.result.pairScore?.overall_score ?? "n/a")} / threshold ${escapeHtml(state.result.pairScoreThreshold ?? "n/a")}</p>
        ${state.result.pairScoreWarning ? `<p class="provider-note error">${escapeHtml(state.result.pairScoreWarning)}</p>` : ""}
      </div>
      ${state.savedDraftPath ? `<span class="badge pending">saved: ${escapeHtml(state.savedDraftPath)}</span>` : ""}
    </div>
    ${sectionOrder.map((name) => `
      <article class="result-section">
        <h3>${escapeHtml(name)}</h3>
        <p>${escapeHtml(state.result.sections[name] || "")}</p>
      </article>
    `).join("")}
  `;
}

function markdownFromResult() {
  if (!state.result) return "";
  return sectionOrder.map((name) => `# ${name}\n\n${state.result.sections[name] || ""}`).join("\n\n");
}

async function copyMarkdown() {
  try {
    await navigator.clipboard.writeText(markdownFromResult());
    setStatus("Markdown copied.");
  } catch {
    setStatus("Could not access clipboard in this browser.", true);
  }
}

async function saveDraft() {
  if (!(state.left && state.right && state.result)) return;
  setStatus("Saving speculative draft...");
  try {
    const payload = await api("/api/drafts", {
      method: "POST",
      body: JSON.stringify({ left: state.left.wikilink, right: state.right.wikilink }),
    });
    state.savedDraftPath = payload.path;
    setStatus(`Saved draft at ${payload.path}. Canonical parents were not edited.`);
    renderResult();
  } catch (error) {
    setStatus(error.message, true);
  }
}

function openSavedDraft() {
  if (state.savedDraftPath) {
    openWikiFile(state.savedDraftPath);
  }
}

async function submitForPromotion() {
  if (!state.savedDraftPath) return;
  setStatus("Submitting saved draft to promotion queue...");
  try {
    const payload = await api("/api/promotions", {
      method: "POST",
      body: JSON.stringify({ draftPath: state.savedDraftPath, note: "Submitted from Combination Lab UI." }),
    });
    setStatus(`Promotion pending: ${payload.path}. No auto-promotion occurred.`);
  } catch (error) {
    setStatus(error.message, true);
  }
}

function openWikiFile(path) {
  window.open(`/file?path=${encodeURIComponent(path)}`, "_blank", "noopener,noreferrer");
}

async function init() {
  try {
    const payload = await api("/api/concepts");
    state.concepts = payload.concepts;
    state.filtered = payload.concepts;
    hydrateFilters();
    renderSelections();
    applyFilters();
    setStatus("Ready. Choose a left and right canonical page.");
  } catch (error) {
    setStatus(error.message, true);
    el.emptyState.hidden = false;
  }
}

[el.searchInput, el.nicheFilter, el.typeFilter, el.tagFilter, el.statusFilter].forEach((control) => {
  control.addEventListener("input", applyFilters);
});

el.generateButton.addEventListener("click", generateCombination);
el.regenerateButton.addEventListener("click", generateCombination);
el.copyButton.addEventListener("click", copyMarkdown);
el.saveButton.addEventListener("click", saveDraft);
el.openDraftButton.addEventListener("click", openSavedDraft);
el.submitButton.addEventListener("click", submitForPromotion);

init();
