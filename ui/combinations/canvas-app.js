/* ───────────────────────────────────────────────────────────
   Atom Canvas — Infinite-Craft-style combination UI
   Layered on top of the existing combination backend.
   ─────────────────────────────────────────────────────────── */

// Brighter, saturated colors that glow on the dark premium background
const NICHE_COLORS = {
  ai:            "#5b8fd4",
  defi:          "#4aad7a",
  biohacking:    "#38c4a8",
  "social-media":"#d46b9e",
  startups:      "#e07840",
  politics:      "#c45252",
  philosophies:  "#9870d4",
  markets:       "#c4b042",
  "cross-niche": "#8a9ab8",
};

const NICHE_ICONS = {
  ai:            "🤖",
  defi:          "🔗",
  biohacking:    "🧬",
  "social-media":"📱",
  startups:      "🚀",
  politics:      "🏛",
  philosophies:  "💡",
  markets:       "📊",
  "cross-niche": "🌐",
};

const SECTION_ORDER = [
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

function nicheColor(niche) {
  return NICHE_COLORS[niche] || "#6b6b6b";
}

function nicheIcon(niche) {
  return NICHE_ICONS[niche] || "📄";
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;",
  })[c]);
}

function clampPercent(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return 0;
  return Math.max(0, Math.min(100, numeric * 100));
}

function formatScore(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toFixed(2) : "n/a";
}

function prefersReducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

// Convert plain text with bullet lists and wikilinks into presentational HTML.
// Wikilinks: [[path|display]] or [[path]] → <span class="wikiref">
// Bullet lines: lines starting with "- " → <ul><li>
function renderSectionBody(text) {
  if (!text) return "";

  function parseLinks(str) {
    return str.replace(/\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]/g, (_, path, display) => {
      const label = escapeHtml(display || path.split("/").pop().replace(/-/g, " "));
      return `<span class="wikiref">${label}</span>`;
    });
  }

  const lines = text.split("\n").filter((l) => l.trim());
  const out = [];
  let listItems = [];

  function flushList() {
    if (!listItems.length) return;
    out.push(`<ul>${listItems.map((item) => `<li>${parseLinks(escapeHtml(item))}</li>`).join("")}</ul>`);
    listItems = [];
  }

  for (const line of lines) {
    if (/^\s*- /.test(line)) {
      listItems.push(line.replace(/^\s*-\s+/, ""));
    } else {
      flushList();
      out.push(`<p>${parseLinks(escapeHtml(line))}</p>`);
    }
  }
  flushList();
  return out.join("");
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

/* ─── State ─── */

const state = {
  concepts: [],
  filtered: [],
  canvasAtoms: [],
  selectedAtomId: null,
  nextAtomId: 1,
  dragging: null,     // { atomId, offsetX, offsetY } for canvas drag
  libDragging: null,  // { concept, ghostEl } for library→canvas drag
};

/* ─── DOM refs ─── */

const el = {
  atomCount:      document.getElementById("atomCount"),
  libSearch:      document.getElementById("libSearch"),
  libNiche:       document.getElementById("libNiche"),
  libType:        document.getElementById("libType"),
  libTag:         document.getElementById("libTag"),
  libStatus:      document.getElementById("libStatus"),
  atomList:       document.getElementById("atomList"),
  canvasViewport: document.getElementById("canvasViewport"),
  canvasSurface:  document.getElementById("canvasSurface"),
  canvasEmpty:    document.getElementById("canvasEmpty"),
  fusionOverlay:  document.getElementById("fusionOverlay"),
  fusionPairLabel: document.getElementById("fusionPairLabel"),
  combineToast:   document.getElementById("combineToast"),
  combineToastText: document.getElementById("combineToastText"),
  inspectorPanel: document.getElementById("inspectorPanel"),
  inspectorEmpty: document.getElementById("inspectorEmpty"),
  inspectorContent: document.getElementById("inspectorContent"),
};

/* ─── Library: load, filter, render ─── */

function optionList(values, label) {
  return [
    `<option value="">All ${escapeHtml(label)}</option>`,
    ...values.map((v) => `<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`),
  ].join("");
}

