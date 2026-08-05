/* Timeline — the cut. Loaded after app.js and canvas.js, and like canvas.js it
 * reuses app.js's globals (el, t, api, toast, state, renderCharacterList,
 * hide*View, setActiveNavGroup, formatTimestamp, workspaceId) rather than
 * duplicating them.
 *
 * The editor holds ONE sequence at a time in `tl`, mirroring what the server
 * stores: an ordered list of references into the vault plus per-clip
 * treatment. Nothing here copies media — a clip is a pointer, which is why
 * reordering and grading are instant and only rendering costs anything.
 *
 * The layout is the arrangement an editor is expected to have: the pool on the
 * left, the strip along the bottom, an inspector for the selection on the
 * right. Selection drives the inspector, the inspector writes straight back
 * into the clip, and every write marks the sequence dirty — no hidden state,
 * no separate apply step.
 */

const TL_LOOKS = ["none", "enhance", "warm", "cool", "noir", "vivid", "vintage", "soft"];
const TL_MOTIONS = ["none", "zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down"];
const TL_TRANSITIONS = ["cut", "fade", "dissolve"];
const TL_TITLE_STYLES = ["center", "lower_third", "left", "end_card"];
const TL_MAX_AUDIO_TRACKS = 4;
const TL_UNDO_LIMIT = 60;

// CSS approximations of the ffmpeg grades in SEQUENCE_LOOKS. Close enough to
// judge a look by, and deliberately not claimed to be exact — the render is
// the truth, this is the preview. They live here rather than in the stylesheet
// so the two halves of one decision sit next to each other.
const TL_LOOK_FILTERS = {
  none: "",
  enhance: "contrast(1.10) saturate(1.08)",
  warm: "sepia(0.18) saturate(1.12) contrast(1.06) hue-rotate(-8deg)",
  cool: "saturate(1.02) contrast(1.06) hue-rotate(12deg) brightness(1.02)",
  noir: "grayscale(1) contrast(1.28) brightness(0.98)",
  vivid: "contrast(1.14) saturate(1.35)",
  vintage: "sepia(0.32) saturate(0.88) contrast(0.96)",
  soft: "contrast(0.94) brightness(1.03) saturate(0.96) blur(0.4px)",
};

// One second of timeline maps to this many pixels, so a clip's width says how
// long it is — the one thing a plain list of cards cannot show.
const TL_PX_PER_SECOND = 26;
const TL_MIN_CLIP_PX = 74;

const tl = {
  id: null,
  name: "",
  aspectRatio: "16:9",
  resolution: "720p",
  clips: [],
  audioTracks: [],
  status: "draft",
  videoId: null,
  manifest: null,
  duration: null,
  selected: null,
  dirty: false,
  pool: [],
  poolFilter: "all",
  poolSearch: "",
  audioPool: [],
  pollTimer: null,
  undo: [],
  redo: [],
};

/* ---------- Undo ----------
 * Snapshots of the edit, not of the whole app: the pool, the selection and the
 * render result are not part of what Ctrl+Z should reach. Every mutating
 * action takes one BEFORE it changes anything, so undo restores the state the
 * user was looking at when they acted.
 */

function tlSnapshot() {
  return JSON.stringify({
    name: tl.name,
    aspectRatio: tl.aspectRatio,
    resolution: tl.resolution,
    clips: tl.clips,
    audioTracks: tl.audioTracks,
  });
}

function tlPushUndo() {
  const snapshot = tlSnapshot();
  if (tl.undo[tl.undo.length - 1] === snapshot) return;  // nothing actually moved
  tl.undo.push(snapshot);
  if (tl.undo.length > TL_UNDO_LIMIT) tl.undo.shift();
  tl.redo.length = 0;  // a fresh edit ends the redo branch, as everywhere else
  tlUpdateHeader();
}

function tlApplySnapshot(snapshot) {
  const restored = JSON.parse(snapshot);
  tl.name = restored.name;
  tl.aspectRatio = restored.aspectRatio;
  tl.resolution = restored.resolution || "720p";
  tl.clips = restored.clips;
  tl.audioTracks = restored.audioTracks;
  if (tl.selected !== null && tl.selected >= tl.clips.length) {
    tl.selected = tl.clips.length ? tl.clips.length - 1 : null;
  }
  el("tl-name").value = tl.name;
  el("tl-aspect").value = tl.aspectRatio;
  el("tl-resolution").value = tl.resolution;
  tl.dirty = true;
  tlRenderStrip();
  tlRenderInspector();
  tlRenderAudio();
  tlPreviewInvalidate();
}

function tlUndo() {
  if (!tl.undo.length) return;
  tl.redo.push(tlSnapshot());
  tlApplySnapshot(tl.undo.pop());
}

function tlRedo() {
  if (!tl.redo.length) return;
  tl.undo.push(tlSnapshot());
  tlApplySnapshot(tl.redo.pop());
}

function tlDefaultClip(entry) {
  const isVideo = entry.kind === "video";
  return {
    source: entry.source,
    ref_id: entry.ref_id,
    duration: isVideo ? (entry.duration || 5) : 3.5,
    in_point: isVideo ? 0 : null,
    out_point: isVideo ? (entry.duration || null) : null,
    transition: "cut",
    fade_duration: 0.5,
    look: "none",
    motion: "none",
    brightness: 0,
    contrast: 0,
    saturation: 0,
    volume: 1,
    text: null,
    subtitle: null,
    // Editor-only, never sent: the thumbnail, label and probed length the pool
    // already resolved, so the strip doesn't look them up on every redraw.
    _label: entry.label,
    _thumb: entry.signed_url,
    _sourceDuration: entry.duration || null,
  };
}

function tlClipLength(clip) {
  if (clip.source === "video") {
    const start = clip.in_point || 0;
    const end = clip.out_point != null ? clip.out_point : (clip._sourceDuration || start + 5);
    return Math.max(0.2, end - start);
  }
  return Math.max(0.2, clip.duration || 3.5);
}

// The span a transition actually gets, mirroring _plan_transitions on the
// server: capped by both clips it touches, and dropped entirely once it would
// be shorter than about three frames.
function tlTransitionSpan(index) {
  const clip = tl.clips[index];
  const kind = clip.transition || "cut";
  if (kind === "cut") return 0;
  const own = tlClipLength(clip);
  let span = Math.min(clip.fade_duration || 0.5, 2.0, own * 0.35, (own - 0.12) / 2);
  if (index > 0) {
    const previous = tlClipLength(tl.clips[index - 1]);
    span = Math.min(span, previous * 0.35, (previous - 0.12) / 2);
  }
  return span < 3 / 24 ? 0 : span;
}

function tlEffectiveTransition(index) {
  const clip = tl.clips[index];
  let kind = clip.transition || "cut";
  if (index === 0 && kind === "dissolve") kind = "fade";  // nothing to blend from
  return tlTransitionSpan(index) > 0 ? kind : "cut";
}

// Where each clip sits on the finished film. A dissolve OVERLAPS its two
// clips, so it pulls everything after it earlier — which is why the strip and
// the total cannot simply add lengths up.
function tlLayout() {
  let at = 0;
  return tl.clips.map((clip, index) => {
    const length = tlClipLength(clip);
    const kind = tlEffectiveTransition(index);
    const span = tlTransitionSpan(index);
    if (kind === "dissolve") at -= span;
    const entry = { clip, index, start: at, length, end: at + length, kind, span };
    at += length;
    return entry;
  });
}

