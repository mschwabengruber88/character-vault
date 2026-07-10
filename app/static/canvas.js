/* Canvas / Templates — a Fabric.js-based layer editor for marketing
 * overlays and manga-panel compositions. Loaded after app.js and
 * fabric.min.js: reuses app.js's globals (el, t, api, toast, state,
 * renderCharacterList, hide*View, setActiveNavGroup) instead of
 * duplicating them, same as every other feature module in this app.
 *
 * Backgrounds are fetched through /assets/proxy rather than the B2
 * presigned URL directly — drawing a cross-origin image onto <canvas>
 * taints it, and canvas.toDataURL() throws SecurityError without CORS
 * headers B2 doesn't send. Proxying same-origin sidesteps that.
 */

let fabricCanvas = null;
let canvasBackgrounds = []; // [{id, label, signedUrl}]

// fabric.Image.fromURL() loads via a plain <img> tag under the hood, which
// can't carry the X-Workspace-Id header /assets/proxy requires (401
// otherwise). Fetch the bytes ourselves (fetch() can set headers) and hand
// Fabric a blob: URL instead — that's also inherently same-origin, so no
// crossOrigin option or tainted-canvas risk either.
async function fetchAssetBlobUrl(signedUrl) {
  const resp = await fetch(`/assets/proxy?url=${encodeURIComponent(signedUrl)}`, {
    headers: { "X-Workspace-Id": workspaceId() },
  });
  if (!resp.ok) throw new Error(`Could not load the image (${resp.status}).`);
  const blob = await resp.blob();
  return URL.createObjectURL(blob);
}

async function loadCanvasBackgrounds() {
  const [assets, scenes, studio] = await Promise.all([
    api("/assets?kind=image").catch(() => []),
    api("/scenes").catch(() => []),
    api("/studio").catch(() => []),
  ]);
  canvasBackgrounds = [
    ...assets.filter((a) => a.signed_url).map((a) => ({
      id: `asset-${a.id}`,
      label: `${a.character_name || "?"} — ${(a.prompt || "").slice(0, 40)}`,
      signedUrl: a.signed_url,
    })),
    ...scenes.filter((s) => s.signed_url).map((s) => ({
      id: `scene-${s.id}`,
      label: `${t("canvasSceneLabel")}: ${(s.participant_names || []).join(" + ")}`,
      signedUrl: s.signed_url,
    })),
    ...studio.filter((s) => s.signed_url).map((s) => ({
      id: `studio-${s.id}`,
      label: `${t("canvasStudioLabel")} (${s.kind}) — ${(s.prompt || "").slice(0, 40)}`,
      signedUrl: s.signed_url,
    })),
  ];
}

function populateCanvasBackgroundSelect() {
  const select = el("canvas-background-select");
  select.innerHTML = "";
  const blank = document.createElement("option");
  blank.value = "";
  blank.textContent = t("canvasNoBackground");
  select.appendChild(blank);
  for (const bg of canvasBackgrounds) {
    const opt = document.createElement("option");
    opt.value = bg.id;
    opt.textContent = bg.label;
    select.appendChild(opt);
  }
}

function initFabricCanvas() {
  if (fabricCanvas) return fabricCanvas;
  fabricCanvas = new fabric.Canvas("canvas-editor", {
    width: 800,
    height: 800,
    backgroundColor: "#1a1730",
    preserveObjectStacking: true,
  });
  setupCanvasTextEditing(fabricCanvas);
  setupPanelSelection(fabricCanvas);
  return fabricCanvas;
}

async function setCanvasBackground(bgId) {
  const canvas = initFabricCanvas();
  const bg = canvasBackgrounds.find((b) => b.id === bgId);
  if (!bg) {
    canvas.setBackgroundImage(null, () => canvas.renderAll());
    canvas.setDimensions({ width: 800, height: 800 });
    return;
  }
  let blobUrl;
  try {
    blobUrl = await fetchAssetBlobUrl(bg.signedUrl);
  } catch (err) {
    toast(err.message, true);
    return;
  }
  fabric.Image.fromURL(blobUrl, (img) => {
    const maxDim = 900;
    const scale = Math.min(maxDim / img.width, maxDim / img.height, 1);
    canvas.setDimensions({ width: img.width * scale, height: img.height * scale });
    img.set({ scaleX: scale, scaleY: scale });
    canvas.setBackgroundImage(img, () => canvas.renderAll());
    URL.revokeObjectURL(blobUrl);
  });
}