function hydrateFilters() {
  const niches   = [...new Set(state.concepts.map((c) => c.niche))].sort();
  const types    = [...new Set(state.concepts.map((c) => c.type))].sort();
  const tags     = [...new Set(state.concepts.flatMap((c) => c.tags))].sort();
  const statuses = [...new Set(state.concepts.map((c) => c.status))].sort();
  el.libNiche.innerHTML  = optionList(niches, "niches");
  el.libType.innerHTML   = optionList(types, "types");
  el.libTag.innerHTML    = optionList(tags, "tags");
  el.libStatus.innerHTML = optionList(statuses, "statuses");
}

function applyFilters() {
  const search = el.libSearch.value.trim().toLowerCase();
  const niche  = el.libNiche.value;
  const type   = el.libType.value;
  const tag    = el.libTag.value;
  const status = el.libStatus.value;

  state.filtered = state.concepts.filter((c) => {
    const hay = `${c.title} ${c.summary} ${c.path} ${c.tags.join(" ")}`.toLowerCase();
    return (
      (!search || hay.includes(search)) &&
      (!niche  || c.niche === niche) &&
      (!type   || c.type === type) &&
      (!tag    || c.tags.includes(tag)) &&
      (!status || c.status === status)
    );
  });

  renderLibrary();
}

function renderLibrary() {
  el.atomCount.textContent = `${state.filtered.length}`;
  el.atomList.innerHTML = state.filtered.map((c) => {
    const color = nicheColor(c.niche);
    return `
      <div class="lib-atom" data-wikilink="${escapeHtml(c.wikilink)}">
        <div class="lib-atom-dot" style="background:${color}"></div>
        <div class="lib-atom-info">
          <div class="lib-atom-title">${escapeHtml(c.title)}</div>
          <div class="lib-atom-niche">${escapeHtml(c.niche)}</div>
        </div>
      </div>`;
  }).join("");

  el.atomList.querySelectorAll(".lib-atom").forEach((chip) => {
    chip.addEventListener("pointerdown", onLibAtomPointerDown);
  });
}

/* ─── Library drag → canvas ─── */

function onLibAtomPointerDown(e) {
  if (e.button !== 0) return;
  const wikilink = e.currentTarget.dataset.wikilink;
  const concept = state.concepts.find((c) => c.wikilink === wikilink);
  if (!concept) return;

  e.preventDefault();
  const color = nicheColor(concept.niche);
  const ghost = document.createElement("div");
  ghost.className = "drag-ghost";
  ghost.innerHTML = `
    <div class="atom-circle canonical" style="color:${color}; background: radial-gradient(circle at 35% 35%, rgba(255,255,255,0.35), ${color}22);">
      <span class="atom-icon">${nicheIcon(concept.niche)}</span>
    </div>`;
  ghost.style.left = `${e.clientX - 35}px`;
  ghost.style.top  = `${e.clientY - 35}px`;
  document.body.appendChild(ghost);

  state.libDragging = { concept, ghostEl: ghost };
  el.canvasViewport.classList.add("drag-over");

  document.addEventListener("pointermove", onLibDragMove);
  document.addEventListener("pointerup", onLibDragEnd);
}

function onLibDragMove(e) {
  if (!state.libDragging) return;
  state.libDragging.ghostEl.style.left = `${e.clientX - 35}px`;
  state.libDragging.ghostEl.style.top  = `${e.clientY - 35}px`;
}

function onLibDragEnd(e) {
  document.removeEventListener("pointermove", onLibDragMove);
  document.removeEventListener("pointerup", onLibDragEnd);
  el.canvasViewport.classList.remove("drag-over");

  if (!state.libDragging) return;
  const { concept, ghostEl } = state.libDragging;
  ghostEl.remove();
  state.libDragging = null;

  const rect = el.canvasViewport.getBoundingClientRect();
  const dropX = e.clientX - rect.left;
  const dropY = e.clientY - rect.top;

  if (dropX < 0 || dropY < 0 || dropX > rect.width || dropY > rect.height) {
    return; // dropped outside canvas
  }

  addCanonicalAtom(concept, dropX - 45, dropY - 45);
}

/* ─── Canvas atom model ─── */