function tlTotalLength() {
  const layout = tlLayout();
  return layout.length ? layout[layout.length - 1].end : 0;
}

function tlFormatSeconds(seconds) {
  if (seconds == null || Number.isNaN(Number(seconds))) return "–";
  const total = Math.max(0, Number(seconds));
  const mins = Math.floor(total / 60);
  const secs = total - mins * 60;
  return mins > 0 ? `${mins}:${secs.toFixed(1).padStart(4, "0")}` : `${secs.toFixed(1)}s`;
}

function tlMarkDirty() {
  tl.dirty = true;
  tlUpdateHeader();
  // The preview shows the edit, so every edit is a repaint. Cheap: it only
  // touches CSS on two layers.
  tlPreviewInvalidate();
}

/* ---------- Media pool ---------- */

async function tlLoadPool() {
  const [pool, audio] = await Promise.all([
    api("/timeline/pool").catch(() => []),
    api("/timeline/audio").catch(() => []),
  ]);
  tl.pool = pool;
  tl.audioPool = audio;
  tlRenderPool();
  tlPopulateAudioSelect();
}

function tlRenderPool() {
  const grid = el("tl-pool-grid");
  grid.innerHTML = "";
  const needle = tl.poolSearch.trim().toLowerCase();
  const items = tl.pool.filter((entry) => {
    if (tl.poolFilter !== "all" && entry.kind !== tl.poolFilter) return false;
    return !needle || (entry.label || "").toLowerCase().includes(needle);
  });
  el("tl-pool-empty").hidden = items.length > 0;

  for (const entry of items) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "tl-pool-card";
    card.title = t("tlPoolAdd");
    if (entry.signed_url) {
      const media = document.createElement(entry.kind === "video" ? "video" : "img");
      media.src = entry.signed_url;
      if (entry.kind === "video") {
        media.muted = true;
        media.preload = "metadata";
      } else {
        media.alt = "";
        media.loading = "lazy";
      }
      card.appendChild(media);
    } else {
      // A signed URL can be missing (expired link, storage not reachable).
      // The card still needs its picture area, or the badges — which are
      // positioned over it — land on top of the label instead.
      const placeholder = document.createElement("span");
      placeholder.className = "tl-pool-placeholder";
      placeholder.textContent = entry.kind === "video" ? "▷" : "▦";
      card.appendChild(placeholder);
    }
    const badge = document.createElement("span");
    badge.className = `tl-pool-badge ${entry.kind}`;
    badge.textContent = entry.kind === "video"
      ? tlFormatSeconds(entry.duration) : t("tlKindStill");
    card.appendChild(badge);
    if (entry.model === "upload") {
      const own = document.createElement("span");
      own.className = "tl-pool-own";
      // Short form: this sits opposite the kind badge on a ~96px card, and
      // the full wording collides with it there.
      own.textContent = t("tlOwnBadge");
      own.title = t("tlOwnFootage");
      card.appendChild(own);
    }
    const label = document.createElement("span");
    label.className = "tl-pool-label";
    label.textContent = entry.label;
    card.appendChild(label);
    card.addEventListener("click", () => tlAddClip(entry));
    grid.appendChild(card);
  }
}

function tlAddClip(entry) {
  tlPushUndo();
  tl.clips.push(tlDefaultClip(entry));
  tl.selected = tl.clips.length - 1;
  tlMarkDirty();
  tlRenderStrip();
  tlRenderInspector();
}

function tlAddTitleCard() {
  tlPushUndo();
  tl.clips.push({
    source: "title", ref_id: null, duration: 2.5, in_point: null, out_point: null,
    transition: "fade", fade_duration: 0.5, look: "none", motion: "none",
    brightness: 0, contrast: 0, saturation: 0, volume: 1,
    text: t("tlNewTitleText"), subtitle: null, title_style: "center",
    voice_url: null, voice_volume: 1,
  });
  tl.selected = tl.clips.length - 1;
  tlMarkDirty();
  tlRenderStrip();
  tlRenderInspector();
}

/* ---------- The strip ---------- */

let tlDragFrom = null;

function tlRenderStrip() {
  const strip = el("tl-strip");
  strip.innerHTML = "";
  el("tl-strip-empty").hidden = tl.clips.length > 0;

  tl.clips.forEach((clip, index) => {
    if (index > 0) {
      const kind = tlEffectiveTransition(index);
      const join = document.createElement("button");
      join.type = "button";
      join.className = `tl-join ${kind}`;
      join.title = t({ cut: "tlJoinCut", fade: "tlJoinFade", dissolve: "tlJoinDissolve" }[kind]);
      join.textContent = { cut: "▮", fade: "◐", dissolve: "◈" }[kind];
      // A transition belongs to the cut between two clips, so that is where it
      // is toggled. Reaching into a side panel to change what happens between
      // two things you can see is exactly the friction to avoid.
      // Clicking the join walks cut → fade → dissolve → cut, so the three
      // shapes are reachable without leaving the strip.
      join.addEventListener("click", () => {
        tlPushUndo();
        const order = TL_TRANSITIONS;
        clip.transition = order[(order.indexOf(clip.transition || "cut") + 1) % order.length];
        tlMarkDirty();
        tlRenderStrip();
        tlRenderInspector();
      });
      strip.appendChild(join);
    }

    const length = tlClipLength(clip);
    const card = document.createElement("div");
    card.className = "tl-clip" + (tl.selected === index ? " selected" : "");
    card.style.width = `${Math.max(TL_MIN_CLIP_PX, length * TL_PX_PER_SECOND)}px`;
    card.draggable = true;
    card.tabIndex = 0;

    if (clip.source === "title") {
      const cardText = document.createElement("span");
      cardText.className = "tl-clip-title";
      cardText.textContent = clip.text || t("tlNewTitleText");
      card.appendChild(cardText);
    } else if (clip._thumb) {
      const media = document.createElement(clip.source === "video" ? "video" : "img");
      media.src = clip._thumb;
      if (clip.source === "video") {
        media.muted = true;
        media.preload = "metadata";
      } else {
        media.alt = "";
      }
      card.appendChild(media);
    }

    const foot = document.createElement("span");
    foot.className = "tl-clip-foot";
    foot.textContent = tlFormatSeconds(length);
    card.appendChild(foot);

    if (clip.look && clip.look !== "none") {
      const look = document.createElement("span");
      look.className = "tl-clip-tag";
      look.textContent = t(`tlLook_${clip.look}`);
      card.appendChild(look);
    }
    if (clip.motion && clip.motion !== "none") {
      const motion = document.createElement("span");
      motion.className = "tl-clip-tag motion";
      motion.textContent = "⤢";
      motion.title = t(`tlMotion_${clip.motion}`);
      card.appendChild(motion);
    }

    card.addEventListener("click", () => {
      tl.selected = index;
      // Selecting a clip parks the playhead on it, so the stage shows what the
      // inspector is talking about instead of some other moment.
      const entry = tlLayout()[index];
      if (entry && !preview.playing) preview.at = entry.start;
      tlRenderStrip();
      tlRenderInspector();
      tlPaintPreview();
    });
    card.addEventListener("dragstart", () => {
      tlDragFrom = index;
      card.classList.add("dragging");
    });
    card.addEventListener("dragend", () => {
      tlDragFrom = null;
      card.classList.remove("dragging");
    });
    card.addEventListener("dragover", (event) => {
      event.preventDefault();
      card.classList.add("drop-target");
    });
    card.addEventListener("dragleave", () => card.classList.remove("drop-target"));
    card.addEventListener("drop", (event) => {
      event.preventDefault();
      card.classList.remove("drop-target");
      if (tlDragFrom === null || tlDragFrom === index) return;
      tlPushUndo();
      const [moved] = tl.clips.splice(tlDragFrom, 1);
      tl.clips.splice(index, 0, moved);
      tl.selected = index;
      tlMarkDirty();
      tlRenderStrip();
      tlRenderInspector();
    });
    strip.appendChild(card);
  });

  tlUpdateHeader();
}

