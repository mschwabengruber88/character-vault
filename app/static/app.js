"use strict";

const KEY_STORAGE = "cv_generate_api_key";

const el = (id) => document.getElementById(id);

const state = {
  characters: [],
  selectedId: null,
  generating: false,
  imageModels: [],
  voices: {},
};

/* ---------- API helpers ---------- */

async function api(path, options = {}) {
  const { headers, ...rest } = options;
  const resp = await fetch(path, {
    ...rest,
    headers: { "Content-Type": "application/json", ...(headers || {}) },
  });
  if (resp.status === 204) return null;
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const detail = typeof body.detail === "string" ? body.detail : `Request failed (${resp.status})`;
    const err = new Error(detail);
    err.status = resp.status;
    throw err;
  }
  return body;
}

function apiKey() {
  return localStorage.getItem(KEY_STORAGE) || "";
}

/* ---------- Image models ---------- */

function selectedModel() {
  return state.imageModels.find((m) => m.slug === el("image-model").value);
}

function applyModelUI() {
  const model = selectedModel();
  if (!model) return;
  el("quality-choice").hidden = !model.quality_tiers;
  el("identity-hint").textContent = model.identity
    ? "this model locks facial identity"
    : "loose likeness only — for locked identity pick an identity model";
}

/* ---------- Voices ---------- */

const PROVIDER_LABEL = { openai: "OpenAI TTS", elevenlabs: "ElevenLabs" };

async function loadVoices() {
  state.voices = await api("/voices").catch(() => ({}));
}

function voiceOptionLabel(voice) {
  return voice.style ? `${voice.name} — ${voice.style}` : voice.name;
}

function populateVoiceSelect(character) {
  state.currentCharacter = character;
  renderVoiceOptions();
}

function renderVoiceOptions() {
  const character = state.currentCharacter;
  if (!character) return;
  const select = el("voice-select");
  const gender = el("filter-gender").value;
  const age = el("filter-age").value;
  const assigned = character.voice_id || "";
  const assignedProvider = character.voice_provider || "";
  select.innerHTML = "";
  let shown = 0;
  for (const [provider, voices] of Object.entries(state.voices)) {
    const filtered = voices.filter((v) => {
      const isAssigned = provider === assignedProvider && v.id === assigned;
      const matches = (!gender || v.gender === gender) && (!age || v.age === age);
      return matches || isAssigned;
    });
    if (!filtered.length) continue;
    const group = document.createElement("optgroup");
    group.label = PROVIDER_LABEL[provider] || provider;
    for (const voice of filtered) {
      const option = document.createElement("option");
      option.value = `${provider}:${voice.id}`;
      option.textContent = voiceOptionLabel(voice);
      if (provider === assignedProvider && voice.id === assigned) option.selected = true;
      group.appendChild(option);
      shown += 1;
    }
    select.appendChild(group);
  }
  if (shown === 0) {
    const opt = document.createElement("option");
    opt.textContent = "No voices match these filters";
    opt.disabled = true;
    select.appendChild(opt);
  }
  updateVoiceNote();
}

let previewAudio = null;

function previewSelectedVoice() {
  const value = el("voice-select").value;
  if (!value) return;
  const [provider, ...rest] = value.split(":");
  const voiceId = rest.join(":");
  const button = el("voice-preview");
  if (previewAudio) { previewAudio.pause(); previewAudio = null; }
  previewAudio = new Audio(`/static/voice-samples/${provider}-${voiceId}.mp3`);
  button.classList.add("playing");
  previewAudio.addEventListener("ended", () => button.classList.remove("playing"));
  previewAudio.addEventListener("error", () => {
    button.classList.remove("playing");
    toast("No sample available for this voice.", true);
  });
  previewAudio.play().catch(() => button.classList.remove("playing"));
}

function updateVoiceNote() {
  const note = el("voice-note");
  const provider = (el("voice-select").value || "").split(":")[0];
  if (provider === "elevenlabs") {
    note.textContent = "ElevenLabs may be unreachable from the cloud — it then falls back to an OpenAI voice.";
    note.hidden = false;
  } else {
    note.hidden = true;
  }
}