function addCanonicalAtom(concept, x, y) {
  const atom = {
    id: state.nextAtomId++,
    kind: "canonical",
    concept,
    title: concept.title,
    niche: concept.niche,
    wikilink: concept.wikilink,
    path: concept.path,
    summary: concept.summary,
    tags: concept.tags,
    type: concept.type,
    status: concept.status,
    x, y,
    result: null,
    parents: null,
    savedDraftPath: null,
  };
  state.canvasAtoms.push(atom);
  renderCanvasAtom(atom);
  updateCanvasEmpty();
  selectAtom(atom.id);
}

function addDraftAtom(result, parentA, parentB, x, y, savedDraftPath = null) {
  const atom = {
    id: state.nextAtomId++,
    kind: "draft",
    concept: null,
    title: result.title,
    niche: "cross-niche",
    wikilink: null,
    path: null,
    summary: result.summary,
    tags: result.tags,
    type: "synthesis",
    status: "draft",
    x, y,
    result,
    parents: [parentA, parentB],
    savedDraftPath,
  };
  state.canvasAtoms.push(atom);
  renderCanvasAtom(atom);
  if (!prefersReducedMotion()) {
    requestAnimationFrame(() => {
      const node = el.canvasSurface.querySelector(`[data-atom-id="${atom.id}"]`);
      if (node) node.classList.add("materialized");
    });
  }
  updateCanvasEmpty();
  selectAtom(atom.id);
  return atom;
}

function removeCanvasAtom(atomId) {
  const idx = state.canvasAtoms.findIndex((a) => a.id === atomId);
  if (idx === -1) return;
  state.canvasAtoms.splice(idx, 1);
  const domAtom = el.canvasSurface.querySelector(`[data-atom-id="${atomId}"]`);
  if (domAtom) domAtom.remove();
  if (state.selectedAtomId === atomId) {
    state.selectedAtomId = null;
    renderInspector();
  }
  updateCanvasEmpty();
}

function updateCanvasEmpty() {
  el.canvasEmpty.style.display = state.canvasAtoms.length === 0 ? "" : "none";
}

/* ─── Canvas atom rendering ─── */

function renderCanvasAtom(atom) {
  const color = nicheColor(atom.niche);
  const icon  = nicheIcon(atom.niche);
  const kindClass = atom.kind;

  const div = document.createElement("div");
  div.className = `canvas-atom`;
  div.dataset.atomId = atom.id;
  div.style.left = `${atom.x}px`;
  div.style.top  = `${atom.y}px`;

  const bgTint = atom.kind === "draft"
    ? `${color}15`
    : `${color}22`;

  div.innerHTML = `
    <div class="atom-circle ${kindClass}" style="color:${color}; background: radial-gradient(circle at 35% 35%, rgba(255,255,255,0.35), ${bgTint});">
      <span class="atom-icon">${icon}</span>
      <span class="atom-kind-badge ${kindClass}">${kindClass}</span>
    </div>
    <div class="atom-label">${escapeHtml(atom.title)}</div>`;

  div.addEventListener("pointerdown", onCanvasAtomPointerDown);
  div.addEventListener("click", (e) => {
    e.stopPropagation();
    selectAtom(atom.id);
  });
  div.addEventListener("dblclick", (e) => {
    e.stopPropagation();
    openAtomPage(atom);
  });

  el.canvasSurface.appendChild(div);
}

function reRenderAllCanvasAtoms() {
  el.canvasSurface.querySelectorAll(".canvas-atom").forEach((node) => node.remove());
  state.canvasAtoms.forEach(renderCanvasAtom);
  updateCanvasEmpty();
}

/* ─── Canvas drag (move atoms around) ─── */

function onCanvasAtomPointerDown(e) {
  if (e.button !== 0) return;
  const atomEl = e.currentTarget;
  const atomId = parseInt(atomEl.dataset.atomId);
  const atom = state.canvasAtoms.find((a) => a.id === atomId);
  if (!atom) return;

  e.preventDefault();
  e.stopPropagation();

  const rect = el.canvasViewport.getBoundingClientRect();
  state.dragging = {
    atomId,
    offsetX: e.clientX - rect.left - atom.x,
    offsetY: e.clientY - rect.top  - atom.y,
  };

  atomEl.classList.add("dragging");

  document.addEventListener("pointermove", onCanvasDragMove);
  document.addEventListener("pointerup",   onCanvasDragEnd);
}