function tlMoveSelected(offset) {
  const from = tl.selected;
  if (from === null) return;
  const to = from + offset;
  if (to < 0 || to >= tl.clips.length) return;
  tlPushUndo();
  const [moved] = tl.clips.splice(from, 1);
  tl.clips.splice(to, 0, moved);
  tl.selected = to;
  tlMarkDirty();
  tlRenderStrip();
  tlRenderInspector();
}

function tlRemoveSelected() {
  if (tl.selected === null) return;
  tlPushUndo();
  tl.clips.splice(tl.selected, 1);
  tl.selected = tl.clips.length ? Math.min(tl.selected, tl.clips.length - 1) : null;
  tlMarkDirty();
  tlRenderStrip();
  tlRenderInspector();
}

function tlDuplicateSelected() {
  if (tl.selected === null) return;
  tlPushUndo();
  tl.clips.splice(tl.selected + 1, 0, { ...tl.clips[tl.selected] });
  tl.selected += 1;
  tlMarkDirty();
  tlRenderStrip();
  tlRenderInspector();
}

/* ---------- Inspector ---------- */

function tlField(label, control, hint) {
  const row = document.createElement("label");
  row.className = "tl-field";
  const caption = document.createElement("span");
  caption.className = "tl-field-label";
  caption.textContent = label;
  row.append(caption, control);
  if (hint) {
    const note = document.createElement("span");
    note.className = "tl-field-hint";
    note.textContent = hint;
    row.appendChild(note);
  }
  return row;
}

function tlSelect(options, value, onChange) {
  const select = document.createElement("select");
  select.className = "filter-select";
  for (const [optionValue, optionLabel] of options) {
    const option = document.createElement("option");
    option.value = optionValue;
    option.textContent = optionLabel;
    select.appendChild(option);
  }
  select.value = value;
  select.addEventListener("change", () => {
    tlPushUndo();
    onChange(select.value);
  });
  return select;
}

function tlNumber(value, { min, max, step }, onChange) {
  const input = document.createElement("input");
  input.type = "number";
  input.className = "tl-number";
  input.min = min;
  input.max = max;
  input.step = step;
  input.value = value;
  input.addEventListener("change", () => {
    tlPushUndo();
    onChange(Number(input.value));
  });
  return input;
}

function tlSlider(value, { min, max, step }, onChange) {
  const wrap = document.createElement("span");
  wrap.className = "tl-slider";
  const input = document.createElement("input");
  input.type = "range";
  input.min = min;
  input.max = max;
  input.step = step;
  input.value = value;
  const readout = document.createElement("span");
  readout.className = "tl-slider-value";
  readout.textContent = Number(value).toFixed(2);
  // One undo step per DRAG, not per pixel: the snapshot is taken on the first
  // movement and the flag clears when the handle is released.
  let dragging = false;
  input.addEventListener("input", () => {
    if (!dragging) {
      dragging = true;
      tlPushUndo();
    }
    readout.textContent = Number(input.value).toFixed(2);
    onChange(Number(input.value));
  });
  input.addEventListener("change", () => { dragging = false; });
  wrap.append(input, readout);
  return wrap;
}