async function saveVoice() {
  const [provider, ...rest] = el("voice-select").value.split(":");
  const voiceId = rest.join(":");
  updateVoiceNote();
  try {
    await api(`/characters/${state.selectedId}/voice`, {
      method: "PUT",
      body: JSON.stringify({ voice_provider: provider, voice_id: voiceId }),
    });
    const character = state.characters.find((c) => c.id === state.selectedId);
    if (character) { character.voice_provider = provider; character.voice_id = voiceId; }
    toast("Voice assigned.");
  } catch (err) {
    toast(err.message, true);
  }
}

async function loadImageModels() {
  const caps = await api("/capabilities").catch(() => ({ image_models: [] }));
  state.imageModels = caps.image_models || [];
  const select = el("image-model");
  select.innerHTML = "";
  for (const model of state.imageModels) {
    const option = document.createElement("option");
    option.value = model.slug;
    option.textContent = model.label;
    select.appendChild(option);
  }
  select.addEventListener("change", applyModelUI);
  applyModelUI();
}

/* ---------- Toast ---------- */

let toastTimer = null;

function toast(message, isError = false) {
  const node = el("toast");
  node.textContent = message;
  node.classList.toggle("error", isError);
  node.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { node.hidden = true; }, 4000);
}

/* ---------- Characters ---------- */

async function loadCharacters(selectId = null) {
  state.characters = await api("/characters");
  renderCharacterList();
  const target = selectId ?? state.selectedId;
  if (target && state.characters.some((c) => c.id === target)) {
    await selectCharacter(target);
  } else if (state.characters.length === 0) {
    state.selectedId = null;
    renderDetail(null);
  }
}

function renderCharacterList() {
  const list = el("character-list");
  list.innerHTML = "";
  el("character-empty").hidden = state.characters.length > 0;
  for (const character of state.characters) {
    const li = document.createElement("li");
    li.classList.toggle("active", character.id === state.selectedId);
    const button = document.createElement("button");

    const avatar = document.createElement("span");
    avatar.className = "avatar";
    if (character.thumbnail_url) {
      const img = document.createElement("img");
      img.src = character.thumbnail_url;
      img.alt = "";
      avatar.appendChild(img);
    } else {
      avatar.textContent = character.name.trim().charAt(0).toUpperCase() || "?";
    }
    button.appendChild(avatar);

    const label = document.createElement("span");
    label.className = "character-name";
    label.textContent = character.name;
    button.appendChild(label);

    button.addEventListener("click", () => selectCharacter(character.id));
    li.appendChild(button);
    list.appendChild(li);
  }
}

async function selectCharacter(id) {
  state.selectedId = id;
  renderCharacterList();
  try {
    const character = await api(`/characters/${id}`);
    renderDetail(character);
  } catch (err) {
    toast(err.message, true);
  }
}

function renderDetail(character) {
  hideScenesView();
  el("detail-placeholder").hidden = character !== null;
  el("detail-content").hidden = character === null;
  if (!character) return;

  el("detail-name").textContent = character.name;
  el("detail-description").textContent = character.description || "";
  el("edit-form").hidden = true;

  const profile = el("detail-profile");
  profile.innerHTML = "";
  const rows = [
    ["Personality", character.personality],
    ["Purpose", character.purpose],
    ["Seed", character.seed != null ? String(character.seed) : ""],
  ];
  for (const [label, value] of rows) {
    if (!value) continue;
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = value;
    profile.append(dt, dd);
  }

  const imageCount = character.assets.filter((a) => a.kind === "image").length;
  el("identity-row").hidden = imageCount === 0;
  el("identity-count").textContent = String(Math.min(imageCount, 3));

  const spend = character.assets.reduce((sum, a) => sum + (a.cost_usd || 0), 0);
  el("detail-spend").hidden = spend === 0;
  el("detail-spend").textContent = `Generation spend so far: $${spend.toFixed(2)}`;

  populateVoiceSelect(character);

  const grid = el("asset-grid");
  grid.innerHTML = "";
  el("asset-empty").hidden = character.assets.length > 0;

  for (const asset of [...character.assets].reverse()) {
    grid.appendChild(renderAssetCard(asset));
  }
}