/* ---------- Manga panel layouts ----------
 * "none" keeps the single full-canvas background above. The others swap
 * the canvas to a fixed multi-panel grid: each panel is a placeholder
 * rect until the user clicks it and picks a background for that slot
 * specifically (via the same #canvas-background-select, repurposed while
 * a panel is "active" instead of setting the whole-canvas background). */

const CANVAS_LAYOUTS = {
  "2x2": { width: 900, height: 900, panels: [
    { left: 0, top: 0, width: 440, height: 440 },
    { left: 460, top: 0, width: 440, height: 440 },
    { left: 0, top: 460, width: 440, height: 440 },
    { left: 460, top: 460, width: 440, height: 440 },
  ] },
  row3: { width: 1200, height: 400, panels: [
    { left: 0, top: 0, width: 380, height: 400 },
    { left: 410, top: 0, width: 380, height: 400 },
    { left: 820, top: 0, width: 380, height: 400 },
  ] },
  strip4: { width: 400, height: 1600, panels: [
    { left: 0, top: 0, width: 400, height: 380 },
    { left: 0, top: 410, width: 400, height: 380 },
    { left: 0, top: 820, width: 400, height: 380 },
    { left: 0, top: 1230, width: 400, height: 380 },
  ] },
};

let panelSlots = [];   // fabric objects (placeholder Rect or filled Image) per panel index
let activePanelIndex = null;

function clearPanelSlots() {
  const canvas = initFabricCanvas();
  panelSlots.forEach((obj) => { if (obj) canvas.remove(obj); });
  panelSlots = [];
  activePanelIndex = null;
  el("canvas-panel-hint").hidden = true;
}

function setActivePanel(index) {
  activePanelIndex = index;
  const hint = el("canvas-panel-hint");
  hint.textContent = t("canvasPanelHintFilling").replace("{n}", index + 1);
  hint.hidden = false;
}

function applyCanvasLayout(layoutKey) {
  const canvas = initFabricCanvas();
  clearPanelSlots();
  canvas.setBackgroundImage(null, () => {});
  const layout = CANVAS_LAYOUTS[layoutKey];
  if (!layout) {
    canvas.setDimensions({ width: 800, height: 800 });
    canvas.renderAll();
    return;
  }
  canvas.setDimensions({ width: layout.width, height: layout.height });
  layout.panels.forEach((rect, index) => {
    const placeholder = new fabric.Rect({
      ...rect,
      fill: "rgba(157,91,255,0.08)",
      stroke: "#9D5BFF",
      strokeDashArray: [8, 6],
      strokeWidth: 2,
      hasControls: false,
      hasBorders: false,
    });
    placeholder.panelIndex = index;
    canvas.add(placeholder);
    panelSlots[index] = placeholder;
  });
  canvas.renderAll();
  setActivePanel(0);
}

async function fillActivePanel(bgId) {
  if (activePanelIndex === null) return;
  const canvas = initFabricCanvas();
  const layout = CANVAS_LAYOUTS[el("canvas-layout-select").value];
  const rect = layout && layout.panels[activePanelIndex];
  const bg = canvasBackgrounds.find((b) => b.id === bgId);
  if (!rect || !bg) return;
  let blobUrl;
  try {
    blobUrl = await fetchAssetBlobUrl(bg.signedUrl);
  } catch (err) {
    toast(err.message, true);
    return;
  }
  fabric.Image.fromURL(blobUrl, (img) => {
    const scale = Math.min(rect.width / img.width, rect.height / img.height);
    img.set({
      left: rect.left + (rect.width - img.width * scale) / 2,
      top: rect.top + (rect.height - img.height * scale) / 2,
      scaleX: scale,
      scaleY: scale,
      hasControls: false,
    });
    img.panelIndex = activePanelIndex;
    const old = panelSlots[activePanelIndex];
    if (old) canvas.remove(old);
    canvas.add(img);
    canvas.moveTo(img, 0);
    panelSlots[activePanelIndex] = img;
    canvas.renderAll();
    URL.revokeObjectURL(blobUrl);
  });
}