function tlRenderInspector() {
  const panel = el("tl-inspector-body");
  panel.innerHTML = "";
  const clip = tl.selected === null ? null : tl.clips[tl.selected];
  el("tl-inspector-empty").hidden = !!clip;
  el("tl-inspector-actions").hidden = !clip;
  if (!clip) return;

  const heading = document.createElement("p");
  heading.className = "tl-inspector-heading";
  heading.textContent = clip.source === "title"
    ? t("tlClipTitleCard")
    : `${t(`tlSource_${clip.source}`)} — ${clip._label || `#${clip.ref_id}`}`;
  panel.appendChild(heading);

  if (clip.source === "title") {
    const text = document.createElement("input");
    text.type = "text";
    text.maxLength = 300;
    text.value = clip.text || "";
    text.addEventListener("input", () => {
      clip.text = text.value;
      tlMarkDirty();
      tlRenderStrip();
    });
    panel.appendChild(tlField(t("tlTitleText"), text));

    const subtitle = document.createElement("input");
    subtitle.type = "text";
    subtitle.maxLength = 300;
    subtitle.value = clip.subtitle || "";
    subtitle.addEventListener("input", () => {
      clip.subtitle = subtitle.value || null;
      tlMarkDirty();
    });
    panel.appendChild(tlField(t("tlTitleSubtitle"), subtitle));

    panel.appendChild(tlField(t("tlTitleStyle"), tlSelect(
      TL_TITLE_STYLES.map((style) => [style, t(`tlTitleStyle_${style}`)]),
      clip.title_style || "center",
      (value) => { clip.title_style = value; tlMarkDirty(); tlRenderStrip(); },
    ), t("tlTitleStyleHint")));
  }

  if (clip.source === "video") {
    // In/out against the clip's real length. The preview jumps to whichever
    // handle just moved — a trim you cannot see is a trim you get wrong.
    const preview = document.createElement("video");
    preview.className = "tl-trim-preview";
    preview.src = clip._thumb || "";
    preview.controls = true;
    preview.preload = "metadata";
    preview.addEventListener("loadedmetadata", () => {
      if (!clip._sourceDuration && Number.isFinite(preview.duration)) {
        clip._sourceDuration = preview.duration;
        if (clip.out_point == null) clip.out_point = preview.duration;
        tlRenderStrip();
        tlRenderInspector();
      }
    });
    panel.appendChild(preview);

    const total = clip._sourceDuration || 60;
    panel.appendChild(tlField(t("tlIn"), tlNumber(
      clip.in_point || 0, { min: 0, max: total, step: 0.1 },
      (value) => {
        clip.in_point = Math.max(0, Math.min(value, (clip.out_point ?? total) - 0.2));
        preview.currentTime = clip.in_point;
        tlMarkDirty();
        tlRenderStrip();
        tlRenderInspector();
      },
    )));
    panel.appendChild(tlField(t("tlOut"), tlNumber(
      clip.out_point ?? total, { min: 0, max: total, step: 0.1 },
      (value) => {
        clip.out_point = Math.min(total, Math.max(value, (clip.in_point || 0) + 0.2));
        preview.currentTime = clip.out_point;
        tlMarkDirty();
        tlRenderStrip();
        tlRenderInspector();
      },
    ), t("tlTrimHint")));

    panel.appendChild(tlField(t("tlVolume"), tlSlider(
      clip.volume ?? 1, { min: 0, max: 2, step: 0.05 },
      (value) => { clip.volume = value; tlMarkDirty(); },
    )));
  } else {
    panel.appendChild(tlField(t("tlDuration"), tlNumber(
      clip.duration ?? 3.5, { min: 0.2, max: 60, step: 0.1 },
      (value) => { clip.duration = value; tlMarkDirty(); tlRenderStrip(); },
    )));
  }

  panel.appendChild(tlField(t("tlTransition"), tlSelect(
    TL_TRANSITIONS.map((kind) => [kind, t(`tlTransition_${kind}`)]),
    clip.transition || "cut",
    (value) => { clip.transition = value; tlMarkDirty(); tlRenderStrip(); tlRenderInspector(); },
  ), t(clip.transition === "dissolve" ? "tlTransitionDissolveHint" : "tlTransitionHint")));

  if ((clip.transition || "cut") !== "cut") {
    // A transition the renderer will have to shorten says so here rather than
    // silently coming back different.
    const clamped = tlTransitionSpan(tl.selected) < (clip.fade_duration ?? 0.5) - 0.01;
    panel.appendChild(tlField(t("tlFadeLength"), tlNumber(
      clip.fade_duration ?? 0.5, { min: 0.1, max: 2, step: 0.1 },
      (value) => { clip.fade_duration = value; tlMarkDirty(); tlRenderStrip(); tlRenderInspector(); },
    ), clamped ? t("tlTransitionClamped") : null));
  }

  panel.appendChild(tlField(t("tlLook"), tlSelect(
    TL_LOOKS.map((look) => [look, t(`tlLook_${look}`)]),
    clip.look || "none",
    (value) => { clip.look = value; tlMarkDirty(); tlRenderStrip(); },
  )));

  if (clip.source !== "video") {
    // Ken Burns is for stills only: a moving clip already has motion, and a
    // second one layered on top just fights it.
    panel.appendChild(tlField(t("tlMotion"), tlSelect(
      TL_MOTIONS.map((motion) => [motion, t(`tlMotion_${motion}`)]),
      clip.motion || "none",
      (value) => { clip.motion = value; tlMarkDirty(); tlRenderStrip(); },
    ), t("tlMotionHint")));
  }

  const grade = document.createElement("details");
  grade.className = "tl-grade";
  const summary = document.createElement("summary");
  summary.textContent = t("tlGrade");
  grade.appendChild(summary);
  grade.appendChild(tlField(t("tlBrightness"), tlSlider(
    clip.brightness ?? 0, { min: -0.5, max: 0.5, step: 0.01 },
    (value) => { clip.brightness = value; tlMarkDirty(); },
  )));
  grade.appendChild(tlField(t("tlContrast"), tlSlider(
    clip.contrast ?? 0, { min: -0.8, max: 1.5, step: 0.01 },
    (value) => { clip.contrast = value; tlMarkDirty(); },
  )));
  grade.appendChild(tlField(t("tlSaturation"), tlSlider(
    clip.saturation ?? 0, { min: -1, max: 2, step: 0.01 },
    (value) => { clip.saturation = value; tlMarkDirty(); },
  )));
  panel.appendChild(grade);

  // A voice line on THIS clip — the motion comic's one-voice-per-panel idea,
  // available per clip. Picking one can also set the clip's length to match,
  // which is the whole point of speaking over a still.
  const voice = tlSelect(
    [["", t("tlVoiceNone")], ...tl.audioPool.map((track) => [track.url, track.label])],
    clip.voice_url || "",
    (value) => { clip.voice_url = value || null; tlMarkDirty(); tlRenderInspector(); },
  );
  panel.appendChild(tlField(t("tlVoice"), voice, t("tlVoiceHint")));

  if (clip.voice_url) {
    panel.appendChild(tlField(t("tlVoiceVolume"), tlSlider(
      clip.voice_volume ?? 1, { min: 0, max: 2, step: 0.05 },
      (value) => { clip.voice_volume = value; tlMarkDirty(); },
    )));
    if (clip.source !== "video") {
      const fit = document.createElement("button");
      fit.type = "button";
      fit.className = "button small";
      fit.textContent = t("tlVoiceFit");
      fit.addEventListener("click", () => {
        const entry = tl.audioPool.find((track) => track.url === clip.voice_url);
        if (!entry || !entry.signed_url) return;
        // The length is read from the file itself rather than guessed — the
        // still should stay up for exactly as long as the line takes.
        const probe = new Audio(entry.signed_url);
        probe.addEventListener("loadedmetadata", () => {
          if (!Number.isFinite(probe.duration)) return;
          tlPushUndo();
          clip.duration = Math.max(0.2, Math.min(60, probe.duration));
          tlMarkDirty();
          tlRenderStrip();
          tlRenderInspector();
        });
      });
      panel.appendChild(tlField(t("tlVoiceFitLabel"), fit));
    }
  }

  if (clip.source !== "title") {
    const caption = document.createElement("input");
    caption.type = "text";
    caption.maxLength = 300;
    caption.value = clip.text || "";
    caption.disabled = clip.source === "video";
    caption.addEventListener("input", () => {
      clip.text = caption.value || null;
      tlMarkDirty();
    });
    panel.appendChild(tlField(t("tlCaption"), caption,
      clip.source === "video" ? t("tlCaptionVideoHint") : t("tlCaptionHint")));
  }
}

/* ---------- Audio laid under the cut ---------- */

function tlRenderAudio() {
  const lane = el("tl-audio-lane");
  lane.innerHTML = "";
  el("tl-audio-empty").hidden = tl.audioTracks.length > 0;
  tl.audioTracks.forEach((track, index) => {
    const row = document.createElement("div");
    row.className = "tl-audio-track";

    const label = document.createElement("span");
    label.className = "tl-audio-label";
    label.textContent = track.label || t("tlAudioTrack");
    row.appendChild(label);

    const volume = document.createElement("input");
    volume.type = "range";
    volume.min = 0;
    volume.max = 1;
    volume.step = 0.05;
    volume.value = track.volume ?? 0.25;
    volume.title = t("tlAudioVolume");
    volume.addEventListener("input", () => {
      track.volume = Number(volume.value);
      tlMarkDirty();
    });
    row.appendChild(volume);

    const duck = document.createElement("label");
    duck.className = "tl-audio-duck";
    const duckBox = document.createElement("input");
    duckBox.type = "checkbox";
    duckBox.checked = track.duck !== false;
    duckBox.addEventListener("change", () => {
      tlPushUndo();
      track.duck = duckBox.checked;
      tlMarkDirty();
    });
    const duckLabel = document.createElement("span");
    duckLabel.textContent = t("tlDuck");
    duck.title = t("tlDuckHint");
    duck.append(duckBox, duckLabel);
    row.appendChild(duck);

    const listen = document.createElement("audio");
    listen.controls = true;
    listen.preload = "none";
    listen.src = track.signed_url || "";
    if (track.signed_url) row.appendChild(listen);

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "button small";
    remove.textContent = t("tlRemove");
    remove.addEventListener("click", () => {
      tlPushUndo();
      tl.audioTracks.splice(index, 1);
      tlMarkDirty();
      tlRenderAudio();
    });
    row.appendChild(remove);
    lane.appendChild(row);
  });
}

function tlPopulateAudioSelect() {
  const select = el("tl-audio-select");
  select.innerHTML = "";
  const blank = document.createElement("option");
  blank.value = "";
  blank.textContent = t("tlAudioPick");
  select.appendChild(blank);
  for (const track of tl.audioPool) {
    const option = document.createElement("option");
    option.value = track.url;
    option.dataset.label = track.label;
    option.dataset.signed = track.signed_url || "";
    option.textContent = track.label;
    select.appendChild(option);
  }
}