function formatTimestamp(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString(undefined, {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
  });
}

function openLightbox(src, caption) {
  el("lightbox-image").src = src;
  el("lightbox-caption").textContent = caption;
  el("lightbox").showModal();
}

function renderAssetCard(asset) {
  const card = document.createElement("div");
  card.className = "asset-card";

  const body = document.createElement("div");
  body.className = "asset-body";

  if (asset.kind === "image" && asset.signed_url) {
    const img = document.createElement("img");
    img.src = asset.signed_url;
    img.alt = asset.prompt;
    img.loading = "lazy";
    img.tabIndex = 0;
    img.addEventListener("click", () => openLightbox(asset.signed_url, asset.prompt));
    img.addEventListener("keydown", (event) => {
      if (event.key === "Enter") openLightbox(asset.signed_url, asset.prompt);
    });
    card.appendChild(img);
  } else if (asset.kind === "voice" && asset.signed_url) {
    const audio = document.createElement("audio");
    audio.controls = true;
    audio.src = asset.signed_url;
    audio.preload = "none";
    body.appendChild(audio);
  } else {
    const note = document.createElement("p");
    note.className = "asset-prompt";
    note.textContent = "Asset stored in B2 (preview unavailable)";
    body.appendChild(note);
  }

  const prompt = document.createElement("p");
  prompt.className = "asset-prompt";
  prompt.textContent = asset.prompt;
  prompt.title = asset.prompt;
  body.appendChild(prompt);

  const provenance = document.createElement("div");
  provenance.className = "provenance";
  const badge = document.createElement("span");
  badge.className = `badge ${asset.manifest_verified ? "verified" : "unverified"}`;
  badge.textContent = asset.manifest_verified ? "✓ manifest verified" : "manifest unverified";
  provenance.appendChild(badge);
  if (asset.disclosure) {
    const ai = document.createElement("span");
    ai.className = "badge ai";
    ai.textContent = asset.disclosure === "visible" ? "✦ AI · watermark" : "✦ AI · metadata";
    ai.title = asset.disclosure === "visible"
      ? "Visible AI watermark burned into the image"
      : "Provenance manifest embedded invisibly in the file";
    provenance.appendChild(ai);
  }
  if (asset.sha256) {
    const sha = document.createElement("span");
    sha.className = "sha";
    sha.textContent = asset.sha256.slice(0, 16);
    sha.title = `SHA-256: ${asset.sha256}`;
    provenance.appendChild(sha);
  }
  body.appendChild(provenance);

  const meta = document.createElement("div");
  meta.className = "asset-meta";
  const time = document.createElement("span");
  const parts = [formatTimestamp(asset.created_at)];
  if (asset.model) parts.push(asset.model.replace("gemini-2.5-flash-image", "nano-banana"));
  if (asset.quality) parts.push(asset.quality);
  if (typeof asset.cost_usd === "number") parts.push(`$${asset.cost_usd.toFixed(3)}`);
  time.textContent = parts.join(" · ");
  meta.appendChild(time);
  const actions = document.createElement("span");
  actions.className = "asset-actions";
  if (asset.signed_url) {
    const open = document.createElement("a");
    open.href = asset.signed_url;
    open.target = "_blank";
    open.rel = "noopener";
    open.textContent = "Open ↗";
    actions.appendChild(open);
  }
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "asset-delete";
  remove.textContent = "Delete";
  remove.addEventListener("click", async () => {
    if (!confirm("Delete this asset record?")) return;
    try {
      await api(`/assets/${asset.id}`, { method: "DELETE" });
      await selectCharacter(state.selectedId);
      await loadCharacters();
      toast("Asset deleted.");
    } catch (err) {
      toast(err.message, true);
    }
  });
  actions.appendChild(remove);
  meta.appendChild(actions);
  body.appendChild(meta);

  card.appendChild(body);
  return card;
}

/* ---------- Create / delete ---------- */