function onCanvasDragMove(e) {
  if (!state.dragging) return;

  const rect = el.canvasViewport.getBoundingClientRect();
  const atom = state.canvasAtoms.find((a) => a.id === state.dragging.atomId);
  if (!atom) return;

  atom.x = e.clientX - rect.left - state.dragging.offsetX;
  atom.y = e.clientY - rect.top  - state.dragging.offsetY;

  const domAtom = el.canvasSurface.querySelector(`[data-atom-id="${atom.id}"]`);
  if (domAtom) {
    domAtom.style.left = `${atom.x}px`;
    domAtom.style.top  = `${atom.y}px`;
  }

  // Overlap detection for combine affordance
  updateCombineTargets(atom);
}

function onCanvasDragEnd(e) {
  document.removeEventListener("pointermove", onCanvasDragMove);
  document.removeEventListener("pointerup",   onCanvasDragEnd);

  if (!state.dragging) return;

  const draggedAtom = state.canvasAtoms.find((a) => a.id === state.dragging.atomId);
  const domAtom = el.canvasSurface.querySelector(`[data-atom-id="${state.dragging.atomId}"]`);
  if (domAtom) domAtom.classList.remove("dragging");

  const target = findCombineTarget(draggedAtom);
  clearCombineTargets();
  state.dragging = null;

  if (target && draggedAtom) {
    attemptCombine(draggedAtom, target);
  }
}

/* ─── Combine: overlap detection ─── */

function atomCenter(atom) {
  return { cx: atom.x + 45, cy: atom.y + 45 };
}

function atomDistance(a, b) {
  const ca = atomCenter(a);
  const cb = atomCenter(b);
  return Math.sqrt((ca.cx - cb.cx) ** 2 + (ca.cy - cb.cy) ** 2);
}

function findCombineTarget(draggedAtom) {
  if (!draggedAtom) return null;
  let closest = null;
  let closestDist = Infinity;

  for (const other of state.canvasAtoms) {
    if (other.id === draggedAtom.id) continue;
    const dist = atomDistance(draggedAtom, other);
    if (dist < 80 && dist < closestDist) {
      closest = other;
      closestDist = dist;
    }
  }
  return closest;
}

function updateCombineTargets(draggedAtom) {
  el.canvasSurface.querySelectorAll(".canvas-atom.combine-target").forEach((node) =>
    node.classList.remove("combine-target")
  );

  const target = findCombineTarget(draggedAtom);
  if (target) {
    const targetEl = el.canvasSurface.querySelector(`[data-atom-id="${target.id}"]`);
    if (targetEl) targetEl.classList.add("combine-target");
  }
}

function clearCombineTargets() {
  el.canvasSurface.querySelectorAll(".canvas-atom.combine-target").forEach((node) =>
    node.classList.remove("combine-target")
  );
}

function showFusionOverlay(atomA, atomB) {
  if (!el.fusionOverlay) return;
  el.fusionPairLabel.textContent = `${atomA.title} x ${atomB.title}`;
  el.fusionOverlay.hidden = false;
  el.fusionOverlay.classList.remove("complete");
  el.canvasViewport.classList.add("is-combining");
}

function completeFusionOverlay() {
  if (!el.fusionOverlay) return;
  el.fusionOverlay.classList.add("complete");
  window.setTimeout(() => {
    el.fusionOverlay.hidden = true;
    el.fusionOverlay.classList.remove("complete");
    el.canvasViewport.classList.remove("is-combining");
  }, 650);
}

function hideFusionOverlay() {
  if (!el.fusionOverlay) return;
  el.fusionOverlay.hidden = true;
  el.fusionOverlay.classList.remove("complete");
  el.canvasViewport.classList.remove("is-combining");
}

function runProgressSequence(atomA, atomB) {
  const steps = [
    "Reading canonical lineage...",
    "Scoring synthesis tension...",
    "Calling Cursor Agent...",
    "Running semantic quality gate...",
    "Rendering draft artifact...",
  ];
  showFusionOverlay(atomA, atomB);

  // Skip the cycling animation for users who prefer reduced motion
  if (prefersReducedMotion()) {
    showToast(steps[steps.length - 1]);
    return null;
  }

  let index = 0;
  showToast(steps[index]);
  return window.setInterval(() => {
    index = Math.min(index + 1, steps.length - 1);
    showToast(steps[index]);
  }, 1200);
}