function tlAddAudioTrack(url, label, signedUrl) {
  if (!url) return;
  if (tl.audioTracks.length >= TL_MAX_AUDIO_TRACKS) {
    toast(t("tlAudioMax"), true);
    return;
  }
  tlPushUndo();
  tl.audioTracks.push({
    url, volume: 0.25, duck: true,
    label: label || t("tlAudioTrack"), signed_url: signedUrl || null,
  });
  tlMarkDirty();
  tlRenderAudio();
}

/* ---------- Preview ----------
 * Plays the cut in the browser, before anything is rendered. This is the
 * difference between an editor and a form that submits to ffmpeg: you can see
 * the pacing, the grade and the transitions while you are still deciding them,
 * instead of waiting minutes to find out.
 *
 * It is an approximation on purpose, and says so in the UI: looks become CSS
 * filters, camera moves become CSS transforms, and a dissolve becomes two
 * stacked layers cross-fading. Anything the browser cannot do faithfully — the
 * exact grade maths, the audio ducking — is left to the render rather than
 * faked badly here.
 *
 * Two layers exist so a dissolve has something to dissolve between; a plain
 * cut only ever uses the first.
 */

const preview = {
  playing: false,
  at: 0,
  last: 0,
  raf: null,
  audio: [],
  loaded: [null, null],
};

function tlLayerNodes(which) {
  return {
    box: el(`tl-stage-${which}`),
    img: el(`tl-stage-${which}-img`),
    video: el(`tl-stage-${which}-video`),
  };
}

function tlGradeFilter(clip) {
  const parts = [TL_LOOK_FILTERS[clip.look || "none"] || ""];
  const brightness = 1 + (clip.brightness || 0);
  const contrast = 1 + (clip.contrast || 0);
  const saturation = 1 + (clip.saturation || 0);
  if (Math.abs(brightness - 1) > 0.001) parts.push(`brightness(${brightness.toFixed(3)})`);
  if (Math.abs(contrast - 1) > 0.001) parts.push(`contrast(${contrast.toFixed(3)})`);
  if (Math.abs(saturation - 1) > 0.001) parts.push(`saturate(${saturation.toFixed(3)})`);
  return parts.filter(Boolean).join(" ") || "none";
}

function tlMotionTransform(clip, progress) {
  const motion = clip.motion || "none";
  if (motion === "none") return "none";
  const peak = 1.12;
  const travel = 6;  // per cent of the frame, matching zoompan's ~12% crop walk
  if (motion === "zoom_in") return `scale(${(1 + (peak - 1) * progress).toFixed(4)})`;
  if (motion === "zoom_out") return `scale(${(peak - (peak - 1) * progress).toFixed(4)})`;
  const shift = (progress - 0.5) * 2 * travel;
  if (motion === "pan_right") return `scale(${peak}) translateX(${-shift}%)`;
  if (motion === "pan_left") return `scale(${peak}) translateX(${shift}%)`;
  if (motion === "pan_down") return `scale(${peak}) translateY(${-shift}%)`;
  return `scale(${peak}) translateY(${shift}%)`;
}

function tlPaintLayer(which, entry, at, opacity) {
  const nodes = tlLayerNodes(which);
  if (!entry) {
    nodes.box.style.opacity = "0";
    if (!nodes.video.paused) nodes.video.pause();
    return;
  }
  const { clip } = entry;
  const offset = Math.max(0, Math.min(at - entry.start, entry.length));
  const progress = entry.length > 0 ? offset / entry.length : 0;
  const isVideo = clip.source === "video";
  const key = `${entry.index}:${clip.source}:${clip._thumb || clip.text}`;

  nodes.box.style.opacity = String(opacity);
  nodes.img.hidden = isVideo;
  nodes.video.hidden = !isVideo;

  if (preview.loaded[which === "a" ? 0 : 1] !== key) {
    preview.loaded[which === "a" ? 0 : 1] = key;
    if (isVideo) {
      nodes.video.src = clip._thumb || "";
      nodes.video.currentTime = (clip.in_point || 0) + offset;
    } else if (clip.source === "title") {
      nodes.img.removeAttribute("src");
    } else {
      nodes.img.src = clip._thumb || "";
    }
  }

  // A text panel has no stored image — the server draws it with Pillow at
  // render time. Showing the words in the same arrangement is a fair preview
  // of the timing, which is what the player is for.
  const card = el(`tl-stage-${which}-card`);
  card.hidden = clip.source !== "title";
  if (clip.source === "title") {
    card.className = `tl-stage-card ${clip.title_style || "center"}`;
    card.innerHTML = "";
    const headline = document.createElement("strong");
    headline.textContent = clip.text || "";
    card.appendChild(headline);
    if (clip.subtitle) {
      const sub = document.createElement("span");
      sub.textContent = clip.subtitle;
      card.appendChild(sub);
    }
  }

  const media = isVideo ? nodes.video : nodes.img;
  media.style.filter = tlGradeFilter(clip);
  media.style.transform = tlMotionTransform(clip, progress);
  if (clip.source === "title") card.style.filter = tlGradeFilter(clip);

  if (isVideo) {
    const target = (clip.in_point || 0) + offset;
    if (preview.playing) {
      if (Math.abs(nodes.video.currentTime - target) > 0.35) nodes.video.currentTime = target;
      nodes.video.volume = Math.max(0, Math.min(1, (clip.volume ?? 1) / 2));
      if (nodes.video.paused) nodes.video.play().catch(() => {});
    } else {
      if (!nodes.video.paused) nodes.video.pause();
      if (Math.abs(nodes.video.currentTime - target) > 0.05) nodes.video.currentTime = target;
    }
  }
}

function tlPaintPreview() {
  const layout = tlLayout();
  const total = layout.length ? layout[layout.length - 1].end : 0;
  const at = Math.max(0, Math.min(preview.at, total));

  const current = layout.filter((entry) => at >= entry.start && at < entry.end);
  const active = current[current.length - 1] || layout[layout.length - 1] || null;
  const under = current.length > 1 ? current[0] : null;

  let blackness = 0;
  let topOpacity = 1;

  if (active) {
    const span = active.span;
    if (active.kind === "dissolve" && under && span > 0) {
      // Both clips are on screen; the incoming one comes up over the outgoing.
      topOpacity = Math.min(1, (at - active.start) / span);
    } else if (active.kind === "fade" && span > 0 && at - active.start < span) {
      blackness = 1 - (at - active.start) / span;   // lifting out of black
    }
    const next = layout[active.index + 1];
    if (next && next.kind === "fade" && next.span > 0 && active.end - at < next.span) {
      blackness = Math.max(blackness, 1 - (active.end - at) / next.span);
    }
  }

  tlPaintLayer("a", under || active, at, 1);
  tlPaintLayer("b", under ? active : null, at, topOpacity);
  el("tl-stage-black").style.opacity = String(blackness);

  el("tl-playhead").style.left = total > 0 ? `${(at / total) * 100}%` : "0%";
  el("tl-preview-time").textContent = `${tlFormatSeconds(at)} / ${tlFormatSeconds(total)}`;
}

function tlPreviewAudio(start) {
  preview.audio.forEach((node) => { node.pause(); });
  preview.audio = [];
  if (!preview.playing) return;
  for (const track of tl.audioTracks) {
    if (!track.signed_url) continue;   // uploaded this session, no signed link yet
    const node = new Audio(track.signed_url);
    node.volume = Math.max(0, Math.min(1, track.volume ?? 0.25));
    node.loop = true;
    node.currentTime = 0;
    node.play().catch(() => {});
    preview.audio.push(node);
  }
  void start;
}