function setupPanelSelection(canvas) {
  canvas.on("mouse:down", (opt) => {
    if (opt.target && typeof opt.target.panelIndex === "number") {
      setActivePanel(opt.target.panelIndex);
    }
  });
}

function addCanvasText() {
  const canvas = initFabricCanvas();
  const textbox = new fabric.Textbox("Text", {
    left: 60,
    top: 60,
    fontSize: 32,
    fill: "#ffffff",
    fontFamily: "sans-serif",
    fontWeight: "bold",
    stroke: "#000000",
    strokeWidth: 1,
    paintFirst: "stroke",
  });
  canvas.add(textbox);
  canvas.setActiveObject(textbox);
}

function buildArrowShape() {
  const line = new fabric.Line([0, 20, 160, 20], { stroke: "#9D5BFF", strokeWidth: 4 });
  const head = new fabric.Triangle({
    left: 160, top: 20, width: 20, height: 24, fill: "#9D5BFF",
    angle: 90, originX: "center", originY: "center",
  });
  return new fabric.Group([line, head], { left: 100, top: 100 });
}

function addCanvasShape(kind) {
  const canvas = initFabricCanvas();
  const common = { left: 100, top: 100, fill: "rgba(157,91,255,0.35)", stroke: "#9D5BFF", strokeWidth: 2 };
  let shape = null;
  if (kind === "rect") shape = new fabric.Rect({ ...common, width: 160, height: 100 });
  else if (kind === "circle") shape = new fabric.Circle({ ...common, radius: 60 });
  else if (kind === "line") shape = new fabric.Line([50, 50, 250, 50], { stroke: "#9D5BFF", strokeWidth: 4 });
  else if (kind === "arrow") shape = buildArrowShape();
  if (!shape) return;
  canvas.add(shape);
  canvas.setActiveObject(shape);
}

/* ---------- Speech bubbles & soundwords ----------
 * Neither is a licensed asset — a bubble is an ellipse + tail path +
 * editable text; a soundword is bold text over a starburst path we draw
 * ourselves (same alternating-radius-points technique as the visible-AI-
 * badge sparkle in app/disclosure.py). Both are Fabric Groups; since Fabric
 * doesn't support double-click-to-edit text nested inside a group, editing
 * goes through a plain prompt() (see setupCanvasTextEditing below). */

function buildSpeechBubble() {
  const bubble = new fabric.Ellipse({
    rx: 120, ry: 70, left: 0, top: 0,
    fill: "#ffffff", stroke: "#0B0A16", strokeWidth: 3, originX: "center", originY: "center",
  });
  const tail = new fabric.Triangle({
    width: 30, height: 40, left: -60, top: 55, angle: -25,
    fill: "#ffffff", stroke: "#0B0A16", strokeWidth: 3, originX: "center", originY: "center",
  });
  const text = new fabric.Textbox("...", {
    left: 0, top: 0, width: 180, fontSize: 20, fill: "#0B0A16",
    fontFamily: "sans-serif", textAlign: "center", originX: "center", originY: "center",
  });
  return new fabric.Group([bubble, tail, text], { left: 150, top: 150 });
}

function addSpeechBubble() {
  const canvas = initFabricCanvas();
  const bubble = buildSpeechBubble();
  canvas.add(bubble);
  canvas.setActiveObject(bubble);
}

const SOUNDWORDS = ["POW!", "BAM!", "ZAP!", "WHOOSH!", "CRASH!", "BOOM!", "SLAM!", "BANG!"];