/* ─── Combine: execution ─── */

async function attemptCombine(atomA, atomB) {
  // v1: only canonical + canonical
  if (atomA.kind !== "canonical" || atomB.kind !== "canonical") {
    showToast("Only canonical + canonical combinations are supported in v1.", "error");
    return;
  }

  if (atomA.wikilink === atomB.wikilink) {
    showToast("Cannot combine a page with itself.", "error");
    return;
  }

  const progressTimer = runProgressSequence(atomA, atomB);

  try {
    const payload = await api("/api/combine", {
      method: "POST",
      body: JSON.stringify({ left: atomA.wikilink, right: atomB.wikilink }),
    });
    if (progressTimer) window.clearInterval(progressTimer);
    completeFusionOverlay();

    const midX = (atomA.x + atomB.x) / 2;
    const midY = (atomA.y + atomB.y) / 2;
    removeCanvasAtom(atomA.id);
    removeCanvasAtom(atomB.id);
    const savedPath = payload.path || payload.result?.draftPath || null;
    const draftAtom = addDraftAtom(payload.result, atomA, atomB, midX, midY, savedPath);

    showToast(savedPath ? `Created draft: ${savedPath}` : `Created: ${draftAtom.title}`, "success");
  } catch (err) {
    if (progressTimer) window.clearInterval(progressTimer);
    hideFusionOverlay();
    showToast(err.message, "error");
  }
}

/* ─── Toast ─── */

let toastTimer = null;

function showToast(message, variant) {
  el.combineToast.hidden = false;
  el.combineToast.className = "combine-toast" + (variant ? ` ${variant}` : "");
  el.combineToastText.textContent = message;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.combineToast.hidden = true; }, 4000);
}

/* ─── Selection ─── */

function selectAtom(atomId) {
  state.selectedAtomId = atomId;

  el.canvasSurface.querySelectorAll(".canvas-atom.selected").forEach((node) =>
    node.classList.remove("selected")
  );

  if (atomId != null) {
    const domAtom = el.canvasSurface.querySelector(`[data-atom-id="${atomId}"]`);
    if (domAtom) domAtom.classList.add("selected");
  }

  renderInspector();
}

function openAtomPage(atom) {
  if (atom.kind === "canonical" && atom.path) {
    window.open(`/file?path=${encodeURIComponent(atom.path)}`, "_blank", "noopener,noreferrer");
  } else if (atom.kind === "draft" && atom.savedDraftPath) {
    window.open(`/file?path=${encodeURIComponent(atom.savedDraftPath)}`, "_blank", "noopener,noreferrer");
  }
}

/* ─── Inspector ─── */

function renderInspector() {
  const atom = state.canvasAtoms.find((a) => a.id === state.selectedAtomId);
  const hasSelection = Boolean(atom);
  el.inspectorPanel.classList.toggle("open", hasSelection);
  el.inspectorPanel.classList.toggle("has-selection", hasSelection);
  el.inspectorPanel.setAttribute("aria-busy", "false");

  if (!atom) {
    el.inspectorEmpty.hidden = false;
    el.inspectorEmpty.setAttribute("aria-hidden", "false");
    el.inspectorContent.hidden = true;
    el.inspectorContent.setAttribute("aria-hidden", "true");
    return;
  }

  el.inspectorEmpty.hidden = true;
  el.inspectorEmpty.setAttribute("aria-hidden", "true");
  el.inspectorContent.hidden = false;
  el.inspectorContent.setAttribute("aria-hidden", "false");

  if (atom.kind === "canonical") {
    renderCanonicalInspector(atom);
  } else {
    renderDraftInspector(atom);
  }
}

