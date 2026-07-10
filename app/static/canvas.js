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
let panelAssetIds = []; // vault asset id filling each panel, so templates can restore images after reload
let activePanelIndex = null;

function clearPanelSlots() {
  const canvas = initFabricCanvas();
  panelSlots.forEach((obj) => { if (obj) canvas.remove(obj); });
  panelSlots = [];
  panelAssetIds = [];
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

async function fillPanelAt(index, bgId, layoutKey) {
  const canvas = initFabricCanvas();
  const layout = CANVAS_LAYOUTS[layoutKey];
  const rect = layout && layout.panels[index];
  const bg = canvasBackgrounds.find((b) => b.id === bgId);
  if (!rect || !bg) return;
  let blobUrl;
  try {
    blobUrl = await fetchAssetBlobUrl(bg.signedUrl);
  } catch (err) {
    toast(err.message, true);
    return;
  }
  await new Promise((resolve) => {
    fabric.Image.fromURL(blobUrl, (img) => {
      const scale = Math.min(rect.width / img.width, rect.height / img.height);
      img.set({
        left: rect.left + (rect.width - img.width * scale) / 2,
        top: rect.top + (rect.height - img.height * scale) / 2,
        scaleX: scale,
        scaleY: scale,
        hasControls: false,
      });
      img.panelIndex = index;
      // Backed by a blob: URL that gets revoked below — never worth persisting
      // in canvas.toJSON(); templates instead restore panels via panelAssetIds.
      img.excludeFromExport = true;
      const old = panelSlots[index];
      if (old) canvas.remove(old);
      canvas.add(img);
      canvas.moveTo(img, 0);
      panelSlots[index] = img;
      panelAssetIds[index] = bgId;
      canvas.renderAll();
      URL.revokeObjectURL(blobUrl);
      resolve();
    });
  });
}

async function fillActivePanel(bgId) {
  if (activePanelIndex === null) return;
  await fillPanelAt(activePanelIndex, bgId, el("canvas-layout-select").value);
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

/* ---------- Video overlay mode (Phase D) ----------
 * The same editor, but the locked background is a finished video's first
 * frame (GET /videos/{id}/poster) at the clip's native resolution, and
 * "export" sends ONLY the drawn layers as a transparent PNG to
 * POST /videos/{id}/overlay, where ffmpeg burns them onto every frame. */

let canvasVideoMode = false;
let overlayVideoId = null;
let overlayApplying = false;

function setCanvasMode(videoMode) {
  canvasVideoMode = videoMode;
  el("canvas-layout-row").hidden = videoMode;
  el("canvas-background-row").hidden = videoMode;
  el("canvas-video-row").hidden = !videoMode;
  el("canvas-save-template").hidden = videoMode;
  el("canvas-export-button").hidden = videoMode;
  el("canvas-apply-overlay").hidden = !videoMode;
  document.querySelector(".canvas-badge-toggle").hidden = videoMode;
  if (videoMode) {
    el("canvas-current-template").hidden = true;
    el("canvas-save-template-changes").hidden = true;
  } else {
    updateTemplateSaveButtons();
  }
}

async function loadOverlayVideoSelect() {
  const select = el("canvas-video-select");
  select.innerHTML = "";
  const blank = document.createElement("option");
  blank.value = "";
  blank.textContent = t("canvasVideoPick");
  select.appendChild(blank);
  const videos = await api("/videos").catch(() => []);
  for (const v of videos) {
    if (v.status !== "done" || !v.url) continue;
    const opt = document.createElement("option");
    opt.value = v.id;
    opt.textContent = `#${v.id} — ${(v.character_name ? v.character_name + ": " : "")}${(v.prompt || "").slice(0, 50)}`;
    select.appendChild(opt);
  }
}

async function pickOverlayVideo(videoId) {
  overlayVideoId = null;
  const canvas = initFabricCanvas();
  if (!videoId) {
    canvas.setBackgroundImage(null, () => canvas.renderAll());
    return;
  }
  const status = el("canvas-status");
  status.classList.remove("error");
  status.innerHTML = `<span class="spinner" aria-hidden="true"></span>${t("canvasLoadingPoster")}`;
  status.hidden = false;
  try {
    const poster = await api(`/videos/${videoId}/poster`);
    const blobUrl = await fetchAssetBlobUrl(poster.signed_url);
    await new Promise((resolve) => {
      fabric.Image.fromURL(blobUrl, (img) => {
        // Native resolution, unscaled — the overlay PNG must line up with
        // the video pixel-for-pixel, unlike image mode's max-900px fit.
        canvas.setDimensions({ width: poster.width, height: poster.height });
        img.set({ scaleX: poster.width / img.width, scaleY: poster.height / img.height });
        canvas.setBackgroundImage(img, () => canvas.renderAll());
        URL.revokeObjectURL(blobUrl);
        resolve();
      });
    });
    overlayVideoId = Number(videoId);
    status.hidden = true;
  } catch (err) {
    status.classList.add("error");
    status.textContent = err.message;
  }
}

function exportOverlayDataUrl() {
  const canvas = initFabricCanvas();
  canvas.discardActiveObject();
  // Only the drawn layers: poster background and fill color stay out so the
  // PNG is transparent wherever nothing was drawn.
  const bg = canvas.backgroundImage;
  const bgColor = canvas.backgroundColor;
  canvas.backgroundImage = null;
  canvas.backgroundColor = "rgba(0,0,0,0)";
  let dataUrl;
  try {
    dataUrl = canvas.toDataURL({ format: "png" });
  } finally {
    canvas.backgroundImage = bg;
    canvas.backgroundColor = bgColor;
    canvas.renderAll();
  }
  return dataUrl;
}

async function applyVideoOverlay() {
  if (overlayApplying) return;
  if (!overlayVideoId) {
    toast(t("canvasOverlayNoVideo"), true);
    return;
  }
  overlayApplying = true;
  const status = el("canvas-status");
  const button = el("canvas-apply-overlay");
  button.disabled = true;
  status.classList.remove("error");
  status.innerHTML = `<span class="spinner" aria-hidden="true"></span>${t("canvasOverlayApplying")}`;
  status.hidden = false;
  try {
    await api(`/videos/${overlayVideoId}/overlay`, {
      method: "POST",
      body: JSON.stringify({ overlay_base64: exportOverlayDataUrl() }),
    });
    status.hidden = true;
    toast(t("toastOverlayDone"));
  } catch (err) {
    status.classList.add("error");
    status.textContent = err.message;
  } finally {
    overlayApplying = false;
    button.disabled = false;
  }
}

let currentTemplateId = null;
let currentTemplateName = null;

function updateTemplateSaveButtons() {
  const label = el("canvas-current-template");
  const saveChanges = el("canvas-save-template-changes");
  if (currentTemplateId) {
    label.textContent = t("canvasEditingTemplate").replace("{name}", currentTemplateName || "");
    label.hidden = false;
    saveChanges.hidden = false;
  } else {
    label.hidden = true;
    saveChanges.hidden = true;
  }
}

function resetCanvasEditor() {
  const canvas = initFabricCanvas();
  clearPanelSlots();
  canvas.clear();
  canvas.setBackgroundImage(null, () => {});
  canvas.setDimensions({ width: 800, height: 800 });
  canvas.backgroundColor = "#1a1730";
  el("canvas-layout-select").value = "none";
  el("canvas-video-select").value = "";
  overlayVideoId = null;
  currentTemplateId = null;
  currentTemplateName = null;
  updateTemplateSaveButtons();
  closeTemplateNameRow();
}

function showCanvasView({ keepState = false, videoMode = false } = {}) {
  state.selectedId = null;
  renderCharacterList();
  hideScenesView();
  hideStudioView();
  hideAudioView();
  hideVideoView();
  hideScriptView();
  hideCanvasTemplatesView();
  setActiveNavGroup("canvas");
  setActiveNavSubitem("canvas", videoMode ? "video" : "new");
  el("detail-placeholder").hidden = true;
  el("detail-content").hidden = true;
  el("canvas-view").hidden = false;
  initFabricCanvas();
  setCanvasMode(videoMode);
  if (!keepState) resetCanvasEditor();
  if (videoMode) {
    loadOverlayVideoSelect().catch(() => {});
  } else {
    loadCanvasBackgrounds().then(populateCanvasBackgroundSelect).catch(() => {});
  }
}

function hideCanvasView() {
  el("canvas-view").hidden = true;
}

/* ---------- Templates: save/load a reusable layout ---------- */

function serializeCanvasState() {
  const canvas = initFabricCanvas();
  return JSON.stringify({
    layoutKey: el("canvas-layout-select").value,
    width: canvas.width,
    height: canvas.height,
    panelAssetIds,
    fabric: canvas.toJSON(["panelIndex"]),
  });
}

async function loadCanvasState(stateJson) {
  const canvas = initFabricCanvas();
  const state = JSON.parse(stateJson);
  clearPanelSlots();
  canvas.setDimensions({ width: state.width, height: state.height });
  await new Promise((resolve) => {
    canvas.loadFromJSON(state.fabric, () => {
      el("canvas-layout-select").value = state.layoutKey || "none";
      canvas.getObjects().forEach((obj) => {
        if (typeof obj.panelIndex === "number") panelSlots[obj.panelIndex] = obj;
      });
      if (state.layoutKey && state.layoutKey !== "none") setActivePanel(0);
      canvas.renderAll();
      resolve();
    });
  });
  const assetIds = state.panelAssetIds || [];
  if (assetIds.some(Boolean)) {
    if (!canvasBackgrounds.length) {
      await loadCanvasBackgrounds().then(populateCanvasBackgroundSelect).catch(() => {});
    }
    for (let i = 0; i < assetIds.length; i++) {
      if (assetIds[i]) await fillPanelAt(i, assetIds[i], state.layoutKey);
    }
  }
}

function generateThumbnailDataUrl() {
  const canvas = initFabricCanvas();
  const multiplier = Math.min(1, 320 / Math.max(canvas.width, canvas.height));
  return canvas.toDataURL({ format: "png", multiplier });
}

function openTemplateNameRow() {
  const input = el("canvas-template-name-input");
  input.value = currentTemplateName || "";
  el("canvas-template-name-row").hidden = false;
  input.focus();
  input.select();
}

function closeTemplateNameRow() {
  el("canvas-template-name-row").hidden = true;
}

async function saveAsNewTemplate() {
  const name = el("canvas-template-name-input").value.trim();
  if (!name) {
    el("canvas-template-name-input").focus();
    return;
  }
  try {
    const template = await api("/canvas/templates", {
      method: "POST",
      body: JSON.stringify({
        name, category: null,
        layout_json: serializeCanvasState(),
        thumbnail_base64: generateThumbnailDataUrl(),
      }),
    });
    currentTemplateId = template.id;
    currentTemplateName = template.name;
    updateTemplateSaveButtons();
    closeTemplateNameRow();
    toast(t("toastTemplateSaved"));
  } catch (err) {
    toast(err.message, true);
  }
}

async function saveTemplateChanges() {
  if (!currentTemplateId) return openTemplateNameRow();
  try {
    const template = await api(`/canvas/templates/${currentTemplateId}`, {
      method: "PUT",
      body: JSON.stringify({
        name: currentTemplateName, category: null,
        layout_json: serializeCanvasState(),
        thumbnail_base64: generateThumbnailDataUrl(),
      }),
    });
    currentTemplateName = template.name;
    updateTemplateSaveButtons();
    toast(t("toastTemplateSaved"));
  } catch (err) {
    toast(err.message, true);
  }
}

async function openTemplateInEditor(templateId) {
  try {
    const template = await api(`/canvas/templates/${templateId}`);
    showCanvasView({ keepState: true });
    await loadCanvasState(template.layout_json);
    currentTemplateId = template.id;
    currentTemplateName = template.name;
    updateTemplateSaveButtons();
  } catch (err) {
    toast(err.message, true);
  }
}

function showCanvasTemplatesView() {
  state.selectedId = null;
  renderCharacterList();
  hideScenesView();
  hideStudioView();
  hideAudioView();
  hideVideoView();
  hideScriptView();
  hideCanvasView();
  setActiveNavGroup("canvas");
  setActiveNavSubitem("canvas", "templates");
  el("detail-placeholder").hidden = true;
  el("detail-content").hidden = true;
  el("canvas-templates-view").hidden = false;
  loadCanvasTemplates();
}

function hideCanvasTemplatesView() {
  el("canvas-templates-view").hidden = true;
}

async function loadCanvasTemplates() {
  try {
    renderCanvasTemplates(await api("/canvas/templates"));
  } catch (err) {
    toast(err.message, true);
  }
}

function renderCanvasTemplates(templates) {
  const grid = el("canvas-templates-grid");
  grid.innerHTML = "";
  el("canvas-templates-empty").hidden = templates.length > 0;
  for (const template of templates) {
    const card = document.createElement("div");
    card.className = "asset-card";
    if (template.signed_thumbnail_url) {
      const img = document.createElement("img");
      img.src = template.signed_thumbnail_url;
      img.alt = template.name;
      img.loading = "lazy";
      card.appendChild(img);
    }
    const body = document.createElement("div");
    body.className = "asset-body";
    const name = document.createElement("p");
    name.className = "asset-prompt";
    name.textContent = template.name;
    body.appendChild(name);
    const meta = document.createElement("div");
    meta.className = "asset-meta";
    const time = document.createElement("span");
    time.textContent = formatTimestamp(template.updated_at);
    meta.appendChild(time);
    const actions = document.createElement("span");
    actions.className = "asset-actions";
    const open = document.createElement("button");
    open.type = "button";
    open.className = "asset-details-btn";
    open.textContent = t("canvasTemplateOpen");
    open.addEventListener("click", () => openTemplateInEditor(template.id));
    actions.appendChild(open);
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "asset-delete";
    remove.textContent = t("canvasTemplateDelete");
    remove.addEventListener("click", async () => {
      if (!confirm(t("canvasConfirmDeleteTemplate"))) return;
      try {
        await api(`/canvas/templates/${template.id}`, { method: "DELETE" });
        loadCanvasTemplates();
        toast(t("toastTemplateDeleted"));
      } catch (err) {
        toast(err.message, true);
      }
    });
    actions.appendChild(remove);
    meta.appendChild(actions);
    body.appendChild(meta);
    card.appendChild(body);
    grid.appendChild(card);
  }
}

function setupCanvas() {
  document.querySelectorAll('.nav-subitem[data-open="canvas"]').forEach((btn) => {
    btn.addEventListener("click", () => {
      if (btn.dataset.mode === "templates") showCanvasTemplatesView();
      else if (btn.dataset.mode === "video") showCanvasView({ videoMode: true });
      else showCanvasView();
    });
  });
  el("canvas-video-select").addEventListener("change", (event) => pickOverlayVideo(event.target.value));
  el("canvas-apply-overlay").addEventListener("click", applyVideoOverlay);
  el("canvas-save-template").addEventListener("click", openTemplateNameRow);
  el("canvas-save-template-changes").addEventListener("click", saveTemplateChanges);
  el("canvas-template-name-confirm").addEventListener("click", saveAsNewTemplate);
  el("canvas-template-name-cancel").addEventListener("click", closeTemplateNameRow);
  el("canvas-template-name-input").addEventListener("keydown", (event) => {
    if (event.key === "Enter") saveAsNewTemplate();
    if (event.key === "Escape") closeTemplateNameRow();
  });
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