function tlPreviewTick(now) {
  if (!preview.playing) return;
  const delta = (now - preview.last) / 1000;
  preview.last = now;
  preview.at += delta;
  const total = tlTotalLength();
  if (preview.at >= total) {
    preview.at = total;
    tlPreviewStop();
    tlPaintPreview();
    return;
  }
  tlPaintPreview();
  preview.raf = requestAnimationFrame(tlPreviewTick);
}

function tlPreviewPlay() {
  if (!tl.clips.length || preview.playing) return;
  if (preview.at >= tlTotalLength() - 0.01) preview.at = 0;
  preview.playing = true;
  preview.last = performance.now();
  el("tl-preview-play").textContent = "⏸";
  tlPreviewAudio(preview.at);
  preview.raf = requestAnimationFrame(tlPreviewTick);
}

function tlPreviewStop() {
  preview.playing = false;
  cancelAnimationFrame(preview.raf);
  el("tl-preview-play").textContent = "▶";
  preview.audio.forEach((node) => node.pause());
  preview.audio = [];
  ["a", "b"].forEach((which) => {
    const node = tlLayerNodes(which).video;
    if (!node.paused) node.pause();
  });
}

function tlPreviewToggle() {
  if (preview.playing) tlPreviewStop();
  else tlPreviewPlay();
}

function tlPreviewSeek(fraction) {
  preview.at = Math.max(0, Math.min(1, fraction)) * tlTotalLength();
  tlPaintPreview();
}

function tlPreviewInvalidate() {
  // The edit changed underneath the player: forget which media is loaded so
  // the next paint picks up new sources, and clamp the playhead into range.
  preview.loaded = [null, null];
  preview.at = Math.min(preview.at, tlTotalLength());
  tlPaintPreview();
}

function tlPreviewAspect() {
  const stage = el("tl-stage");
  stage.style.aspectRatio = { "16:9": "16 / 9", "9:16": "9 / 16", "1:1": "1 / 1" }[tl.aspectRatio];
}

/* ---------- Save, render, provenance ---------- */

function tlPayload() {
  return {
    name: tl.name.trim() || t("tlUntitled"),
    aspect_ratio: tl.aspectRatio,
    resolution: tl.resolution,
    // The underscore-prefixed fields are editor-only (thumbnail, label, probed
    // source length) and deliberately stripped: the server has its own copy of
    // all three, and sending them back would only invite them to drift.
    clips: tl.clips.map(({ _label, _thumb, _sourceDuration, ...clip }) => clip),
    audio_tracks: tl.audioTracks.map(({ url, volume, duck, label }) =>
      ({ url, volume, duck: duck !== false, label })),
  };
}

function tlAdoptSequence(sequence) {
  tl.id = sequence.id;
  tl.name = sequence.name;
  tl.aspectRatio = sequence.aspect_ratio;
  tl.resolution = sequence.resolution || "720p";
  tl.status = sequence.status;
  tl.videoId = sequence.video_id;
  tl.manifest = sequence.manifest;
  tl.duration = sequence.duration;
  tl.audioTracks = sequence.audio_tracks || [];
  // Stored clips carry no thumbnails — re-attach them from the pool so a
  // reopened sequence looks like the one that was saved.
  const byKey = new Map(tl.pool.map((entry) => [`${entry.source}:${entry.ref_id}`, entry]));
  tl.clips = (sequence.clips || []).map((clip) => {
    const entry = byKey.get(`${clip.source}:${clip.ref_id}`);
    return {
      ...clip,
      _label: entry ? entry.label : null,
      _thumb: entry ? entry.signed_url : null,
      _sourceDuration: entry ? entry.duration : null,
    };
  });
  // Audio tracks come back with plain bucket URLs; re-attach the signed links
  // from the pool so they can be auditioned and heard in the preview.
  const audioByUrl = new Map(tl.audioPool.map((track) => [track.url, track]));
  tl.audioTracks = tl.audioTracks.map((track) => ({
    ...track, signed_url: (audioByUrl.get(track.url) || {}).signed_url || null,
  }));

  tl.selected = tl.clips.length ? 0 : null;
  tl.dirty = false;
  tl.undo.length = 0;
  tl.redo.length = 0;
  preview.at = 0;
  el("tl-name").value = tl.name;
  el("tl-aspect").value = tl.aspectRatio;
  el("tl-resolution").value = tl.resolution;
  tlPreviewAspect();
  tlRenderStrip();
  tlRenderInspector();
  tlRenderAudio();
  tlRenderResult();
  tlPreviewInvalidate();
}

async function tlSave() {
  if (!tl.clips.length) {
    toast(t("tlNothingToSave"), true);
    return null;
  }
  try {
    const sequence = tl.id
      ? await api(`/sequences/${tl.id}`, { method: "PUT", body: JSON.stringify(tlPayload()) })
      : await api("/sequences", { method: "POST", body: JSON.stringify(tlPayload()) });
    tl.id = sequence.id;
    tl.dirty = false;
    tlUpdateHeader();
    toast(t("tlSaved"));
    return sequence;
  } catch (err) {
    toast(err.message, true);
    return null;
  }
}

async function tlRender() {
  // Rendering always renders what is on screen. Saving first removes the whole
  // class of "I changed it and got the old cut back".
  const saved = await tlSave();
  if (!saved) return;
  const status = el("tl-status");
  try {
    await api(`/sequences/${tl.id}/render`, { method: "POST" });
    tl.status = "rendering";
    status.classList.remove("error");
    status.innerHTML = `<span class="spinner" aria-hidden="true"></span>${t("tlRendering")}`;
    status.hidden = false;
    tlUpdateHeader();
    tlPollRender();
  } catch (err) {
    status.classList.add("error");
    status.textContent = err.message;
    status.hidden = false;
  }
}

function tlPollRender() {
  clearTimeout(tl.pollTimer);
  tl.pollTimer = setTimeout(async () => {
    if (!tl.id) return;
    try {
      const sequence = await api(`/sequences/${tl.id}`);
      tl.status = sequence.status;
      if (sequence.status === "rendering") {
        tlPollRender();
        return;
      }
      const status = el("tl-status");
      if (sequence.status === "error") {
        status.classList.add("error");
        status.textContent = sequence.error || t("tlRenderFailed");
        status.hidden = false;
      } else {
        status.hidden = true;
        tl.videoId = sequence.video_id;
        tl.manifest = sequence.manifest;
        tl.duration = sequence.duration;
        toast(t("tlRenderDone"));
        tlRenderResult();
        // The finished cut is itself a vault clip now, so it can go into the
        // next one.
        tlLoadPool().catch(() => {});
      }
      tlUpdateHeader();
    } catch {
      tlPollRender();
    }
  }, 2500);
}

async function tlRenderResult() {
  const wrap = el("tl-result");
  wrap.hidden = !(tl.videoId && tl.status === "done");
  if (wrap.hidden) return;
  try {
    const video = await api(`/videos/${tl.videoId}`);
    el("tl-result-video").src = video.signed_url || "";
    const download = el("tl-result-download");
    download.href = video.signed_url || "#";
    el("tl-result-meta").textContent = t("tlResultMeta")
      .replace("{duration}", tlFormatSeconds(tl.duration))
      .replace("{clips}", String((tl.manifest && tl.manifest.sequence.clip_count) || tl.clips.length));
  } catch (err) {
    toast(err.message, true);
  }
  tlRenderProvenance();
}