function renderCanonicalInspector(atom) {
  el.inspectorContent.innerHTML = `
    <span class="inspector-kind canonical">canonical</span>
    <div class="inspector-title">${escapeHtml(atom.title)}</div>
    <div class="inspector-summary">${escapeHtml(atom.summary)}</div>
    <div class="inspector-meta">
      <div class="inspector-meta-row">
        <span class="inspector-meta-label">Path</span>
        <span class="inspector-meta-value inspector-meta-path">${escapeHtml(atom.path)}</span>
      </div>
      <div class="inspector-meta-row">
        <span class="inspector-meta-label">Type</span>
        <span class="inspector-meta-value">${escapeHtml(atom.type)}</span>
      </div>
      <div class="inspector-meta-row">
        <span class="inspector-meta-label">Status</span>
        <span class="inspector-meta-value">${escapeHtml(atom.status)}</span>
      </div>
      <div class="inspector-meta-row">
        <span class="inspector-meta-label">Niche</span>
        <span class="inspector-meta-value">${escapeHtml(atom.niche)}</span>
      </div>
    </div>
    <div class="inspector-tags">
      ${atom.tags.map((t) => `<span class="inspector-tag">${escapeHtml(t)}</span>`).join("")}
    </div>
    <div class="inspector-actions">
      <button onclick="openAtomPage(state.canvasAtoms.find(a=>a.id===${atom.id}))">Open canonical page</button>
      <button onclick="removeCanvasAtom(${atom.id})">Remove from canvas</button>
    </div>`;
}

function renderDraftInspector(atom) {
  const result = atom.result;

  const parentHtml = atom.parents
    ? atom.parents.map((p) => `
        <div class="inspector-parent-link" onclick="selectAtom(${p.id})">
          <div class="inspector-parent-dot" style="background:${nicheColor(p.niche)}"></div>
          ${escapeHtml(p.title)}
        </div>`).join("")
    : "<em>Unknown parents</em>";

  const sectionsHtml = result
    ? SECTION_ORDER.map((name) => {
        const body = result.sections[name];
        if (!body) return "";
        return `
          <div class="inspector-section">
            <h4>${escapeHtml(name)}</h4>
            <div class="inspector-section-body">${renderSectionBody(body)}</div>
          </div>`;
      }).join("")
    : "";

  const savedIndicator = atom.savedDraftPath
    ? `<div class="inspector-status success">Draft artifact saved: ${escapeHtml(atom.savedDraftPath)}</div>`
    : "";
  const scoreIndicator = result?.pairScore
    ? `
      <div class="score-card">
        <div class="score-card-head">
          <span>Pair Score</span>
          <strong>${escapeHtml(formatScore(result.pairScore.overall_score))}</strong>
        </div>
        <div class="score-track">
          <div class="score-fill" style="width:${clampPercent(result.pairScore.overall_score)}%"></div>
        </div>
        <div class="score-meta">Threshold ${escapeHtml(formatScore(result.pairScoreThreshold))}</div>
      </div>`
    : "";
  const scoreWarning = result?.pairScoreWarning
    ? `<div class="inspector-status error">${escapeHtml(result.pairScoreWarning)}</div>`
    : "";
  const gate = result?.semanticGate
    ? `<span class="inspector-kind ${escapeHtml(result.semanticGate.status)}">gate: ${escapeHtml(result.semanticGate.status)}</span>`
    : "";

  el.inspectorContent.innerHTML = `
    <div class="inspector-badge-row">
      <span class="inspector-kind draft">draft</span>
      ${gate}
    </div>
    <div class="inspector-title">${escapeHtml(atom.title)}</div>
    <div class="inspector-summary">${escapeHtml(atom.summary)}</div>
    <div class="inspector-tags">
      ${atom.tags.map((t) => `<span class="inspector-tag">${escapeHtml(t)}</span>`).join("")}
    </div>
    <div class="inspector-section">
      <h4>Parents</h4>
      <div class="inspector-parents">${parentHtml}</div>
    </div>
    ${scoreIndicator}
    ${scoreWarning}
    ${sectionsHtml}
    ${savedIndicator}
    <div class="inspector-actions" id="draftActions"></div>`;

  renderDraftActions(atom);
}

