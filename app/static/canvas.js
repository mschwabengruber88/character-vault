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
  el("canvas-background-select").addEventListener("change", (event) => setCanvasBackground(event.target.value));
  el("canvas-add-text").addEventListener("click", addCanvasText);
  el("canvas-add-rect").addEventListener("click", () => addCanvasShape("rect"));
  el("canvas-add-circle").addEventListener("click", () => addCanvasShape("circle"));
  el("canvas-add-line").addEventListener("click", () => addCanvasShape("line"));
  el("canvas-add-arrow").addEventListener("click", () => addCanvasShape("arrow"));
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