function tlRenderProvenance() {
  const box = el("tl-provenance");
  box.innerHTML = "";
  if (!tl.manifest) {
    box.hidden = true;
    return;
  }
  box.hidden = false;
  const summary = tl.manifest.summary || {};

  const title = document.createElement("h4");
  title.textContent = t("tlProvTitle");
  box.appendChild(title);

  const head = document.createElement("p");
  head.className = "tl-prov-head";
  head.textContent = t("tlProvHead")
    .replace("{ai}", String(summary.ai_generated_clips ?? 0))
    .replace("{own}", String(summary.captured_or_uploaded_clips ?? 0));
  box.appendChild(head);

  if ((summary.models || []).length) {
    const models = document.createElement("p");
    models.className = "tl-prov-models";
    models.textContent = `${t("tlProvModels")}: ${summary.models.join(", ")}`;
    box.appendChild(models);
  }

  const verified = document.createElement("p");
  verified.className = `tl-prov-verified ${summary.all_sources_verified ? "ok" : "partial"}`;
  verified.textContent = summary.all_sources_verified
    ? t("tlProvAllVerified") : t("tlProvNotAllVerified");
  box.appendChild(verified);

  const list = document.createElement("ol");
  list.className = "tl-prov-list";
  for (const source of tl.manifest.sources || []) {
    const item = document.createElement("li");
    const when = document.createElement("span");
    when.className = "tl-prov-time";
    when.textContent = `${tlFormatSeconds(source.starts_at_s)} · ${tlFormatSeconds(source.duration_s)}`;
    const what = document.createElement("span");
    const provenance = source.provenance || {};
    what.textContent = source.source === "title"
      ? `${t("tlClipTitleCard")}: “${source.text || ""}”`
      : `${provenance.model || t("tlProvUnknownModel")}`
        + (provenance.ai_generated ? "" : ` · ${t("tlOwnFootage")}`);
    item.append(when, what);
    list.appendChild(item);
  }
  box.appendChild(list);

  const actions = document.createElement("div");
  actions.className = "tl-prov-actions";
  const verify = document.createElement("button");
  verify.type = "button";
  verify.className = "button small";
  verify.textContent = t("tlVerify");
  verify.title = t("tlVerifyHint");
  verify.addEventListener("click", () => tlVerify(verify));
  actions.appendChild(verify);
  box.appendChild(actions);
}

async function tlVerify(button) {
  button.disabled = true;
  try {
    const result = await api(`/sequences/${tl.id}/verify`, { method: "POST" });
    const ok = result.found && result.matches_stored;
    toast(ok ? t("tlVerifyOk") : t("tlVerifyMismatch"), !ok);
  } catch (err) {
    toast(err.message, true);
  } finally {
    button.disabled = false;
  }
}

function tlUpdateHeader() {
  el("tl-total").textContent = t("tlTotal")
    .replace("{duration}", tlFormatSeconds(tlTotalLength()))
    .replace("{clips}", String(tl.clips.length));
  el("tl-dirty").hidden = !tl.dirty;
  el("tl-render-button").disabled = !tl.clips.length || tl.status === "rendering";
  el("tl-undo").disabled = !tl.undo.length;
  el("tl-redo").disabled = !tl.redo.length;
  el("tl-preview-play").disabled = !tl.clips.length;
}

/* ---------- Uploads: bringing your own footage in ---------- */

async function tlUpload(input, path, statusKey) {
  const file = input.files && input.files[0];
  if (!file) return;
  const status = el("tl-status");
  status.classList.remove("error");
  status.innerHTML = `<span class="spinner" aria-hidden="true"></span>${t(statusKey)}`;
  status.hidden = false;
  const form = new FormData();
  form.append("file", file);
  try {
    // Not through api(): that helper sets Content-Type: application/json,
    // which would strip the multipart boundary the upload needs.
    const resp = await fetch(path, {
      method: "POST",
      headers: { "X-Workspace-Id": workspaceId() },
      body: form,
    });
    const body = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(body.detail || t("tlUploadFailed"));
    status.hidden = true;
    toast(t("tlUploaded"));
    await tlLoadPool();
  } catch (err) {
    status.classList.add("error");
    status.textContent = err.message;
  } finally {
    input.value = "";
  }
}

/* ---------- Assisted cut ---------- */

async function tlAutoCut() {
  const brief = el("tl-auto-brief").value.trim();
  if (!brief) {
    el("tl-auto-brief").focus();
    return;
  }
  const button = el("tl-auto-run");
  const status = el("tl-status");
  button.disabled = true;
  status.classList.remove("error");
  status.innerHTML = `<span class="spinner" aria-hidden="true"></span>${t("tlAutoRunning")}`;
  status.hidden = false;
  try {
    const sequence = await api("/sequences/auto", {
      method: "POST",
      body: JSON.stringify({
        brief,
        target_seconds: Number(el("tl-auto-seconds").value) || 30,
        aspect_ratio: tl.aspectRatio,
      }),
    });
    status.hidden = true;
    await tlLoadPool();
    tlAdoptSequence(sequence);
    el("tl-auto-row").hidden = true;
    toast(sequence.dropped_clips
      ? t("tlAutoDoneWithDrops").replace("{n}", String(sequence.dropped_clips))
      : t("tlAutoDone"));
  } catch (err) {
    status.classList.add("error");
    status.textContent = err.message;
  } finally {
    button.disabled = false;
  }
}

/* ---------- Views ---------- */

function tlReset() {
  clearTimeout(tl.pollTimer);
  tlPreviewStop();
  Object.assign(tl, {
    id: null, name: "", aspectRatio: "16:9", resolution: "720p",
    clips: [], audioTracks: [],
    status: "draft", videoId: null, manifest: null, duration: null,
    selected: null, dirty: false, undo: [], redo: [],
  });
  preview.at = 0;
  el("tl-name").value = "";
  el("tl-aspect").value = "16:9";
  el("tl-resolution").value = "720p";
  tlPreviewAspect();
  el("tl-status").hidden = true;
  el("tl-result").hidden = true;
  el("tl-provenance").hidden = true;
  el("tl-auto-row").hidden = true;
  tlRenderStrip();
  tlRenderInspector();
  tlRenderAudio();
}

function showTimelineView({ keepState = false } = {}) {
  state.selectedId = null;
  renderCharacterList();
  hideScenesView();
  hideStudioView();
  hideAudioView();
  hideVideoView();
  hideScriptView();
  hideCanvasView();
  hideCanvasTemplatesView();
  hideTimelineListView();
  setActiveNavGroup("timeline");
  setActiveNavSubitem("timeline", "new");
  el("detail-placeholder").hidden = true;
  el("detail-content").hidden = true;
  el("timeline-view").hidden = false;
  if (!keepState) tlReset();
  tlPreviewAspect();
  tlPaintPreview();
  tlLoadPool().catch(() => {});
}

function hideTimelineView() {
  el("timeline-view").hidden = true;
}

function showTimelineListView() {
  state.selectedId = null;
  renderCharacterList();
  hideScenesView();
  hideStudioView();
  hideAudioView();
  hideVideoView();
  hideScriptView();
  hideCanvasView();
  hideCanvasTemplatesView();
  hideTimelineView();
  setActiveNavGroup("timeline");
  setActiveNavSubitem("timeline", "list");
  el("detail-placeholder").hidden = true;
  el("detail-content").hidden = true;
  el("timeline-list-view").hidden = false;
  tlLoadSequences();
}