function starPoints(cx, cy, spikes, outerR, innerR) {
  const points = [];
  const step = Math.PI / spikes;
  let angle = -Math.PI / 2;
  for (let i = 0; i < spikes * 2; i++) {
    const r = i % 2 === 0 ? outerR : innerR;
    points.push({ x: cx + Math.cos(angle) * r, y: cy + Math.sin(angle) * r });
    angle += step;
  }
  return points;
}

function buildSoundword(word) {
  const burst = new fabric.Polygon(starPoints(0, 0, 10, 90, 55), {
    fill: "#FFB84D", stroke: "#0B0A16", strokeWidth: 3, originX: "center", originY: "center",
  });
  const text = new fabric.Text(word, {
    fontSize: 28, fontWeight: "900", fill: "#0B0A16", fontFamily: "Impact, Haettenschweiler, sans-serif",
    originX: "center", originY: "center", angle: -8,
  });
  return new fabric.Group([burst, text], { left: 220, top: 220 });
}

function populateSoundwordSelect() {
  const select = el("canvas-soundword-select");
  select.innerHTML = "";
  for (const word of SOUNDWORDS) {
    const opt = document.createElement("option");
    opt.value = word;
    opt.textContent = word;
    select.appendChild(opt);
  }
}

function addSoundword() {
  const canvas = initFabricCanvas();
  const word = el("canvas-soundword-select").value || SOUNDWORDS[0];
  const sw = buildSoundword(word);
  canvas.add(sw);
  canvas.setActiveObject(sw);
}

function findGroupTextChild(obj) {
  if (!obj || obj.type !== "group" || typeof obj._objects === "undefined") return null;
  return obj._objects.find((o) => o.type === "textbox" || o.type === "text") || null;
}

function setupCanvasTextEditing(canvas) {
  canvas.on("mouse:dblclick", (opt) => {
    const textChild = findGroupTextChild(opt.target);
    if (!textChild) return;
    const next = window.prompt(t("canvasEditTextPrompt"), textChild.text);
    if (next === null || next === textChild.text) return;
    textChild.set("text", next);
    canvas.requestRenderAll();
  });
}

/* ---------- Stickers ----------
 * A curated subset of Twemoji's SVGs (CC-BY 4.0, vendored under
 * app/static/vendor/stickers/ — see manifest.json + TWEMOJI_LICENSE.txt
 * there). These are same-origin static files, unlike vault backgrounds, so
 * they load straight through fabric.Image.fromURL() with no proxy/blob
 * detour needed. */

const STICKERS_BASE = "/static/vendor/stickers";
let stickerManifest = null;

async function loadStickerManifest() {
  if (stickerManifest) return stickerManifest;
  stickerManifest = await fetch(`${STICKERS_BASE}/manifest.json`).then((r) => r.json());
  return stickerManifest;
}

function addSticker(stickerId) {
  const canvas = initFabricCanvas();
  // fabric.Image.fromURL() rasterizes via the browser's intrinsic-size
  // handling for <img>, which doesn't reliably report a size for SVGs that
  // only declare a viewBox (no width/height) — it loads with no error but
  // draws nothing. Fabric's dedicated SVG loader parses the markup into
  // real vector path objects instead, which is both correct and crisper.
  fabric.loadSVGFromURL(`${STICKERS_BASE}/${stickerId}.svg`, (objects, options) => {
    const sticker = fabric.util.groupSVGElements(objects, options);
    sticker.set({ left: 120, top: 120, scaleX: 1.2, scaleY: 1.2 });
    canvas.add(sticker);
    canvas.setActiveObject(sticker);
  });
}

async function renderStickerPicker() {
  const grid = el("canvas-sticker-grid");
  const manifest = await loadStickerManifest().catch(() => null);
  if (!manifest) return;
  grid.innerHTML = "";
  for (const items of Object.values(manifest)) {
    for (const sticker of items) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "canvas-sticker-btn";
      btn.title = sticker.label;
      btn.innerHTML = `<img src="${STICKERS_BASE}/${sticker.id}.svg" alt="${sticker.label}">`;
      btn.addEventListener("click", () => addSticker(sticker.id));
      grid.appendChild(btn);
    }
  }
}