function setupCreateForm() {
  const form = el("create-form");
  el("new-character-button").addEventListener("click", () => {
    form.hidden = !form.hidden;
    if (!form.hidden) el("create-name").focus();
  });
  el("create-cancel").addEventListener("click", () => { form.hidden = true; });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const seedVal = el("create-seed").value.trim();
    try {
      const created = await api("/characters", {
        method: "POST",
        body: JSON.stringify({
          name: el("create-name").value.trim(),
          description: el("create-description").value.trim(),
          personality: el("create-personality").value.trim() || null,
          purpose: el("create-purpose").value.trim() || null,
          seed: seedVal ? Number(seedVal) : null,
        }),
      });
      const fileInput = el("create-image");
      if (fileInput.files.length) {
        await uploadReferenceImage(created.id, fileInput.files[0]);
      }
      form.reset();
      form.hidden = true;
      await loadCharacters(created.id);
      toast(`Created “${created.name}”`);
    } catch (err) {
      toast(err.message, true);
    }
  });
}

async function uploadReferenceImage(characterId, file) {
  if (!apiKey()) { openKeyDialog(); throw new Error("API key required to upload."); }
  const data = new FormData();
  data.append("file", file);
  const resp = await fetch(`/characters/${characterId}/reference`, {
    method: "POST", headers: { "X-API-Key": apiKey() }, body: data,
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : "Upload failed");
  }
  return resp.json();
}