function hideTimelineListView() {
  el("timeline-list-view").hidden = true;
}

async function tlLoadSequences() {
  try {
    tlRenderSequences(await api("/sequences"));
  } catch (err) {
    toast(err.message, true);
  }
}

function tlRenderSequences(sequences) {
  const grid = el("tl-sequence-grid");
  grid.innerHTML = "";
  el("tl-sequence-empty").hidden = sequences.length > 0;
  for (const sequence of sequences) {
    const card = document.createElement("div");
    card.className = "asset-card";
    const body = document.createElement("div");
    body.className = "asset-body";

    const name = document.createElement("p");
    name.className = "asset-prompt";
    name.textContent = sequence.name;
    body.appendChild(name);

    const facts = document.createElement("p");
    facts.className = "tl-sequence-facts";
    facts.textContent = `${(sequence.clips || []).length} ${t("tlClipsWord")} · ${sequence.aspect_ratio}`
      + (sequence.duration ? ` · ${tlFormatSeconds(sequence.duration)}` : "")
      + ` · ${t(`tlStatus_${sequence.status}`)}`;
    body.appendChild(facts);

    const meta = document.createElement("div");
    meta.className = "asset-meta";
    const time = document.createElement("span");
    time.textContent = formatTimestamp(sequence.updated_at);
    meta.appendChild(time);

    const actions = document.createElement("span");
    actions.className = "asset-actions";
    const open = document.createElement("button");
    open.type = "button";
    open.className = "asset-details-btn";
    open.textContent = t("tlOpen");
    open.addEventListener("click", () => tlOpenSequence(sequence.id));
    actions.appendChild(open);
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "asset-delete";
    remove.textContent = t("tlDelete");
    remove.addEventListener("click", async () => {
      if (!confirm(t("tlConfirmDelete"))) return;
      try {
        await api(`/sequences/${sequence.id}`, { method: "DELETE" });
        tlLoadSequences();
        toast(t("tlDeleted"));
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

async function tlOpenSequence(sequenceId) {
  try {
    showTimelineView({ keepState: true });
    await tlLoadPool();
    tlAdoptSequence(await api(`/sequences/${sequenceId}`));
    if (tl.status === "rendering") tlPollRender();
  } catch (err) {
    toast(err.message, true);
  }
}

function setupTimeline() {
  document.querySelectorAll('.nav-subitem[data-open="timeline"]').forEach((btn) => {
    btn.addEventListener("click", () => {
      if (btn.dataset.mode === "list") showTimelineListView();
      else showTimelineView();
    });
  });

  el("tl-name").addEventListener("input", (event) => {
    tl.name = event.target.value;
    tlMarkDirty();
  });
  el("tl-aspect").addEventListener("change", (event) => {
    tlPushUndo();
    tl.aspectRatio = event.target.value;
    tlPreviewAspect();
    tlMarkDirty();
  });
  el("tl-resolution").addEventListener("change", (event) => {
    tlPushUndo();
    tl.resolution = event.target.value;
    tlMarkDirty();
  });
  el("tl-undo").addEventListener("click", tlUndo);
  el("tl-redo").addEventListener("click", tlRedo);

  el("tl-preview-play").addEventListener("click", tlPreviewToggle);
  el("tl-scrubber").addEventListener("pointerdown", (event) => {
    const seek = (moveEvent) => {
      const box = el("tl-scrubber").getBoundingClientRect();
      tlPreviewSeek((moveEvent.clientX - box.left) / box.width);
    };
    seek(event);
    const move = (moveEvent) => seek(moveEvent);
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  });
  el("tl-save-button").addEventListener("click", tlSave);
  el("tl-render-button").addEventListener("click", tlRender);
  el("tl-new-button").addEventListener("click", tlReset);
  el("tl-add-title").addEventListener("click", tlAddTitleCard);

  el("tl-pool-search").addEventListener("input", (event) => {
    tl.poolSearch = event.target.value;
    tlRenderPool();
  });
  document.querySelectorAll(".tl-pool-filter").forEach((btn) => {
    btn.addEventListener("click", () => {
      tl.poolFilter = btn.dataset.filter;
      document.querySelectorAll(".tl-pool-filter")
        .forEach((other) => other.classList.toggle("active", other === btn));
      tlRenderPool();
    });
  });

  el("tl-upload-image").addEventListener("change", (event) =>
    tlUpload(event.target, "/uploads/image", "tlUploadingImage"));
  el("tl-upload-video").addEventListener("change", (event) =>
    tlUpload(event.target, "/uploads/video", "tlUploadingVideo"));
  el("tl-upload-music").addEventListener("change", async (event) => {
    const input = event.target;
    const file = input.files && input.files[0];
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    try {
      const resp = await fetch("/uploads/music", {
        method: "POST", headers: { "X-Workspace-Id": workspaceId() }, body: form,
      });
      const body = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(body.detail || t("tlUploadFailed"));
      tlAddAudioTrack(body.url, file.name, null);
      toast(t("tlUploaded"));
    } catch (err) {
      toast(err.message, true);
    } finally {
      input.value = "";
    }
  });

  el("tl-audio-add").addEventListener("click", () => {
    const select = el("tl-audio-select");
    const option = select.selectedOptions[0];
    if (option) tlAddAudioTrack(select.value, option.dataset.label, option.dataset.signed);
    select.value = "";
  });

  el("tl-auto-open").addEventListener("click", () => {
    const row = el("tl-auto-row");
    row.hidden = !row.hidden;
    if (!row.hidden) el("tl-auto-brief").focus();
  });
  el("tl-auto-run").addEventListener("click", tlAutoCut);

  el("tl-clip-left").addEventListener("click", () => tlMoveSelected(-1));
  el("tl-clip-right").addEventListener("click", () => tlMoveSelected(1));
  el("tl-clip-duplicate").addEventListener("click", tlDuplicateSelected);
  el("tl-clip-delete").addEventListener("click", tlRemoveSelected);

  // Keyboard is part of what makes an editor feel like one: arrows walk the
  // strip, Delete removes — and nothing fires while a field has focus.
  document.addEventListener("keydown", (event) => {
    if (el("timeline-view").hidden) return;
    // Undo works even from inside a field — that is where a mistyped duration
    // happens, and having to click away first would defeat the point.
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z") {
      event.preventDefault();
      if (event.shiftKey) tlRedo();
      else tlUndo();
      return;
    }
    if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) return;
    if (event.code === "Space") {
      event.preventDefault();
      tlPreviewToggle();
      return;
    }
    if (event.key === "ArrowLeft" && tl.selected !== null) {
      tl.selected = Math.max(0, tl.selected - 1);
      tlRenderStrip();
      tlRenderInspector();
    } else if (event.key === "ArrowRight" && tl.selected !== null) {
      tl.selected = Math.min(tl.clips.length - 1, tl.selected + 1);
      tlRenderStrip();
      tlRenderInspector();
    } else if (event.key === "Delete" || event.key === "Backspace") {
      tlRemoveSelected();
    }
  });

  // An unsaved cut is minutes of work that exists nowhere else yet.
  window.addEventListener("beforeunload", (event) => {
    if (!tl.dirty || el("timeline-view").hidden) return;
    event.preventDefault();
    event.returnValue = "";
  });
}

setupTimeline();