function duplicateCanvasSelection() {
  const canvas = initFabricCanvas();
  const obj = canvas.getActiveObject();
  if (!obj) return;
  obj.clone((clone) => {
    clone.set({ left: obj.left + 20, top: obj.top + 20 });
    canvas.add(clone);
    canvas.setActiveObject(clone);
  });
}

function deleteCanvasSelection() {
  const canvas = initFabricCanvas();
  const obj = canvas.getActiveObject();
  if (!obj) return;
  canvas.remove(obj);
}

let canvasExporting = false;

async function exportCanvasComposition() {
  if (canvasExporting) return;
  const canvas = initFabricCanvas();
  canvas.discardActiveObject();
  canvas.renderAll();

  let dataUrl;
  try {
    dataUrl = canvas.toDataURL({ format: "png" });
  } catch (err) {
    toast("Export failed — the canvas couldn't be read (a background image loaded without the proxy).", true);
    return;
  }

  canvasExporting = true;
  const status = el("canvas-status");
  el("canvas-export-button").disabled = true;
  status.classList.remove("error");
  status.innerHTML = `<span class="spinner" aria-hidden="true"></span>${t("canvasExporting")}`;
  status.hidden = false;
  try {
    await api("/canvas/export", {
      method: "POST",
      body: JSON.stringify({
        image_base64: dataUrl,
        visible_badge: el("canvas-visible-badge").checked,
      }),
    });
    status.hidden = true;
    toast(t("toastCanvasExported"));
  } catch (err) {
    status.classList.add("error");
    status.textContent = err.message;
  } finally {
    canvasExporting = false;
    el("canvas-export-button").disabled = false;
  }
}

function showCanvasView() {
  state.selectedId = null;
  renderCharacterList();
  hideScenesView();
  hideStudioView();
  hideAudioView();
  hideVideoView();
  hideScriptView();
  setActiveNavGroup(null);
  el("detail-placeholder").hidden = true;
  el("detail-content").hidden = true;
  el("canvas-view").hidden = false;
  el("open-canvas").classList.add("active");
  initFabricCanvas();
  loadCanvasBackgrounds().then(populateCanvasBackgroundSelect).catch(() => {});
}

function hideCanvasView() {
  el("canvas-view").hidden = true;
  el("open-canvas").classList.remove("active");
}

function setupCanvas() {
  el("open-canvas").addEventListener("click", showCanvasView);
  el("canvas-layout-select").addEventListener("change", (event) => applyCanvasLayout(event.target.value));
  el("canvas-background-select").addEventListener("change", (event) => {
    if (activePanelIndex !== null) fillActivePanel(event.target.value);
    else setCanvasBackground(event.target.value);
  });
  el("canvas-add-text").addEventListener("click", addCanvasText);
  el("canvas-add-rect").addEventListener("click", () => addCanvasShape("rect"));
  el("canvas-add-circle").addEventListener("click", () => addCanvasShape("circle"));
  el("canvas-add-line").addEventListener("click", () => addCanvasShape("line"));
  el("canvas-add-arrow").addEventListener("click", () => addCanvasShape("arrow"));
  el("canvas-add-bubble").addEventListener("click", addSpeechBubble);
  el("canvas-add-soundword").addEventListener("click", addSoundword);
  populateSoundwordSelect();
  renderStickerPicker();
  el("canvas-duplicate").addEventListener("click", duplicateCanvasSelection);
  el("canvas-delete").addEventListener("click", deleteCanvasSelection);
  el("canvas-export-button").addEventListener("click", exportCanvasComposition);
  document.addEventListener("keydown", (event) => {
    if (el("canvas-view").hidden) return;
    if ((event.key === "Delete" || event.key === "Backspace") && !["INPUT", "TEXTAREA"].includes(document.activeElement.tagName)) {
      const canvas = initFabricCanvas();
      if (canvas.getActiveObject() && !canvas.getActiveObject().isEditing) deleteCanvasSelection();
    }
  });
}

setupCanvas();