function renderDraftActions(atom) {
  const container = document.getElementById("draftActions");
  if (!container) return;

  container.innerHTML = "";

  if (!atom.savedDraftPath) {
    const saveBtn = document.createElement("button");
    saveBtn.className = "primary";
    saveBtn.textContent = "Save as draft";
    saveBtn.addEventListener("click", () => saveDraftAtom(atom));
    container.appendChild(saveBtn);
  }

  if (atom.result) {
    const copyBtn = document.createElement("button");
    copyBtn.textContent = "Copy markdown";
    copyBtn.addEventListener("click", () => copyDraftMarkdown(atom));
    container.appendChild(copyBtn);
  }

  if (atom.savedDraftPath) {
    const openBtn = document.createElement("button");
    openBtn.textContent = "Open draft file";
    openBtn.addEventListener("click", () => openAtomPage(atom));
    container.appendChild(openBtn);

    const submitBtn = document.createElement("button");
    submitBtn.textContent = "Submit for promotion";
    submitBtn.addEventListener("click", () => submitDraftPromotion(atom));
    container.appendChild(submitBtn);
  }

  const removeBtn = document.createElement("button");
  removeBtn.textContent = "Remove from canvas";
  removeBtn.addEventListener("click", () => removeCanvasAtom(atom.id));
  container.appendChild(removeBtn);
}

/* ─── Draft actions ─── */

async function saveDraftAtom(atom) {
  if (!atom.parents || atom.parents.length < 2) return;

  const parentA = atom.parents[0];
  const parentB = atom.parents[1];

  try {
    const payload = await api("/api/drafts", {
      method: "POST",
      body: JSON.stringify({ left: parentA.wikilink, right: parentB.wikilink }),
    });
    atom.savedDraftPath = payload.path;
    showToast(`Saved draft: ${payload.path}`, "success");
    renderInspector();
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function submitDraftPromotion(atom) {
  if (!atom.savedDraftPath) return;

  try {
    const payload = await api("/api/promotions", {
      method: "POST",
      body: JSON.stringify({ draftPath: atom.savedDraftPath, note: "Submitted from Atom Canvas." }),
    });
    showToast(`Promotion pending: ${payload.path}`, "success");
  } catch (err) {
    showToast(err.message, "error");
  }
}

function copyDraftMarkdown(atom) {
  if (!atom.result) return;
  const md = SECTION_ORDER.map(
    (name) => `# ${name}\n\n${atom.result.sections[name] || ""}`
  ).join("\n\n");
  navigator.clipboard.writeText(md).then(
    () => showToast("Markdown copied.", "success"),
    () => showToast("Clipboard access denied.", "error"),
  );
}

/* ─── Dark mode toggle ─── */

const darkToggle = document.getElementById("darkToggle");

function applyDark(dark) {
  document.body.classList.toggle("dark", dark);
  darkToggle.textContent = dark ? "🌙" : "☀️";
  const label = dark ? "Switch to lighter shade" : "Switch to darker shade";
  darkToggle.title = label;
  darkToggle.setAttribute("aria-label", label);
  try { localStorage.setItem("canvas-dark", dark ? "1" : "0"); } catch {}
}

darkToggle.addEventListener("click", () => {
  applyDark(!document.body.classList.contains("dark"));
});

// Restore saved preference; default to dark (premium operator console aesthetic)
(function initDark() {
  let saved;
  try { saved = localStorage.getItem("canvas-dark"); } catch {}
  applyDark(saved !== null ? saved === "1" : true);
})();

/* ─── Canvas click / keyboard deselect ─── */

el.canvasSurface.addEventListener("click", (e) => {
  if (e.target === el.canvasSurface || e.target === el.canvasEmpty) {
    selectAtom(null);
  }
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && state.selectedAtomId != null) {
    selectAtom(null);
  }
});

/* ─── Filter event wiring ─── */

[el.libSearch, el.libNiche, el.libType, el.libTag, el.libStatus].forEach((control) => {
  control.addEventListener("input", applyFilters);
});

/* ─── Init ─── */

async function init() {
  // Show skeleton placeholders while the concept list loads
  el.atomList.innerHTML = Array.from({ length: 8 }, () =>
    `<div class="lib-atom-skeleton" aria-hidden="true"></div>`
  ).join("");
  el.atomCount.textContent = "…";

  try {
    const payload = await api("/api/concepts");
    state.concepts = payload.concepts;
    state.filtered = payload.concepts;
    hydrateFilters();
    renderLibrary();
    renderInspector();
  } catch (err) {
    el.atomCount.textContent = "!";
    el.atomList.innerHTML = `
      <div class="inspector-status error" style="margin:4px 0">
        Failed to load concepts: ${escapeHtml(err.message)}
      </div>`;
    console.error("Failed to load concepts:", err);
  }
}

init();