function setupProfileEditing() {
  el("edit-profile-button").addEventListener("click", () => {
    const c = state.currentCharacter;
    if (!c) return;
    el("edit-name").value = c.name || "";
    el("edit-description").value = c.description || "";
    el("edit-personality").value = c.personality || "";
    el("edit-purpose").value = c.purpose || "";
    el("edit-seed").value = c.seed ?? "";
    el("edit-form").hidden = false;
  });
  el("edit-cancel").addEventListener("click", () => { el("edit-form").hidden = true; });
  el("edit-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const seedVal = el("edit-seed").value.trim();
    try {
      await api(`/characters/${state.selectedId}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: el("edit-name").value.trim(),
          description: el("edit-description").value.trim(),
          personality: el("edit-personality").value.trim(),
          purpose: el("edit-purpose").value.trim(),
          seed: seedVal ? Number(seedVal) : null,
        }),
      });
      el("edit-form").hidden = true;
      await selectCharacter(state.selectedId);
      await loadCharacters();
      toast("Profile saved.");
    } catch (err) {
      toast(err.message, true);
    }
  });
  el("upload-image").addEventListener("change", async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    try {
      await uploadReferenceImage(state.selectedId, file);
      event.target.value = "";
      await selectCharacter(state.selectedId);
      await loadCharacters();
      toast("Reference photo uploaded.");
    } catch (err) {
      toast(err.message, true);
    }
  });
}

function setupDelete() {
  el("delete-button").addEventListener("click", async () => {
    const character = state.characters.find((c) => c.id === state.selectedId);
    if (!character) return;
    if (!confirm(`Delete “${character.name}” and its asset records?`)) return;
    try {
      await api(`/characters/${character.id}`, { method: "DELETE" });
      state.selectedId = null;
      await loadCharacters();
      toast(`Deleted “${character.name}”`);
    } catch (err) {
      toast(err.message, true);
    }
  });
}

/* ---------- Generation ---------- */

function setGenerating(active, message = "", isError = false) {
  state.generating = active;
  el("generate-image-button").disabled = active;
  el("generate-voice-button").disabled = active;
  const status = el("generation-status");
  status.classList.toggle("error", isError);
  if (active) {
    status.innerHTML = `<span class="spinner" aria-hidden="true"></span>${message}`;
    status.hidden = false;
  } else if (message) {
    status.textContent = message;
    status.hidden = false;
  } else {
    status.hidden = true;
  }
}

async function generate(kind) {
  if (state.generating || !state.selectedId) return;
  const input = kind === "image" ? el("image-prompt") : el("voice-text");
  const value = input.value.trim();
  if (!value) {
    toast(kind === "image" ? "Describe the portrait first." : "Enter a line for the character to say.", true);
    input.focus();
    return;
  }
  if (!apiKey()) {
    openKeyDialog();
    return;
  }

  const label = kind === "image" ? "Generating portrait" : "Generating voice line";
  setGenerating(true, `${label}… this usually takes 15–60 seconds. The asset is uploaded to Backblaze B2 with a provenance manifest.`);

  try {
    const payload = kind === "image"
      ? {
          prompt: value,
          model: el("image-model").value,
          disclosure: document.querySelector('input[name="disclosure"]:checked').value,
          use_identity: !el("identity-row").hidden && el("use-identity").checked,
          quality: document.querySelector('input[name="quality"]:checked').value,
        }
      : { text: value };
    await api(`/characters/${state.selectedId}/generate/${kind}`, {
      method: "POST",
      headers: { "X-API-Key": apiKey() },
      body: JSON.stringify(payload),
    });
    input.value = "";
    setGenerating(false);
    await selectCharacter(state.selectedId);
    toast(kind === "image" ? "Portrait stored in the vault." : "Voice line stored in the vault.");
  } catch (err) {
    if (err.status === 401) {
      setGenerating(false, "", false);
      openKeyDialog();
      toast("Generation needs a valid API key.", true);
    } else {
      setGenerating(false, err.message, true);
    }
  }
}

/* ---------- API key dialog ---------- */

function refreshKeyButton() {
  el("key-button").classList.toggle("has-key", Boolean(apiKey()));
}

function openKeyDialog() {
  el("key-input").value = apiKey();
  el("key-dialog").showModal();
}

function setupKeyDialog() {
  el("key-button").addEventListener("click", openKeyDialog);
  el("key-dialog").addEventListener("close", () => {
    if (el("key-dialog").returnValue === "save") {
      const value = el("key-input").value.trim();
      if (value) {
        localStorage.setItem(KEY_STORAGE, value);
      } else {
        localStorage.removeItem(KEY_STORAGE);
      }
      refreshKeyButton();
    }
  });
}

/* ---------- Init ---------- */

/* ---------- Scenes / storytelling ---------- */

function showScenesView() {
  state.selectedId = null;
  renderCharacterList();
  el("detail-placeholder").hidden = true;
  el("detail-content").hidden = true;
  el("scenes-view").hidden = false;
  el("open-scenes").classList.add("active");
  renderSceneParticipants();
  loadScenes();
}

function hideScenesView() {
  el("scenes-view").hidden = true;
  el("open-scenes").classList.remove("active");
}

function renderSceneParticipants() {
  const box = el("scene-participants");
  box.innerHTML = "";
  const withPortrait = state.characters.filter((c) => c.thumbnail_url);
  if (!withPortrait.length) {
    box.innerHTML = '<p class="empty-note">Create at least two characters with a portrait first.</p>';
    return;
  }
  for (const character of withPortrait) {
    const label = document.createElement("label");
    label.className = "participant";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = String(character.id);
    const avatar = document.createElement("span");
    avatar.className = "avatar";
    const img = document.createElement("img");
    img.src = character.thumbnail_url;
    img.alt = "";
    avatar.appendChild(img);
    const name = document.createElement("span");
    name.textContent = character.name;
    label.append(cb, avatar, name);
    box.appendChild(label);
  }
}

async function loadScenes() {
  try {
    const scenes = await api("/scenes");
    renderScenes(scenes);
  } catch (err) {
    toast(err.message, true);
  }
}

function renderScenes(scenes) {
  const grid = el("scene-grid");
  grid.innerHTML = "";
  el("scene-empty").hidden = scenes.length > 0;
  for (const scene of scenes) {
    const card = document.createElement("div");
    card.className = "asset-card";
    if (scene.signed_url) {
      const img = document.createElement("img");
      img.src = scene.signed_url;
      img.alt = scene.prompt;
      img.loading = "lazy";
      img.tabIndex = 0;
      img.addEventListener("click", () => openLightbox(scene.signed_url, scene.prompt));
      card.appendChild(img);
    }
    const body = document.createElement("div");
    body.className = "asset-body";
    const who = document.createElement("p");
    who.className = "scene-who";
    who.textContent = (scene.participant_names || []).join(" + ");
    body.appendChild(who);
    const prompt = document.createElement("p");
    prompt.className = "asset-prompt";
    prompt.textContent = scene.prompt;
    body.appendChild(prompt);
    const meta = document.createElement("div");
    meta.className = "asset-meta";
    const time = document.createElement("span");
    time.textContent = `${formatTimestamp(scene.created_at)}${typeof scene.cost_usd === "number" ? ` · $${scene.cost_usd.toFixed(3)}` : ""}`;
    meta.appendChild(time);
    const actions = document.createElement("span");
    actions.className = "asset-actions";
    if (scene.signed_url) {
      const open = document.createElement("a");
      open.href = scene.signed_url;
      open.target = "_blank";
      open.rel = "noopener";
      open.textContent = "Open ↗";
      actions.appendChild(open);
    }
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "asset-delete";
    remove.textContent = "Delete";
    remove.addEventListener("click", async () => {
      if (!confirm("Delete this scene?")) return;
      try { await api(`/scenes/${scene.id}`, { method: "DELETE" }); loadScenes(); toast("Scene deleted."); }
      catch (err) { toast(err.message, true); }
    });
    actions.appendChild(remove);
    meta.appendChild(actions);
    body.appendChild(meta);
    card.appendChild(body);
    grid.appendChild(card);
  }
}

let sceneGenerating = false;

async function generateScene() {
  if (sceneGenerating) return;
  const ids = [...document.querySelectorAll("#scene-participants input:checked")].map((c) => Number(c.value));
  const prompt = el("scene-prompt").value.trim();
  if (ids.length < 2) { toast("Pick at least two characters.", true); return; }
  if (ids.length > 4) { toast("Pick at most four characters.", true); return; }
  if (!prompt) { toast("Describe the scene first.", true); el("scene-prompt").focus(); return; }
  if (!apiKey()) { openKeyDialog(); return; }

  sceneGenerating = true;
  el("generate-scene-button").disabled = true;
  const status = el("scene-status");
  status.classList.remove("error");
  status.innerHTML = '<span class="spinner" aria-hidden="true"></span>Composing the scene with Nano Banana… 20–60 seconds.';
  status.hidden = false;
  try {
    await api("/scenes", {
      method: "POST",
      headers: { "X-API-Key": apiKey() },
      body: JSON.stringify({ character_ids: ids, prompt }),
    });
    el("scene-prompt").value = "";
    status.hidden = true;
    await loadScenes();
    toast("Scene created.");
  } catch (err) {
    if (err.status === 401) { status.hidden = true; openKeyDialog(); toast("Scene generation needs a valid API key.", true); }
    else { status.classList.add("error"); status.textContent = err.message; }
  } finally {
    sceneGenerating = false;
    el("generate-scene-button").disabled = false;
  }
}

function setupLightbox() {
  const lightbox = el("lightbox");
  el("lightbox-close").addEventListener("click", () => lightbox.close());
  lightbox.addEventListener("click", (event) => {
    if (event.target === lightbox) lightbox.close();
  });
  lightbox.addEventListener("close", () => { el("lightbox-image").src = ""; });
}

function init() {
  setupCreateForm();
  setupProfileEditing();
  setupDelete();
  setupKeyDialog();
  setupLightbox();
  refreshKeyButton();
  el("generate-image-button").addEventListener("click", () => generate("image"));
  el("generate-voice-button").addEventListener("click", () => generate("voice"));
  el("voice-select").addEventListener("change", saveVoice);
  el("voice-preview").addEventListener("click", previewSelectedVoice);
  el("filter-gender").addEventListener("change", renderVoiceOptions);
  el("filter-age").addEventListener("change", renderVoiceOptions);
  el("open-scenes").addEventListener("click", showScenesView);
  el("generate-scene-button").addEventListener("click", generateScene);
  Promise.all([
    loadImageModels(),
    loadVoices(),
  ]).catch((err) => toast(err.message, true))
    .finally(() => loadCharacters().catch((err) => toast(err.message, true)));
}

init();
