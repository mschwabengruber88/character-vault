"use strict";

const KEY_STORAGE = "cv_generate_api_key";

const el = (id) => document.getElementById(id);

const state = {
  characters: [],
  selectedId: null,
  generating: false,
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
  el("detail-placeholder").hidden = character !== null;
  el("detail-content").hidden = character === null;
  if (!character) return;

  el("detail-name").textContent = character.name;
  el("detail-description").textContent = character.description || "";

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
  time.textContent = formatTimestamp(asset.created_at);
  meta.appendChild(time);
  if (asset.signed_url) {
    const open = document.createElement("a");
    open.href = asset.signed_url;
    open.target = "_blank";
    open.rel = "noopener";
    open.textContent = "Open ↗";
    meta.appendChild(open);
  }
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
    try {
      const created = await api("/characters", {
        method: "POST",
        body: JSON.stringify({
          name: el("create-name").value.trim(),
          description: el("create-description").value.trim(),
        }),
      });
      form.reset();
      form.hidden = true;
      await loadCharacters(created.id);
      toast(`Created “${created.name}”`);
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
    await api(`/characters/${state.selectedId}/generate/${kind}`, {
      method: "POST",
      headers: { "X-API-Key": apiKey() },
      body: JSON.stringify(kind === "image" ? { prompt: value } : { text: value }),
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
  setupDelete();
  setupKeyDialog();
  setupLightbox();
  refreshKeyButton();
  el("generate-image-button").addEventListener("click", () => generate("image"));
  el("generate-voice-button").addEventListener("click", () => generate("voice"));
  loadCharacters().catch((err) => toast(err.message, true));
}

init();
