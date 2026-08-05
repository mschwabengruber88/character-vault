"use strict";

const KEY_STORAGE = "cv_generate_api_key";

const el = (id) => document.getElementById(id);

/* ---------- i18n (English / German) ---------- */

const LANG_STORAGE = "cv_lang";

const TRANSLATIONS = {
  en: {
    provenanceNote: "Every asset stored on Backblaze B2 with a verified provenance manifest",
    apiKey: "API key",
    landingEyebrow: "Backblaze Generative AI Media Hackathon",
    landingTitle: "One character. Every medium. Always consistent.",
    landingSub: "Loomina turns a single character profile into a full library of images, scenes, voiceover and video — keeping the same face, style and identity across all of them. No model training, no LoRA.",
    landingCreate: "Create your first character",
    landingCtaNote: "Every asset is stored on your Backblaze B2 with a verifiable provenance manifest.",
    landingWhy: "Why it stands out",
    feat1Title: "Consistent identity — without LoRA",
    feat1Body: "The vault's own portraits become the reference. A character keeps the same face across every image, multi-character scene and video — no training, no fine-tuning, in seconds.",
    feat2Title: "One pipeline, end to end",
    feat2Body: "Profile → image modes (single, variation set, photoshoot, story) → studio backgrounds & photo art → voiceover → video. The whole creative chain in one place.",
    feat3Title: "Provenance & AI disclosure built in",
    feat3Body: "Every asset carries a verifiable manifest. Choose a visible “AI” watermark or invisible embedded metadata — transparency by design, not an afterthought.",
    feat4Title: "Waste-aware by design",
    feat4Body: "Draft and final quality tiers, live cost estimates before every run, batch generation with a stop button, and a duplicate-request guard. Spend credits on keepers, not misfires.",
    landingHow: "How it works",
    step1Title: "Build a character",
    step1Body: "Give them a reference image (generated or your own photo), personality, a fixed voice, a seed and a purpose — an extended CV.",
    step2Title: "Generate in any mode",
    step2Body: "One portrait, a 10-shot variation set, a 100-frame photoshoot, or a full story series — the prompt builder assembles a strong prompt from optional fields.",
    step3Title: "Bring them to life",
    step3Body: "Add voiceover, compose multi-character scenes, or animate a portrait into a short video — identity held throughout.",
    charactersHeading: "Characters",
    new: "New",
    noCharacters: "No characters yet. Create your first one.",
    navGroupBild: "Images",
    navBildSingle: "Single image",
    navBildVariation: "Variation set",
    navBildPhotoshoot: "Photoshoot",
    navBildStory: "Story series",
    navBildScene: "Scene (multi-character)",
    navBildPhotoArt: "Photo art",
    navBildBackground: "Background / scene plate",
    navGroupVideo: "Video",
    navVideoCharacter: "Animate a character",
    navVideoScene: "Scene (multi-character)",
    navVideoMotionComic: "Motion comic",
    navGroupTon: "Audio",
    navTonSingle: "Single voice",
    navTonDialogue: "Dialogue",
    imagesTitle: "Images",
    imagesDesc: "Generate portraits, variation sets, photoshoots or story panels for one character — or bring several together in one scene. Pick who's in the frame below.",
    pickOneCharacter: "Pick the character — their stored portraits keep the identity consistent:",
    pickSceneCharacters: "Pick the characters for the scene (2–4) — Nano Banana composes them together:",
    optScene: "Scene — multiple characters together",
    phScenePrompt: "Describe the scene, e.g. 'the two of them talking by the classroom window, manga panel'",
    hintScene: "Nano Banana multi-character composition — pick 2–4 characters above.",
    needPortraitForImages: "Create at least one character with a portrait first.",
    toastPickCharacterFirst: "Pick a character first.",
    toastPickTwoCharacters: "Pick at least two characters.",
    toastPickAtMostFour: "Pick at most four characters.",
    toastDescribeSceneFirst: "Describe the scene first.",
    generatingScene: "Composing the scene with Nano Banana… 20–60 seconds.",
    assetsEmptyImages: "No assets yet — generate a portrait above.",
    studioTitle: "Studio",
    studioDesc: "Generate images without a character — free artistic photo art like Midjourney, or empty background/scene plates. Same prompt builder, no identity lock.",
    audioTitle: "Audio",
    audioDesc: "Turn a script into spoken audio — narration, voiceover, dialogue. Pick a voice from the catalog.",
    videoTitle: "Video",
    videoDesc: "Bring a character to life — animate one of their portraits into a short clip (identity held via image-to-video), or generate video straight from a prompt.",
    wsGateTitle: "Your workspace",
    wsGateIntro: "Loomina is multi-tenant: your characters, images, audio and videos live in your own private workspace. Create one, or open an existing workspace with its token.",
    wsNameLabel: "New workspace name",
    wsCreate: "Create workspace",
    wsOr: "or",
    wsTokenLabel: "Open with a workspace token",
    wsOpen: "Open workspace",
    wsInfoTitle: "Workspace",
    wsTokenNote: "Share this token to give someone access to this exact workspace, or use it to open it on another device. Keep it private otherwise.",
    wsCopy: "Copy",
    wsSwitch: "Switch workspace",
    wsClose: "Close",
    wsNeedName: "Give your workspace a name.",
    wsBadToken: "That workspace token was not found.",
    wsError: "Could not create the workspace. Try again.",
    wsCopied: "Workspace token copied.",
    wsRecent: "Continue in a workspace",
    budgetLeft: "credits left",
    budgetGone: "credits used up",
    budgetTitle: "Free generation credits in this workspace — an image costs 1, a video 20.",
    navScript: "Idea → Script",
    scriptTitle: "Idea → Script",
    scriptDesc: "Describe an idea in a sentence and get a ready-to-shoot script. A story script drops straight into the Story image mode — one line becomes one panel.",
    navGroupCanvas: "Canvas",
    navCanvasNew: "New template",
    navCanvasTemplates: "My templates",
    navCanvasVideo: "Video overlay",
    canvasVideoLabel: "Video",
    canvasVideoPick: "Pick a finished video…",
    canvasLoadingPoster: "Loading the video's first frame…",
    canvasApplyOverlay: "Apply overlay to video",
    canvasOverlayApplying: "Burning the overlay onto the clip…",
    canvasOverlayNoVideo: "Pick a video first.",
    toastOverlayDone: "Overlay video created — find it in the Video tab.",
    canvasTitle: "Canvas",
    canvasDesc: "Bring text and shapes onto your generated images — marketing overlays, manga pages, and more.",
    canvasBackgroundLabel: "Background",
    canvasAddText: "+ Text",
    canvasAddRect: "+ Rectangle",
    canvasAddCircle: "+ Circle",
    canvasAddLine: "+ Line",
    canvasAddArrow: "+ Arrow",
    canvasDuplicate: "Duplicate",
    canvasDelete: "Delete",
    canvasVisibleBadge: "Stamp a visible “✦ AI” badge onto the result",
    canvasExportBtn: "Export",
    canvasNoBackground: "Blank canvas",
    canvasSceneLabel: "Scene",
    canvasStudioLabel: "Studio",
    canvasExporting: "Exporting…",
    toastCanvasExported: "Saved to your Studio gallery.",
    canvasAddBubble: "+ Speech bubble",
    canvasAddSoundword: "+ Soundword",
    canvasEditHint: "Double-click a speech bubble or soundword to edit its text.",
    canvasEditTextPrompt: "Edit text",
    canvasLayoutLabel: "Layout",
    canvasLayoutNone: "Single background",
    canvasLayout2x2: "Manga page — 2×2 panels",
    canvasLayoutRow3: "Manga page — 3 panels in a row",
    canvasLayoutStrip4: "Manga page — 4-panel strip",
    canvasPanelHintFilling: "Choose a background below to fill panel {n} — click another panel to fill it instead.",
    canvasStickersTitle: "Stickers",
    canvasSaveTemplate: "Save as template",
    canvasSaveTemplateChanges: "Save changes",
    canvasTemplateNamePrompt: "Template name",
    canvasTemplateNameConfirm: "Save",
    canvasEditingTemplate: "Editing: {name}",
    toastTemplateSaved: "Template saved.",
    toastTemplateDeleted: "Template deleted.",
    canvasTemplatesTitle: "My templates",
    canvasTemplatesDesc: "Reopen a saved layout and swap in different images.",
    canvasTemplatesEmpty: "No templates saved yet — build a layout and save it from the editor.",
    canvasTemplateOpen: "Open",
    canvasTemplateDelete: "Delete",
    canvasConfirmDeleteTemplate: "Delete this template?",
    scriptIdeaPh: "Describe your idea, e.g. 'a shy robot learns to dance at a city festival'",
    scriptFormat: "Format",
    fmtStory: "Story — one line per panel",
    fmtVideo: "Video — scenes + narration",
    fmtManga: "Manga — panels + dialogue",
    fmtDialogue: "Dialogue — spoken lines",
    scriptLength: "Length",
    lenShort: "Short",
    lenMedium: "Medium",
    lenLong: "Long",
    scriptCastHint: "Optionally include your characters by name:",
    scriptGenerate: "Generate script",
    scriptResult: "Script",
    scriptSaved: "Saved scripts",
    scriptNone: "No scripts yet — describe an idea above.",
    scriptGenerating: "Writing your script…",
    scriptCopied: "Script copied.",
    phName: "Name",
    phDescription: "Appearance / short description",
    phPersonality: "Personality & traits — e.g. 'shy, doesn't speak directly to women' or 'strong, confident, charismatic'",
    phPurpose: "Purpose / use-case (optional)",
    phSeed: "Seed (optional, for reproducibility)",
    phPersonalityShort: "Personality & traits",
    phPurposeShort: "Purpose / use-case",
    phSeedShort: "Seed",
    refPhotoLabel: "Reference photo (optional — create from your own image)",
    create: "Create",
    cancel: "Cancel",
    save: "Save",
    uploadPhoto: "Upload photo",
    editProfile: "Edit profile",
    delete: "Delete",
    imgGenHint: "Genblaze → Backblaze B2 · identity, personality & seed from the profile carry into every frame",
    modeLabel: "Mode",
    optSingle: "Single image",
    optVariation: "Variation set — different outfits/poses/backgrounds",
    optPhotoshoot: "Photoshoot — same outfit & setting, many shots",
    optStory: "Story series — one panel per script line",
    howMany: "How many",
    composerTitle: "Prompt builder",
    composerSub: "optional — style, light, angle…",
    clearFields: "Clear fields",
    modelLabel: "Model",
    identityKeep: "Keep character identity",
    identityRefNote: " stored portrait(s) used as reference · ",
    qualityLegend: "Quality",
    qualityDraft: "<b>Draft</b> — ~$0.01 per image, for finding the right motif",
    qualityFinal: "<b>Final</b> — ~$0.17 per image, full quality for the keeper",
    disclosureLegend: "AI disclosure",
    disclInvisible: "<b>Invisible</b> — provenance manifest embedded in the file",
    disclVisible: "<b>Visible</b> — “✦ AI” watermark badge on the image",
    stop: "Stop",
    ttsHint: "Genblaze TTS → Backblaze B2",
    voiceLabel: "Voice",
    assetsHeading: "Assets",
    detailsBtn: "Details",
    detailsTitle: "Generation details",
    portraitPickTitle: "Choose the reference portrait",
    portraitPickBody: "Four options are being generated. The one you pick becomes this character's reference — the others are discarded.",
    portraitPickKeepAll: "Keep all of them",
    portraitPickClose: "Close",
    portraitPickUse: "Use this one",
    portraitPickWaiting: "Generating four options…",
    portraitPickReady: "Pick the one you want to keep.",
    portraitPickNone: "No portrait could be generated. You can add one anytime from the Images tab.",
    portraitPickNeedDescription: "Add a short description to have portraits generated automatically.",
    portraitPickKept: "Portrait saved as the reference.",
    portraitPickKeptAll: "All options kept.",
    detailPrompt: "Prompt",
    detailScript: "Script",
    detailWho: "Character(s)",
    detailVoice: "Voice",
    detailModel: "Model",
    detailSeed: "Seed",
    detailQuality: "Quality",
    qualityFinalShort: "Final",
    qualityDraftShort: "Draft",
    detailDisclosure: "AI disclosure",
    detailDisclosureVisible: "Visible watermark",
    detailDisclosureInvisible: "Invisible manifest",
    detailManifest: "Provenance manifest",
    detailManifestYes: "Verified",
    detailManifestNo: "Not verified",
    detailCost: "Cost",
    detailDuration: "Duration",
    detailAspect: "Aspect ratio",
    detailType: "File type",
    detailHash: "SHA-256",
    detailHashCopied: "Hash copied.",
    detailCreated: "Created",
    copy: "Copy",
    assetsEmpty: "No assets yet — generate one in the Images tab.",
    filterAnyGender: "Any gender",
    filterFemale: "Female",
    filterMale: "Male",
    filterNeutral: "Neutral",
    filterAnyAge: "Any age",
    filterChild: "Child",
    filterYoung: "Young / teen",
    filterAdult: "Adult",
    filterMature: "Mature",
    genSceneBtn: "Generate scene",
    yourScenes: "Your scenes",
    scenesEmpty: "No scenes yet — pick characters and describe a scene above.",
    studioPhotoArt: "✦ Photo Art",
    studioBackground: "▤ Background / Scene",
    phStudioPrompt: "Describe the image, e.g. 'a lone lighthouse on a stormy cliff'",
    studioQualityDraft: "<b>Draft</b> — ~$0.01 per image",
    studioQualityFinal: "<b>Final</b> — ~$0.17 per image",
    genImageBtn: "Generate image",
    yourStudio: "Your studio images",
    studioEmpty: "Nothing here yet — pick a mode and generate.",
    phAudioText: "What should be spoken? e.g. 'In a world long forgotten, one traveller set out at dawn…'",
    genAudioBtn: "Generate audio",
    yourAudio: "Your audio",
    audioEmpty: "Nothing here yet — write a line and generate.",
    audioModeSingle: "Single voice",
    audioModeDialogue: "Dialogue — multiple characters",
    dialoguePick: "Pick the characters (2–6) — each speaks in their own fixed voice:",
    phDialogueScript: "Kaede: Hey Ren, can you help me with English?\nRen: Sure, let's start with this chapter.",
    dialogueHint: "One line per turn, format \"Name: line\" — spoken in order, each in the named character's fixed voice.",
    genDialogueBtn: "Generate dialogue",
    yourDialogues: "Your dialogues",
    dialogueEmpty: "No dialogues yet — pick characters and write a script above.",
    needVoiceForDialogue: "Give at least two characters a voice in their profile first.",
    dialogueLineFormat: "Couldn't read this line — use \"Name: line\": {line}",
    dialogueUnknownSpeaker: "\"{name}\" isn't one of the picked characters — check the spelling.",
    toastPickAtMostSix: "Pick at most six characters.",
    toastWriteScriptFirst: "Write the script first.",
    generatingDialogue: "Generating the dialogue… each line renders in its speaker's voice, then they're combined.",
    toastDialogueCreated: "Dialogue created.",
    characterLabel: "Character",
    videoSourceLabel: "Reference",
    videoSourceCharacter: "Single character",
    videoSourceScene: "Existing scene — multiple characters",
    videoSourceMotionComic: "Motion comic — panels + dialogue",
    motionComicHint: "No video model, no lip-sync risk — each panel's still scene image is shown for exactly as long as its own line takes to speak. Built for more than one character talking at once, since real animated lip-sync only ever works for one face per clip.",
    addPanel: "+ Add panel",
    removePanel: "Remove panel",
    phMotionComicLine: "What does this character say in this panel?",
    genMotionComicBtn: "Generate motion comic",
    generatingMotionComic: "Rendering panels and voice lines… usually a few seconds.",
    toastMotionComicCreated: "Motion comic created.",
    toastNeedTwoPanels: "Add at least two panels.",
    phMotionComicCaption: "Optional caption/CTA text burned into this panel, e.g. 'Visit us today!'",
    musicUploadLabel: "Background music (optional) — mixed quietly under the voice lines",
    musicClear: "Remove",
    uploadingMusic: "Uploading…",
    musicAttached: "Attached",
    sceneLabel: "Scene",
    videoNoScenes: "No scenes yet — create one in the Images tab first.",
    toastPickSceneFirst: "Pick a scene first.",
    phVideoPrompt: "Describe the motion, e.g. 'she turns her head and smiles, gentle camera push-in'",
    durationLabel: "Duration",
    dur5: "5 seconds",
    dur8: "8 seconds",
    dur10: "10 seconds",
    aspectLabel: "Aspect",
    asp169: "16:9 — landscape",
    asp916: "9:16 — vertical",
    asp11: "1:1 — square",
    videoRunHint: "Video generation runs on GMI Cloud and takes 1–4 minutes. It keeps running if you switch views.",
    genVideoBtn: "Generate video",
    yourVideos: "Your videos",
    videoEmpty: "No videos yet — pick a model and generate.",
    keyDialogTitle: "Owner key (optional)",
    keyDialogBody: "Generation is free for everyone, just rate-limited. Add the owner key only to lift the limits (unlimited generation). Stored only in this browser.",
    phKeyInput: "Owner key (optional)",
    // JS-set strings
    modePortraitBtn: "Generate portrait",
    modeVariationBtn: "Generate variation set",
    modePhotoshootBtn: "Run photoshoot",
    modeStoryBtn: "Generate story series",
    phSinglePrompt: "Describe the portrait, e.g. 'a weathered sea captain, oil painting style'",
    phVariationPrompt: "Describe the character, e.g. 'a young sorceress with silver hair'",
    phPhotoshootPrompt: "Describe the look & setting, e.g. 'in a beige trench coat, city street at dusk'",
    phStoryPrompt: "One line per panel:\nShe wakes at dawn.\nShe walks to the harbour.\nShe boards the ship.",
    hintVariation: "Each frame changes outfit, pose, background and lighting — same person throughout.",
    hintPhotoshoot: "Wardrobe, location and lighting stay locked — only the camera angle and expression change, like a real shoot.",
    hintStory: "One image per line of the script. The character stays consistent across every panel.",
    identityLocks: "this model locks facial identity",
    identityLoose: "loose likeness only — for locked identity pick an identity model",
    studioHintPhoto: "Free artistic image generation — like Midjourney or Grok. No character, no identity lock.",
    studioHintBg: "An empty environment/scene plate with no people — a backdrop you can reuse or drop a character into later.",
    videoHintChar: "Animates the chosen character's portrait as the first frame — their identity carries into the clip.",
    videoHintAudio: "Includes a generated audio track.",
    videoHintText: "No character needed — describe the whole shot.",
    videoRendering: "Rendering… 1–4 minutes.",
    toastPortraitSaved: "Portrait stored in the vault.",
    toastImageSaved: "Image stored in the vault.",
    toastAudioSaved: "Audio stored in the vault.",
    toastVideoSaved: "Video stored in the vault.",
    toastSceneCreated: "Scene created.",
    toastDeleted: "Deleted.",
    toastNeedKey: "Generation needs a valid API key.",
    toastDescribeFirst: "Describe the character first.",
    generatingImage: "Generating portrait… this usually takes 15–60 seconds. The asset is uploaded to Backblaze B2 with a provenance manifest.",
    generatingAudio: "Generating audio… 15–60 seconds. Stored on Backblaze B2 with a provenance manifest.",
    voicePickLabel: "Voice (fixed on the character)",
    voiceNone: "No voice yet — pick one",
    voiceNoneMatch: "No voices match these filters",
    voiceFixedNote: "Set at creation · change only in the profile",
    videoSpeechLabel: "✦ Let them speak (optional) — uses the character’s fixed voice",
    videoSpeechPh: "e.g. 'Hi. Nice to meet you.'",
    toastPickVoiceFirst: "Give this character a voice in its profile first.",
  },
  de: {
    provenanceNote: "Jedes Asset auf Backblaze B2 gespeichert – mit verifiziertem Herkunftsnachweis",
    apiKey: "API-Schlüssel",
    landingEyebrow: "Backblaze Generative AI Media Hackathon",
    landingTitle: "Ein Charakter. Jedes Medium. Immer konsistent.",
    landingSub: "Loomina macht aus einem einzigen Charakter-Profil eine ganze Bibliothek aus Bildern, Szenen, Sprachausgabe und Video – mit demselben Gesicht, Stil und derselben Identität über alles hinweg. Kein Modell-Training, kein LoRA.",
    landingCreate: "Ersten Charakter erstellen",
    landingCtaNote: "Jedes Asset landet auf deinem Backblaze B2 – mit verifizierbarem Herkunftsnachweis.",
    landingWhy: "Was es auszeichnet",
    feat1Title: "Konsistente Identität – ohne LoRA",
    feat1Body: "Die Porträts im Vault werden selbst zur Referenz. Ein Charakter behält dasselbe Gesicht über jedes Bild, jede Multi-Charakter-Szene und jedes Video – ohne Training, ohne Fine-Tuning, in Sekunden.",
    feat2Title: "Eine Pipeline, von Anfang bis Ende",
    feat2Body: "Profil → Bild-Modi (Einzeln, Variationsset, Fotoshooting, Story) → Studio-Hintergründe & Foto-Art → Sprachausgabe → Video. Die ganze Kreativkette an einem Ort.",
    feat3Title: "Herkunft & KI-Kennzeichnung eingebaut",
    feat3Body: "Jedes Asset trägt einen verifizierbaren Manifest-Nachweis. Wähle ein sichtbares „KI“-Wasserzeichen oder unsichtbare eingebettete Metadaten – Transparenz von Grund auf, nicht nachträglich.",
    feat4Title: "Von Grund auf sparsam",
    feat4Body: "Entwurfs- und Final-Qualitätsstufen, Live-Kostenschätzung vor jedem Lauf, Batch-Generierung mit Stopp-Knopf und Schutz vor Doppel-Anfragen. Credits für Treffer, nicht für Fehlversuche.",
    landingHow: "So funktioniert's",
    step1Title: "Charakter aufbauen",
    step1Body: "Gib ihm ein Referenzbild (generiert oder dein eigenes Foto), Persönlichkeit, eine feste Stimme, einen Seed und einen Verwendungszweck – ein erweiterter Lebenslauf.",
    step2Title: "In jedem Modus generieren",
    step2Body: "Ein Porträt, ein 10er-Variationsset, ein 100-Bilder-Fotoshooting oder eine ganze Bildergeschichte – der Prompt-Baukasten setzt aus optionalen Feldern einen starken Prompt zusammen.",
    step3Title: "Zum Leben erwecken",
    step3Body: "Sprachausgabe hinzufügen, Multi-Charakter-Szenen komponieren oder ein Porträt zu einem kurzen Video animieren – Identität bleibt durchgängig erhalten.",
    charactersHeading: "Charaktere",
    new: "Neu",
    noCharacters: "Noch keine Charaktere. Erstelle deinen ersten.",
    navGroupBild: "Bild",
    navBildSingle: "Einzelbild",
    navBildVariation: "Variation",
    navBildPhotoshoot: "Fotoshooting",
    navBildStory: "Story-Serie",
    navBildScene: "Szene (mehrere Charaktere)",
    navBildPhotoArt: "Foto-Art",
    navBildBackground: "Hintergrund / Szenenkulisse",
    navGroupVideo: "Video",
    navVideoCharacter: "Charakter animieren",
    navVideoScene: "Szene (mehrere Charaktere)",
    navVideoMotionComic: "Motion Comic",
    navGroupTon: "Ton",
    navTonSingle: "Einzelstimme",
    navTonDialogue: "Dialog",
    imagesTitle: "Bilder",
    imagesDesc: "Porträts, Variationssets, Fotoshootings oder Story-Panels für einen Charakter generieren – oder mehrere in einer Szene zusammenbringen. Wähle unten, wer im Bild ist.",
    pickOneCharacter: "Wähle den Charakter — seine gespeicherten Porträts halten die Identität konsistent:",
    pickSceneCharacters: "Wähle die Charaktere für die Szene (2–4) — Nano Banana setzt sie gemeinsam zusammen:",
    optScene: "Szene — mehrere Charaktere zusammen",
    phScenePrompt: "Beschreibe die Szene, z. B. 'die beiden unterhalten sich am Klassenzimmerfenster, Manga-Panel'",
    hintScene: "Nano-Banana-Multi-Charakter-Komposition — wähle oben 2–4 Charaktere.",
    needPortraitForImages: "Erstelle zuerst mindestens einen Charakter mit einem Porträt.",
    toastPickCharacterFirst: "Wähle zuerst einen Charakter.",
    toastPickTwoCharacters: "Wähle mindestens zwei Charaktere.",
    toastPickAtMostFour: "Wähle höchstens vier Charaktere.",
    toastDescribeSceneFirst: "Beschreibe zuerst die Szene.",
    generatingScene: "Szene wird mit Nano Banana komponiert … 20–60 Sekunden.",
    assetsEmptyImages: "Noch keine Assets – generiere oben ein Porträt.",
    studioTitle: "Studio",
    studioDesc: "Bilder ohne Charakter generieren – freie künstlerische Foto-Art wie bei Midjourney oder leere Hintergrund-/Szenen-Plates. Derselbe Prompt-Baukasten, ohne Identitäts-Lock.",
    audioTitle: "Audio",
    audioDesc: "Mach aus einem Skript gesprochenes Audio – Erzählung, Voiceover, Dialog. Wähle eine Stimme aus dem Katalog.",
    videoTitle: "Video",
    videoDesc: "Erwecke einen Charakter zum Leben – animiere eines seiner Porträts zu einem kurzen Clip (Identität via Image-to-Video gehalten) oder generiere Video direkt aus einem Prompt.",
    wsGateTitle: "Dein Workspace",
    wsGateIntro: "Loomina ist mandantenfähig: Deine Charaktere, Bilder, Audios und Videos liegen in deinem eigenen privaten Workspace. Erstelle einen – oder öffne einen bestehenden mit seinem Token.",
    wsNameLabel: "Name des neuen Workspace",
    wsCreate: "Workspace erstellen",
    wsOr: "oder",
    wsTokenLabel: "Mit Workspace-Token öffnen",
    wsOpen: "Workspace öffnen",
    wsInfoTitle: "Workspace",
    wsTokenNote: "Teile diesen Token, um jemandem Zugriff auf genau diesen Workspace zu geben, oder öffne ihn damit auf einem anderen Gerät. Ansonsten bitte privat halten.",
    wsCopy: "Kopieren",
    wsSwitch: "Workspace wechseln",
    wsClose: "Schließen",
    wsNeedName: "Gib deinem Workspace einen Namen.",
    wsBadToken: "Dieser Workspace-Token wurde nicht gefunden.",
    wsError: "Workspace konnte nicht erstellt werden. Bitte erneut versuchen.",
    wsCopied: "Workspace-Token kopiert.",
    wsRecent: "In einem Workspace weiter",
    budgetLeft: "Credits übrig",
    budgetGone: "Credits aufgebraucht",
    budgetTitle: "Freie Generierungs-Credits in diesem Workspace — ein Bild kostet 1, ein Video 20.",
    navScript: "Idee → Skript",
    scriptTitle: "Idee → Skript",
    scriptDesc: "Beschreibe eine Idee in einem Satz und erhalte ein drehfertiges Skript. Ein Story-Skript fließt direkt in den Story-Bildmodus – eine Zeile wird ein Panel.",
    navGroupCanvas: "Canvas",
    navCanvasNew: "Neue Vorlage",
    navCanvasTemplates: "Meine Vorlagen",
    navCanvasVideo: "Video-Overlay",
    canvasVideoLabel: "Video",
    canvasVideoPick: "Fertiges Video wählen…",
    canvasLoadingPoster: "Erstes Video-Frame wird geladen…",
    canvasApplyOverlay: "Overlay aufs Video anwenden",
    canvasOverlayApplying: "Overlay wird ins Video gebrannt…",
    canvasOverlayNoVideo: "Wähle zuerst ein Video.",
    toastOverlayDone: "Overlay-Video erstellt — zu finden im Video-Tab.",
    canvasTitle: "Canvas",
    canvasDesc: "Text und Formen auf deine generierten Bilder bringen – Marketing-Overlays, Manga-Seiten und mehr.",
    canvasBackgroundLabel: "Hintergrund",
    canvasAddText: "+ Text",
    canvasAddRect: "+ Rechteck",
    canvasAddCircle: "+ Kreis",
    canvasAddLine: "+ Linie",
    canvasAddArrow: "+ Pfeil",
    canvasDuplicate: "Duplizieren",
    canvasDelete: "Löschen",
    canvasVisibleBadge: "Sichtbares „✦ AI“-Badge auf das Ergebnis stempeln",
    canvasExportBtn: "Exportieren",
    canvasNoBackground: "Leere Fläche",
    canvasSceneLabel: "Szene",
    canvasStudioLabel: "Studio",
    canvasExporting: "Wird exportiert…",
    toastCanvasExported: "In deiner Studio-Galerie gespeichert.",
    canvasAddBubble: "+ Sprechblase",
    canvasAddSoundword: "+ Soundword",
    canvasEditHint: "Doppelklick auf eine Sprechblase oder ein Soundword bearbeitet den Text.",
    canvasEditTextPrompt: "Text bearbeiten",
    canvasLayoutLabel: "Layout",
    canvasLayoutNone: "Einzelner Hintergrund",
    canvasLayout2x2: "Manga-Seite – 2×2 Panels",
    canvasLayoutRow3: "Manga-Seite – 3 Panels nebeneinander",
    canvasLayoutStrip4: "Manga-Seite – 4er-Streifen",
    canvasPanelHintFilling: "Wähle unten einen Hintergrund für Panel {n} – klicke ein anderes Panel an, um dieses stattdessen zu füllen.",
    canvasStickersTitle: "Sticker",
    canvasSaveTemplate: "Als Vorlage speichern",
    canvasSaveTemplateChanges: "Änderungen speichern",
    canvasTemplateNamePrompt: "Name der Vorlage",
    canvasTemplateNameConfirm: "Speichern",
    canvasEditingTemplate: "Bearbeitet: {name}",
    toastTemplateSaved: "Vorlage gespeichert.",
    toastTemplateDeleted: "Vorlage gelöscht.",
    canvasTemplatesTitle: "Meine Vorlagen",
    canvasTemplatesDesc: "Öffne ein gespeichertes Layout und tausche die Bilder aus.",
    canvasTemplatesEmpty: "Noch keine Vorlagen gespeichert – baue ein Layout und speichere es im Editor.",
    canvasTemplateOpen: "Öffnen",
    canvasTemplateDelete: "Löschen",
    canvasConfirmDeleteTemplate: "Diese Vorlage löschen?",
    scriptIdeaPh: "Beschreibe deine Idee, z. B. 'ein schüchterner Roboter lernt auf einem Stadtfest tanzen'",
    scriptFormat: "Format",
    fmtStory: "Story – eine Zeile pro Panel",
    fmtVideo: "Video – Szenen + Erzählung",
    fmtManga: "Manga – Panels + Dialog",
    fmtDialogue: "Dialog – gesprochene Zeilen",
    scriptLength: "Länge",
    lenShort: "Kurz",
    lenMedium: "Mittel",
    lenLong: "Lang",
    scriptCastHint: "Optional deine Charaktere namentlich einbeziehen:",
    scriptGenerate: "Skript generieren",
    scriptResult: "Skript",
    scriptSaved: "Gespeicherte Skripte",
    scriptNone: "Noch keine Skripte – beschreibe oben eine Idee.",
    scriptGenerating: "Dein Skript wird geschrieben …",
    scriptCopied: "Skript kopiert.",
    phName: "Name",
    phDescription: "Aussehen / Kurzbeschreibung",
    phPersonality: "Persönlichkeit & Eigenschaften – z. B. 'schüchtern, spricht nicht direkt mit Frauen' oder 'stark, selbstbewusst, charismatisch'",
    phPurpose: "Verwendungszweck (optional)",
    phSeed: "Seed (optional, für Reproduzierbarkeit)",
    phPersonalityShort: "Persönlichkeit & Eigenschaften",
    phPurposeShort: "Verwendungszweck",
    phSeedShort: "Seed",
    refPhotoLabel: "Referenzfoto (optional – aus deinem eigenen Bild erstellen)",
    create: "Erstellen",
    cancel: "Abbrechen",
    save: "Speichern",
    uploadPhoto: "Foto hochladen",
    editProfile: "Profil bearbeiten",
    delete: "Löschen",
    imgGenHint: "Genblaze → Backblaze B2 · Identität, Persönlichkeit & Seed aus dem Profil fließen in jedes Bild",
    modeLabel: "Modus",
    optSingle: "Einzelbild",
    optVariation: "Variationsset – verschiedene Outfits/Posen/Hintergründe",
    optPhotoshoot: "Fotoshooting – gleiches Outfit & Setting, viele Aufnahmen",
    optStory: "Bildergeschichte – ein Panel pro Skriptzeile",
    howMany: "Anzahl",
    composerTitle: "Prompt-Baukasten",
    composerSub: "optional – Stil, Licht, Winkel …",
    clearFields: "Felder leeren",
    modelLabel: "Modell",
    identityKeep: "Charakter-Identität halten",
    identityRefNote: " gespeicherte(s) Porträt(s) als Referenz · ",
    qualityLegend: "Qualität",
    qualityDraft: "<b>Entwurf</b> – ~$0,01 pro Bild, zum Finden des Motivs",
    qualityFinal: "<b>Final</b> – ~$0,17 pro Bild, volle Qualität für den Keeper",
    disclosureLegend: "KI-Kennzeichnung",
    disclInvisible: "<b>Unsichtbar</b> – Herkunftsnachweis in der Datei eingebettet",
    disclVisible: "<b>Sichtbar</b> – „✦ AI“-Wasserzeichen auf dem Bild",
    stop: "Stopp",
    ttsHint: "Genblaze TTS → Backblaze B2",
    voiceLabel: "Stimme",
    assetsHeading: "Assets",
    detailsBtn: "Details",
    detailsTitle: "Generierungs-Details",
    portraitPickTitle: "Referenzbild auswählen",
    portraitPickBody: "Es werden vier Varianten erzeugt. Die ausgewählte wird zum Referenzbild dieser Figur — die anderen werden verworfen.",
    portraitPickKeepAll: "Alle behalten",
    portraitPickClose: "Schließen",
    portraitPickUse: "Diese verwenden",
    portraitPickWaiting: "Vier Varianten werden erzeugt…",
    portraitPickReady: "Wähle die Variante, die bleiben soll.",
    portraitPickNone: "Es konnte kein Bild erzeugt werden. Du kannst jederzeit im Bilder-Tab eines hinzufügen.",
    portraitPickNeedDescription: "Ergänze eine kurze Beschreibung, damit Bilder automatisch erzeugt werden.",
    portraitPickKept: "Bild als Referenz gespeichert.",
    portraitPickKeptAll: "Alle Varianten behalten.",
    detailPrompt: "Prompt",
    detailScript: "Skript",
    detailWho: "Charakter(e)",
    detailVoice: "Stimme",
    detailModel: "Modell",
    detailSeed: "Seed",
    detailQuality: "Qualität",
    qualityFinalShort: "Final",
    qualityDraftShort: "Entwurf",
    detailDisclosure: "KI-Kennzeichnung",
    detailDisclosureVisible: "Sichtbares Wasserzeichen",
    detailDisclosureInvisible: "Unsichtbares Manifest",
    detailManifest: "Herkunftsnachweis",
    detailManifestYes: "Verifiziert",
    detailManifestNo: "Nicht verifiziert",
    detailCost: "Kosten",
    detailDuration: "Dauer",
    detailAspect: "Seitenverhältnis",
    detailType: "Dateityp",
    detailHash: "SHA-256",
    detailHashCopied: "Hash kopiert.",
    detailCreated: "Erstellt",
    copy: "Kopieren",
    assetsEmpty: "Noch keine Assets – generiere eins im Bilder-Reiter.",
    filterAnyGender: "Beliebiges Geschlecht",
    filterFemale: "Weiblich",
    filterMale: "Männlich",
    filterNeutral: "Neutral",
    filterAnyAge: "Beliebiges Alter",
    filterChild: "Kind",
    filterYoung: "Jung / Teenager",
    filterAdult: "Erwachsen",
    filterMature: "Reif",
    genSceneBtn: "Szene generieren",
    yourScenes: "Deine Szenen",
    scenesEmpty: "Noch keine Szenen – wähle Charaktere und beschreibe oben eine Szene.",
    studioPhotoArt: "✦ Foto-Art",
    studioBackground: "▤ Hintergrund / Szene",
    phStudioPrompt: "Beschreibe das Bild, z. B. 'ein einsamer Leuchtturm auf einer stürmischen Klippe'",
    studioQualityDraft: "<b>Entwurf</b> – ~$0,01 pro Bild",
    studioQualityFinal: "<b>Final</b> – ~$0,17 pro Bild",
    genImageBtn: "Bild generieren",
    yourStudio: "Deine Studio-Bilder",
    studioEmpty: "Noch nichts hier – wähle einen Modus und generiere.",
    phAudioText: "Was soll gesprochen werden? z. B. 'In einer längst vergessenen Welt brach ein Reisender bei Tagesanbruch auf …'",
    genAudioBtn: "Audio generieren",
    yourAudio: "Deine Audios",
    audioEmpty: "Noch nichts hier – schreibe eine Zeile und generiere.",
    audioModeSingle: "Einzelstimme",
    audioModeDialogue: "Dialog — mehrere Charaktere",
    dialoguePick: "Wähle die Charaktere (2–6) — jeder spricht in seiner festen Stimme:",
    phDialogueScript: "Kaede: Hey Ren, kannst du mir bei Englisch helfen?\nRen: Klar, fangen wir mit diesem Kapitel an.",
    dialogueHint: "Eine Zeile pro Sprecher, Format \"Name: Zeile\" — wird der Reihe nach in der festen Stimme des jeweiligen Charakters gesprochen.",
    genDialogueBtn: "Dialog generieren",
    yourDialogues: "Deine Dialoge",
    dialogueEmpty: "Noch keine Dialoge – wähle Charaktere und schreibe oben ein Skript.",
    needVoiceForDialogue: "Gib zuerst mindestens zwei Charakteren im Profil eine Stimme.",
    dialogueLineFormat: "Diese Zeile konnte ich nicht lesen – nutze \"Name: Zeile\": {line}",
    dialogueUnknownSpeaker: "\"{name}\" ist keiner der ausgewählten Charaktere – prüfe die Schreibweise.",
    toastPickAtMostSix: "Wähle höchstens sechs Charaktere.",
    toastWriteScriptFirst: "Schreibe zuerst das Skript.",
    generatingDialogue: "Dialog wird generiert … jede Zeile entsteht in der Stimme ihres Sprechers, dann werden sie zusammengefügt.",
    toastDialogueCreated: "Dialog erstellt.",
    characterLabel: "Charakter",
    videoSourceLabel: "Referenz",
    videoSourceCharacter: "Einzelner Charakter",
    videoSourceScene: "Bestehende Szene — mehrere Charaktere",
    videoSourceMotionComic: "Motion Comic — Panels + Dialog",
    motionComicHint: "Kein Videomodell, kein Sync-Risiko — jedes Panel-Bild steht genau so lange, wie seine Zeile dauert. Gebaut für mehr als eine sprechende Person gleichzeitig, da echtes animiertes Lipsync immer nur für ein Gesicht pro Clip funktioniert.",
    addPanel: "+ Panel hinzufügen",
    removePanel: "Panel entfernen",
    phMotionComicLine: "Was sagt dieser Charakter in diesem Panel?",
    genMotionComicBtn: "Motion Comic generieren",
    generatingMotionComic: "Panels und Sprachzeilen werden gerendert … meist ein paar Sekunden.",
    toastMotionComicCreated: "Motion Comic erstellt.",
    toastNeedTwoPanels: "Füge mindestens zwei Panels hinzu.",
    phMotionComicCaption: "Optionaler Bildunterschrift-/CTA-Text, der in dieses Panel eingebrannt wird, z. B. 'Jetzt vorbeischauen!'",
    musicUploadLabel: "Hintergrundmusik (optional) — läuft leise unter den Sprachzeilen",
    musicClear: "Entfernen",
    uploadingMusic: "Wird hochgeladen …",
    musicAttached: "Angehängt",
    sceneLabel: "Szene",
    videoNoScenes: "Noch keine Szenen – erstelle zuerst eine im Bilder-Reiter.",
    toastPickSceneFirst: "Wähle zuerst eine Szene.",
    phVideoPrompt: "Beschreibe die Bewegung, z. B. 'sie dreht den Kopf und lächelt, sanfte Kamerafahrt nach vorn'",
    durationLabel: "Dauer",
    dur5: "5 Sekunden",
    dur8: "8 Sekunden",
    dur10: "10 Sekunden",
    aspectLabel: "Format",
    asp169: "16:9 – Querformat",
    asp916: "9:16 – Hochformat",
    asp11: "1:1 – Quadratisch",
    videoRunHint: "Video-Generierung läuft auf GMI Cloud und dauert 1–4 Minuten. Sie läuft weiter, wenn du die Ansicht wechselst.",
    genVideoBtn: "Video generieren",
    yourVideos: "Deine Videos",
    videoEmpty: "Noch keine Videos – wähle ein Modell und generiere.",
    keyDialogTitle: "Owner-Schlüssel (optional)",
    keyDialogBody: "Generierung ist für alle kostenlos, nur rate-limitiert. Der Owner-Schlüssel hebt die Limits auf (unbegrenzt). Nur in diesem Browser gespeichert.",
    phKeyInput: "Owner-Schlüssel (optional)",
    // JS-set strings
    modePortraitBtn: "Porträt generieren",
    modeVariationBtn: "Variationsset generieren",
    modePhotoshootBtn: "Fotoshooting starten",
    modeStoryBtn: "Bildergeschichte generieren",
    phSinglePrompt: "Beschreibe das Porträt, z. B. 'ein wettergegerbter Seekapitän, Ölgemälde-Stil'",
    phVariationPrompt: "Beschreibe den Charakter, z. B. 'eine junge Zauberin mit silbernem Haar'",
    phPhotoshootPrompt: "Beschreibe Look & Setting, z. B. 'in einem beigen Trenchcoat, Stadtstraße in der Dämmerung'",
    phStoryPrompt: "Eine Zeile pro Panel:\nSie erwacht bei Tagesanbruch.\nSie geht zum Hafen.\nSie geht an Bord des Schiffs.",
    hintVariation: "Jedes Bild ändert Outfit, Pose, Hintergrund und Licht – durchgängig dieselbe Person.",
    hintPhotoshoot: "Garderobe, Ort und Licht bleiben fixiert – nur Kamerawinkel und Ausdruck ändern sich, wie bei einem echten Shooting.",
    hintStory: "Ein Bild pro Skriptzeile. Der Charakter bleibt über alle Panels konsistent.",
    identityLocks: "dieses Modell fixiert die Gesichtsidentität",
    identityLoose: "nur lose Ähnlichkeit – für fixierte Identität ein Identity-Modell wählen",
    studioHintPhoto: "Freie künstlerische Bildgenerierung – wie Midjourney oder Grok. Kein Charakter, kein Identitäts-Lock.",
    studioHintBg: "Eine leere Umgebungs-/Szenen-Plate ohne Personen – ein Hintergrund zum Wiederverwenden oder für einen späteren Charakter.",
    videoHintChar: "Animiert das Porträt des gewählten Charakters als ersten Frame – seine Identität überträgt sich in den Clip.",
    videoHintAudio: "Enthält eine generierte Tonspur.",
    videoHintText: "Kein Charakter nötig – beschreibe die ganze Aufnahme.",
    videoRendering: "Rendern … 1–4 Minuten.",
    toastPortraitSaved: "Porträt im Vault gespeichert.",
    toastImageSaved: "Bild im Vault gespeichert.",
    toastAudioSaved: "Audio im Vault gespeichert.",
    toastVideoSaved: "Video im Vault gespeichert.",
    toastSceneCreated: "Szene erstellt.",
    toastDeleted: "Gelöscht.",
    toastNeedKey: "Generierung braucht einen gültigen API-Schlüssel.",
    toastDescribeFirst: "Beschreibe zuerst den Charakter.",
    generatingImage: "Porträt wird generiert … dauert meist 15–60 Sekunden. Das Asset wird mit Herkunftsnachweis auf Backblaze B2 hochgeladen.",
    generatingAudio: "Audio wird generiert … 15–60 Sekunden. Auf Backblaze B2 mit Herkunftsnachweis gespeichert.",
    voicePickLabel: "Stimme (fest am Charakter)",
    voiceNone: "Noch keine Stimme – wähle eine",
    voiceNoneMatch: "Keine Stimme passt zu diesen Filtern",
    voiceFixedNote: "Bei Erstellung gesetzt · nur im Profil änderbar",
    videoSpeechLabel: "✦ Lass sie sprechen (optional) – nutzt die feste Stimme des Charakters",
    videoSpeechPh: "z. B. 'Hi. Nice to meet you.'",
    toastPickVoiceFirst: "Gib diesem Charakter zuerst im Profil eine Stimme.",
  },
};

function initialLang() {
  const saved = localStorage.getItem(LANG_STORAGE);
  if (saved === "en" || saved === "de") return saved;
  return (navigator.language || "en").toLowerCase().startsWith("de") ? "de" : "en";
}

let lang = initialLang();

function t(key) {
  return (TRANSLATIONS[lang] && TRANSLATIONS[lang][key]) || TRANSLATIONS.en[key] || key;
}

function applyI18n() {
  document.documentElement.lang = lang;
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = t(node.getAttribute("data-i18n"));
  });
  document.querySelectorAll("[data-i18n-ph]").forEach((node) => {
    node.setAttribute("placeholder", t(node.getAttribute("data-i18n-ph")));
  });
  document.querySelectorAll("[data-i18n-html]").forEach((node) => {
    node.innerHTML = t(node.getAttribute("data-i18n-html"));
  });
  const toggle = el("lang-toggle");
  if (toggle) toggle.textContent = lang === "de" ? "EN" : "DE";
}

function setLang(next) {
  lang = next;
  localStorage.setItem(LANG_STORAGE, next);
  applyI18n();
  // Re-render the strings that JS sets dynamically (not covered by data-i18n).
  try { updateModeUI(); } catch {}
  try { applyModelUI(); } catch {}
  try { applyStudioModelUI(); } catch {}
  try { if (studioComposer) setStudioMode(studioMode); } catch {}
  try { applyVideoModelUI(); } catch {}
  try { updateVoiceNote(); } catch {}
}

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
    headers: { "Content-Type": "application/json", "X-Workspace-Id": workspaceId(), ...(headers || {}) },
  });
  // Keep the credit counter honest after anything that spends — including a
  // refusal, where the 429 itself is what tells the visitor they are out.
  const method = (rest.method || "GET").toUpperCase();
  if (method !== "GET" && SPENDING_PATH.test(path)) refreshBudget();
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

/* ---------- Workspaces (multitenancy) ---------- */

const WORKSPACE_STORAGE = "cv_workspace_id";
const WORKSPACE_COOKIE = "cv_ws";        // backup of the active id
const RECENT_STORAGE = "cv_workspaces";  // remembered [{id,name}]

function setCookie(name, value, days = 365) {
  try {
    const exp = new Date(Date.now() + days * 864e5).toUTCString();
    document.cookie = `${name}=${encodeURIComponent(value)}; expires=${exp}; path=/; SameSite=Lax`;
  } catch {}
}
function getCookie(name) {
  return document.cookie.split("; ").reduce((acc, c) => {
    const i = c.indexOf("=");
    return c.slice(0, i) === name ? decodeURIComponent(c.slice(i + 1)) : acc;
  }, "");
}

// Active workspace survives a localStorage-only clear via the cookie backup.
function workspaceId() {
  return localStorage.getItem(WORKSPACE_STORAGE) || getCookie(WORKSPACE_COOKIE) || "";
}

function recentWorkspaces() {
  try { return JSON.parse(localStorage.getItem(RECENT_STORAGE) || getCookie(RECENT_STORAGE) || "[]"); }
  catch { return []; }
}
function rememberWorkspace(ws) {
  const list = [{ id: ws.id, name: ws.name }, ...recentWorkspaces().filter((w) => w.id !== ws.id)].slice(0, 6);
  const json = JSON.stringify(list);
  localStorage.setItem(RECENT_STORAGE, json);
  setCookie(RECENT_STORAGE, json);
}
function forgetWorkspace(id) {
  const json = JSON.stringify(recentWorkspaces().filter((w) => w.id !== id));
  localStorage.setItem(RECENT_STORAGE, json);
  setCookie(RECENT_STORAGE, json);
}

async function validateWorkspace(id) {
  try {
    const resp = await fetch("/workspaces/current", { headers: { "X-Workspace-Id": id } });
    return resp.ok ? await resp.json() : null;
  } catch {
    return null;
  }
}

let workspaceResolve = null;

function ensureWorkspace() {
  return (async () => {
    const id = workspaceId();
    if (id) {
      const ws = await validateWorkspace(id);
      if (ws) { adoptWorkspace(ws); return; }   // valid → adopt (also remembers it)
      localStorage.removeItem(WORKSPACE_STORAGE);
      setCookie(WORKSPACE_COOKIE, "", -1);
    }
    await new Promise((resolve) => {
      workspaceResolve = resolve;
      el("ws-gate-error").hidden = true;
      el("ws-name").value = "";
      el("ws-token").value = "";
      renderRecentWorkspaces();
      el("workspace-gate").showModal();
    });
  })();
}

function renderRecentWorkspaces() {
  const wrap = el("ws-recent");
  const box = el("ws-recent-list");
  const list = recentWorkspaces();
  box.innerHTML = "";
  if (!list.length) { wrap.hidden = true; return; }
  for (const w of list) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ws-recent-chip";
    btn.textContent = `◈ ${w.name}`;
    btn.addEventListener("click", async () => {
      const ws = await validateWorkspace(w.id);
      if (ws) { adoptWorkspace(ws); }
      else { forgetWorkspace(w.id); renderRecentWorkspaces(); gateError("wsBadToken"); }
    });
    box.appendChild(btn);
  }
  wrap.hidden = false;
}

function gateError(key) {
  const node = el("ws-gate-error");
  node.textContent = t(key);
  node.hidden = false;
}

function adoptWorkspace(ws) {
  localStorage.setItem(WORKSPACE_STORAGE, ws.id);
  setCookie(WORKSPACE_COOKIE, ws.id);
  rememberWorkspace(ws);
  setWorkspaceChip(ws);
  if (el("workspace-gate").open) el("workspace-gate").close();
  if (workspaceResolve) { workspaceResolve(); workspaceResolve = null; }
}

function setWorkspaceChip(ws) {
  const chip = el("workspace-chip");
  chip.textContent = `◈ ${ws.name}`;
  chip.dataset.token = ws.id;
  chip.dataset.name = ws.name;
  chip.hidden = false;
  setBudgetChip(ws);
}

/* ---------- Free-credit counter ----------
 * Generation is keyless but each workspace has a fixed budget, so the count
 * has to be visible — otherwise a visitor hits a 429 with no warning. The
 * owner key lifts the budget, so the chip stays hidden while it is set.
 */

function setBudgetChip(ws) {
  const chip = el("budget-chip");
  if (!chip) return;
  const quota = Number(ws?.units_quota ?? 0);
  const left = Number(ws?.units_remaining ?? 0);
  if (!quota || apiKey()) { chip.hidden = true; return; }
  chip.textContent = left > 0 ? `✦ ${left} ${t("budgetLeft")}` : `✦ ${t("budgetGone")}`;
  chip.title = t("budgetTitle");
  chip.classList.toggle("budget-chip-low", left > 0 && left <= 5);
  chip.classList.toggle("budget-chip-empty", left <= 0);
  chip.hidden = false;
}

async function refreshBudget() {
  const id = workspaceId();
  if (!id) return;
  const ws = await validateWorkspace(id);
  if (ws) setBudgetChip(ws);
}

// Paths whose POSTs actually spend credits. A plain character or template
// save costs nothing, so it must not trigger a needless round-trip.
const SPENDING_PATH = /\/(generate|reference)|^\/(videos|scenes|studio|audio|scripts)\b/;

function setupWorkspace() {
  el("ws-create").addEventListener("click", async () => {
    const name = el("ws-name").value.trim();
    if (!name) { gateError("wsNeedName"); return; }
    try {
      const resp = await fetch("/workspaces", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      if (!resp.ok) throw new Error();
      adoptWorkspace(await resp.json());
    } catch { gateError("wsError"); }
  });

  el("ws-open").addEventListener("click", async () => {
    const token = el("ws-token").value.trim();
    if (!token) { gateError("wsBadToken"); return; }
    const ws = await validateWorkspace(token);
    if (!ws) { gateError("wsBadToken"); return; }
    adoptWorkspace(ws);
  });

  // The gate is mandatory — don't let Esc dismiss it without a workspace.
  el("workspace-gate").addEventListener("cancel", (event) => {
    if (!workspaceId()) event.preventDefault();
  });

  el("workspace-chip").addEventListener("click", () => {
    el("ws-info-name").textContent = el("workspace-chip").dataset.name || "";
    el("ws-info-token").value = el("workspace-chip").dataset.token || "";
    el("workspace-info").showModal();
  });

  el("ws-copy").addEventListener("click", () => {
    navigator.clipboard?.writeText(el("ws-info-token").value).then(() => toast(t("wsCopied")));
  });

  el("ws-switch").addEventListener("click", async () => {
    el("workspace-info").close();
    localStorage.removeItem(WORKSPACE_STORAGE);
    setCookie(WORKSPACE_COOKIE, "", -1);  // keep the remembered list for one-click switch-back
    el("workspace-chip").hidden = true;
    state.selectedId = null;
    await ensureWorkspace();
    renderDetail(null);
    await loadCharacters();
  });
}

/* ---------- Image models ---------- */

function selectedModel() {
  return state.imageModels.find((m) => m.slug === el("image-model").value);
}

function applyModelUI() {
  const model = selectedModel();
  if (!model) return;
  el("quality-choice").hidden = !model.quality_tiers;
  el("identity-hint").textContent = model.identity ? t("identityLocks") : t("identityLoose");
  if (typeof updateCostEstimate === "function") updateCostEstimate();
}

/* ---------- Voices ---------- */

const PROVIDER_LABEL = { openai: "OpenAI TTS", gmi: "GMI (Inworld)" };

async function loadVoices() {
  state.voices = await api("/voices").catch(() => ({}));
  refreshVoicePicker("create");
}

function voiceOptionLabel(voice) {
  return voice.style ? `${voice.name} — ${voice.style}` : voice.name;
}

// Human label for a stored provider:id voice (falls back to the raw id).
function voiceLabelFor(provider, voiceId) {
  const list = (state.voices && state.voices[provider]) || [];
  const v = list.find((x) => x.id === voiceId);
  return v ? voiceOptionLabel(v) : voiceId;
}

// Fill a <select> with voices (grouped) plus a "none" option — used by the
// create and profile forms, the only places a voice can be chosen/changed.
// `filters` narrows by gender/age. This is a plain filter with no
// exceptions: if the previously selected voice doesn't match, it drops out
// and the select falls back to "none" — anything else (e.g. quietly
// keeping a stale selection alive) makes the filter look broken.
function buildVoicePicker(select, currentValue, filters) {
  if (!select) return;
  const gender = filters && filters.gender;
  const age = filters && filters.age;
  select.innerHTML = "";
  const none = document.createElement("option");
  none.value = "";
  none.textContent = t("voiceNone");
  select.appendChild(none);
  let shown = 0;
  for (const [provider, voices] of Object.entries(state.voices || {})) {
    const filtered = voices.filter((v) =>
      (!gender || v.gender === gender) && (!age || v.age === age));
    if (!filtered.length) continue;
    const group = document.createElement("optgroup");
    group.label = PROVIDER_LABEL[provider] || provider;
    for (const voice of filtered) {
      const o = document.createElement("option");
      o.value = `${provider}:${voice.id}`;
      o.textContent = voiceOptionLabel(voice);
      group.appendChild(o);
      shown += 1;
    }
    select.appendChild(group);
  }
  if (!shown && (gender || age)) {
    const opt = document.createElement("option");
    opt.textContent = t("voiceNoneMatch");
    opt.disabled = true;
    select.appendChild(opt);
  }
  const hasCurrent = currentValue && [...select.options].some((o) => o.value === currentValue);
  select.value = hasCurrent ? currentValue : "";
}

// Re-render a voice picker from its paired gender/age filter selects. Keeps
// the selection only if it still matches the new filter.
function refreshVoicePicker(prefix) {
  const select = el(`${prefix}-voice`);
  if (!select) return;
  const filters = {
    gender: el(`${prefix}-voice-filter-gender`).value,
    age: el(`${prefix}-voice-filter-age`).value,
  };
  buildVoicePicker(select, select.value, filters);
}

function splitVoiceValue(value) {
  if (!value) return { voice_provider: null, voice_id: null };
  const [provider, ...rest] = value.split(":");
  return { voice_provider: provider, voice_id: rest.join(":") };
}

// The voice-line card shows the character's FIXED voice read-only.
function populateVoiceSelect(character) {
  state.currentCharacter = character;
  const fixed = el("voice-fixed");
  const note = el("voice-note");
  if (character.voice_id) {
    fixed.textContent = voiceLabelFor(character.voice_provider, character.voice_id);
    fixed.dataset.value = `${character.voice_provider}:${character.voice_id}`;
    note.textContent = t("voiceFixedNote");
  } else {
    fixed.textContent = t("voiceNone");
    fixed.dataset.value = "";
    note.textContent = t("toastPickVoiceFirst");
  }
  note.hidden = false;
}

let previewAudio = null;

function previewVoiceValue(value, buttonId) {
  if (!value) return;
  const [provider, ...rest] = value.split(":");
  const voiceId = rest.join(":");
  const button = el(buttonId);
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

function previewVoice(selectId, buttonId) {
  previewVoiceValue(el(selectId).value, buttonId);
}

// Preview the voice currently selected in a picker (create / profile forms).
function previewPickerVoice(selectId, buttonId) {
  const value = el(selectId).value || "";
  if (!value) { toast(t("toastPickVoiceFirst"), true); return; }
  previewVoiceValue(value, buttonId);
}

async function loadImageModels() {
  const caps = await api("/capabilities").catch(() => ({ image_models: [], video_models: [] }));
  state.imageModels = caps.image_models || [];
  state.videoModels = caps.video_models || [];
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
  populateStudioModel();
  populateVideoModels();
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
  hideStudioView();
  hideAudioView();
  hideVideoView();
  hideScriptView();
  hideCanvasView();
  hideCanvasTemplatesView();
  setActiveNavGroup(null);
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

/* ---------- Transparency: per-asset detail card ---------- */
// Every generated asset already carries its full provenance (prompt, model,
// seed, quality, disclosure, manifest, cost, hash) — this surfaces it
// explicitly instead of leaving it in hover tooltips, so consistency claims
// are checkable, not just asserted.

function assetDetailFields(asset) {
  const fields = [];
  const push = (labelKey, value) => {
    if (value !== undefined && value !== null && value !== "") fields.push([labelKey, value]);
  };

  if (Array.isArray(asset.script) && asset.script.length) {
    push("detailScript", asset.script.map((s) => `${s.character_name}: ${s.text}`).join("\n"));
  } else if (asset.prompt) {
    push("detailPrompt", asset.prompt);
  }
  if (asset.character_name) push("detailWho", asset.character_name);
  if (Array.isArray(asset.participant_names) && asset.participant_names.length) {
    push("detailWho", asset.participant_names.join(" + "));
  }
  if (asset.voice) push("detailVoice", asset.voice);
  push("detailModel", asset.model);
  if (typeof asset.seed === "number") push("detailSeed", String(asset.seed));
  if (asset.quality) push("detailQuality", asset.quality === "final" ? t("qualityFinalShort") : t("qualityDraftShort"));
  if (asset.disclosure) {
    push("detailDisclosure", asset.disclosure === "visible" ? t("detailDisclosureVisible") : t("detailDisclosureInvisible"));
  }
  if (asset.manifest_verified !== undefined) {
    push("detailManifest", asset.manifest_verified ? t("detailManifestYes") : t("detailManifestNo"));
  }
  if (typeof asset.cost_usd === "number") push("detailCost", `$${asset.cost_usd.toFixed(4)}`);
  if (asset.duration) push("detailDuration", `${asset.duration}s`);
  if (asset.aspect_ratio) push("detailAspect", asset.aspect_ratio);
  if (asset.mime_type) push("detailType", asset.mime_type);
  if (asset.sha256) push("detailHash", asset.sha256);
  if (asset.created_at) push("detailCreated", formatTimestamp(asset.created_at));
  return fields;
}

function showAssetDetails(asset) {
  const body = el("detail-dialog-body");
  body.innerHTML = "";
  for (const [labelKey, value] of assetDetailFields(asset)) {
    const dt = document.createElement("dt");
    dt.textContent = t(labelKey);
    const dd = document.createElement("dd");
    if (labelKey === "detailHash") {
      const code = document.createElement("code");
      code.textContent = value;
      dd.appendChild(code);
      const copyBtn = document.createElement("button");
      copyBtn.type = "button";
      copyBtn.className = "button small";
      copyBtn.textContent = t("copy");
      copyBtn.addEventListener("click", () => {
        navigator.clipboard.writeText(value);
        toast(t("detailHashCopied"));
      });
      dd.appendChild(copyBtn);
    } else {
      dd.textContent = value;
    }
    body.append(dt, dd);
  }
  el("detail-dialog").showModal();
}

function addDetailsButton(actions, item) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "asset-details-btn";
  btn.textContent = t("detailsBtn");
  btn.addEventListener("click", () => showAssetDetails(item));
  actions.appendChild(btn);
}

function setupDetailDialog() {
  el("detail-dialog-close").addEventListener("click", () => el("detail-dialog").close());
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
  addDetailsButton(actions, asset);
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
  el("create-voice-filter-gender").addEventListener("change", () => refreshVoicePicker("create"));
  el("create-voice-filter-age").addEventListener("change", () => refreshVoicePicker("create"));
  el("create-cancel").addEventListener("click", () => { form.hidden = true; });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const seedVal = el("create-seed").value.trim();
    const voice = splitVoiceValue(el("create-voice").value);
    try {
      const created = await api("/characters", {
        method: "POST",
        body: JSON.stringify({
          name: el("create-name").value.trim(),
          description: el("create-description").value.trim(),
          personality: el("create-personality").value.trim() || null,
          purpose: el("create-purpose").value.trim() || null,
          seed: seedVal ? Number(seedVal) : null,
          voice_provider: voice.voice_provider,
          voice_id: voice.voice_id,
        }),
      });
      const fileInput = el("create-image");
      const uploadedOwnImage = fileInput.files.length > 0;
      if (uploadedOwnImage) {
        await uploadReferenceImage(created.id, fileInput.files[0]);
      }
      // Read before reset() wipes the form — it seeds the portrait prompts.
      const description = el("create-description").value.trim();
      form.reset();
      form.hidden = true;
      await loadCharacters(created.id);
      toast(`Created “${created.name}”`);
      // Someone who brought their own reference already has one; generating
      // alternatives would only spend credits on images they didn't ask for.
      if (!uploadedOwnImage) {
        await offerPortraitOptions(created, description);
      }
    } catch (err) {
      toast(err.message, true);
    }
  });
}

async function uploadReferenceImage(characterId, file) {
  const data = new FormData();
  data.append("file", file);
  const resp = await fetch(`/characters/${characterId}/reference`, {
    method: "POST", headers: { "X-API-Key": apiKey(), "X-Workspace-Id": workspaceId() }, body: data,
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : "Upload failed");
  }
  return resp.json();
}

function setupProfileEditing() {
  el("edit-voice-filter-gender").addEventListener("change", () => refreshVoicePicker("edit"));
  el("edit-voice-filter-age").addEventListener("change", () => refreshVoicePicker("edit"));
  el("edit-profile-button").addEventListener("click", () => {
    const c = state.currentCharacter;
    if (!c) return;
    el("edit-name").value = c.name || "";
    el("edit-description").value = c.description || "";
    el("edit-personality").value = c.personality || "";
    el("edit-purpose").value = c.purpose || "";
    el("edit-seed").value = c.seed ?? "";
    el("edit-voice-filter-gender").value = "";
    el("edit-voice-filter-age").value = "";
    buildVoicePicker(el("edit-voice"), c.voice_id ? `${c.voice_provider}:${c.voice_id}` : "");
    el("edit-form").hidden = false;
  });
  el("edit-cancel").addEventListener("click", () => { el("edit-form").hidden = true; });
  el("edit-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const seedVal = el("edit-seed").value.trim();
    const voice = splitVoiceValue(el("edit-voice").value);
    try {
      await api(`/characters/${state.selectedId}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: el("edit-name").value.trim(),
          description: el("edit-description").value.trim(),
          personality: el("edit-personality").value.trim(),
          purpose: el("edit-purpose").value.trim(),
          seed: seedVal ? Number(seedVal) : null,
          voice_provider: voice.voice_provider,
          voice_id: voice.voice_id,
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

/* ---------- Prompt builder ---------- */
// Optional structured fields → well-formed prompt fragments. Each field's
// display label is human-friendly; the value is the phrase appended to the
// prompt (models respond best to concrete photographic/cinematic terms).
// Shared by the character image card and the standalone Studio.
const PROMPT_FIELDS = [
  { label: "Style", options: [
    ["", "—"],
    ["photorealistic, highly detailed", "Photorealistic"],
    ["cinematic film still, dramatic composition", "Cinematic"],
    ["oil painting, visible brushstrokes", "Oil painting"],
    ["watercolor painting, soft edges", "Watercolor"],
    ["anime / manga art style", "Anime / Manga"],
    ["3D render, octane, physically based", "3D render"],
    ["comic book art, bold ink", "Comic"],
    ["pencil sketch, graphite", "Pencil sketch"],
    ["film noir, high-contrast black and white", "Film noir"],
    ["vintage analog photograph, film grain", "Vintage photo"],
    ["epic fantasy concept art", "Fantasy art"],
  ]},
  { label: "Lighting", options: [
    ["", "—"],
    ["golden hour lighting, warm sun", "Golden hour"],
    ["soft diffused studio lighting", "Soft studio"],
    ["hard direct flash", "Hard flash"],
    ["backlit, rim light, glowing edges", "Backlight"],
    ["neon lighting, colorful glow", "Neon"],
    ["candlelight, warm intimate glow", "Candlelight"],
    ["overcast diffused daylight", "Overcast"],
    ["dramatic side lighting, chiaroscuro", "Dramatic side light"],
    ["blue hour twilight", "Blue hour"],
  ]},
  { label: "Camera angle", options: [
    ["", "—"],
    ["eye-level shot", "Eye level"],
    ["low-angle shot, looking up", "Low angle"],
    ["high-angle shot, looking down", "High angle"],
    ["bird's-eye view, top-down", "Bird's eye"],
    ["dutch angle, tilted frame", "Dutch angle"],
    ["over-the-shoulder shot", "Over the shoulder"],
  ]},
  { label: "Framing", options: [
    ["", "—"],
    ["extreme close-up", "Extreme close-up"],
    ["close-up shot", "Close-up"],
    ["medium shot, waist up", "Medium shot"],
    ["full-body shot", "Full body"],
    ["wide establishing shot", "Wide shot"],
  ]},
  { label: "Lens", options: [
    ["", "—"],
    ["shot on 35mm lens", "35mm"],
    ["shot on 50mm lens", "50mm"],
    ["85mm portrait lens, shallow depth of field", "85mm portrait"],
    ["macro lens, extreme detail", "Macro"],
    ["wide-angle lens", "Wide-angle"],
    ["telephoto lens, compressed background", "Telephoto"],
    ["fisheye lens", "Fisheye"],
  ]},
  { label: "Mood", options: [
    ["", "—"],
    ["serene, calm mood", "Serene"],
    ["dramatic, intense mood", "Dramatic"],
    ["melancholic, wistful mood", "Melancholic"],
    ["energetic, dynamic mood", "Energetic"],
    ["mysterious, enigmatic mood", "Mysterious"],
    ["joyful, bright mood", "Joyful"],
    ["epic, grand scale", "Epic"],
  ]},
  { label: "Color", options: [
    ["", "—"],
    ["warm color palette", "Warm"],
    ["cool color palette", "Cool"],
    ["black and white, monochrome", "Black & white"],
    ["pastel color palette", "Pastel"],
    ["vibrant saturated colors", "Vibrant"],
    ["muted, desaturated colors", "Muted"],
    ["sepia tone", "Sepia"],
  ]},
];

function composePrompt(base, modifiers) {
  const extra = modifiers.trim();
  if (!extra) return base;
  if (!base.trim()) return extra;
  return `${base.trim()}. ${extra}`;
}

// Build the field selects into `container`; return an object exposing the
// current modifier string, the selects, and a reset. `onChange` fires on any
// field change so callers can refresh a live preview.
function createComposer(container, onChange) {
  container.innerHTML = "";
  const selects = [];
  for (const field of PROMPT_FIELDS) {
    const wrap = document.createElement("label");
    wrap.className = "composer-field";
    const span = document.createElement("span");
    span.textContent = field.label;
    const select = document.createElement("select");
    for (const [value, label] of field.options) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      select.appendChild(option);
    }
    if (onChange) select.addEventListener("change", onChange);
    wrap.append(span, select);
    container.appendChild(wrap);
    selects.push(select);
  }
  return {
    modifiers: () => selects.map((s) => s.value).filter(Boolean).join(", "),
    reset: () => { selects.forEach((s) => { s.value = ""; }); if (onChange) onChange(); },
    selects,
  };
}

let imageComposer = null;

function refreshPromptPreview() {
  if (!imageComposer) return;
  updateCostEstimate();
  const preview = el("prompt-preview");
  const mods = imageComposer.modifiers();
  const base = el("image-prompt").value.trim();
  if (!mods) { preview.hidden = true; return; }
  preview.textContent = `Prompt: ${composePrompt(base || "…", mods)}`;
  preview.hidden = false;
}

function setupImageComposer() {
  imageComposer = createComposer(el("prompt-composer"), refreshPromptPreview);
  el("composer-reset").addEventListener("click", () => imageComposer.reset());
  el("image-prompt").addEventListener("input", refreshPromptPreview);
}

/* ---------- Generation ---------- */

const MODE_META = {
  single: { counted: false, buttonKey: "modePortraitBtn", phKey: "phSinglePrompt", hintKey: null },
  variation: { counted: true, buttonKey: "modeVariationBtn", phKey: "phVariationPrompt", hintKey: "hintVariation" },
  photoshoot: { counted: true, buttonKey: "modePhotoshootBtn", phKey: "phPhotoshootPrompt", hintKey: "hintPhotoshoot" },
  story: { counted: false, buttonKey: "modeStoryBtn", phKey: "phStoryPrompt", hintKey: "hintStory" },
  scene: { counted: false, buttonKey: "genSceneBtn", phKey: "phScenePrompt", hintKey: "hintScene" },
};

function currentMode() {
  return el("gen-mode").value;
}

function plannedCount() {
  const mode = currentMode();
  if (mode === "single") return 1;
  if (mode === "story") {
    const lines = el("image-prompt").value.split("\n").map((l) => l.trim()).filter(Boolean);
    return Math.max(1, lines.length);
  }
  return Math.max(1, Math.min(100, Number(el("gen-count").value) || 1));
}

function unitCost() {
  const model = selectedModel();
  if (!model) return null;
  if (model.quality_tiers) {
    const q = document.querySelector('input[name="quality"]:checked').value;
    return q === "final" ? model.cost_final : model.cost_draft;
  }
  return model.cost;
}

function updateCostEstimate() {
  const box = el("cost-estimate");
  if (currentMode() === "scene") { box.hidden = true; return; }
  const unit = unitCost();
  const count = plannedCount();
  if (unit == null) { box.hidden = true; return; }
  const total = unit * count;
  const frames = currentMode() === "story" ? "panel" : "image";
  box.textContent = count > 1
    ? `Estimated cost: ${count} × $${unit.toFixed(3)} ≈ $${total.toFixed(2)}`
    : `Estimated cost: ~$${unit.toFixed(3)} for one ${frames}`;
  box.hidden = false;
}

function toggleGalleryPanels() {
  const isScene = currentMode() === "scene";
  el("single-gallery").hidden = isScene;
  el("scene-gallery").hidden = !isScene;
  if (isScene) loadScenes();
}

function updateModeUI() {
  const mode = currentMode();
  const meta = MODE_META[mode];
  const isScene = mode === "scene";
  setActiveNavSubitem("scenes", mode);
  el("count-row").hidden = !meta.counted;
  el("image-prompt").placeholder = t(meta.phKey);
  el("image-prompt").rows = mode === "story" ? 5 : 2;
  el("mode-hint").textContent = meta.hintKey ? t(meta.hintKey) : "";
  el("mode-hint").hidden = !meta.hintKey;
  el("generate-image-button").textContent = t(meta.buttonKey);
  el("image-model-row").hidden = isScene;
  el("quality-choice").hidden = isScene;
  renderImageParticipants();
  toggleGalleryPanels();
  updateCostEstimate();
}

function setGenerating(active, message = "", isError = false) {
  state.generating = active;
  el("generate-image-button").disabled = active;
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

async function generateImage() {
  if (state.generating) return;
  const mode = currentMode();
  const ids = pickedImageIds();

  if (mode === "scene") {
    await generateSceneImage(ids);
    return;
  }

  const pickedId = ids[0];
  if (!pickedId) { toast(t("toastPickCharacterFirst"), true); return; }

  const input = el("image-prompt");
  const value = input.value.trim();
  if (!value) { toast(t("toastDescribeFirst"), true); input.focus(); return; }

  const mods = imageComposer ? imageComposer.modifiers() : "";
  // Story splits per line server-side, so the builder fields must ride on
  // every line — not just the tail — to style each panel equally.
  const prompt = mode === "story" && mods
    ? value.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => composePrompt(l, mods)).join("\n")
    : composePrompt(value, mods);
  const payload = {
    prompt,
    model: el("image-model").value,
    disclosure: document.querySelector('input[name="disclosure"]:checked').value,
    use_identity: !el("identity-row").hidden && el("use-identity").checked,
    quality: document.querySelector('input[name="quality"]:checked').value,
  };

  if (mode === "single") {
    setGenerating(true, t("generatingImage"));
    try {
      await api(`/characters/${pickedId}/generate/image`, {
        method: "POST", headers: { "X-API-Key": apiKey() }, body: JSON.stringify(payload),
      });
      input.value = "";
      setGenerating(false);
      await refreshSingleCharacterPanel(pickedId);
      toast(t("toastPortraitSaved"));
    } catch (err) {
      if (err.status === 401) { setGenerating(false); openKeyDialog(); toast(t("toastNeedKey"), true); }
      else { setGenerating(false, err.message, true); }
    }
    return;
  }

  await runBatch({ ...payload, mode, count: plannedCount() }, pickedId);
}

let batchCancelId = null;

async function runBatch(payload, pickedId) {
  setGenerating(true, "Starting the batch…");
  const progress = el("batch-progress");
  try {
    const job = await api(`/characters/${pickedId}/generate/batch`, {
      method: "POST", headers: { "X-API-Key": apiKey() }, body: JSON.stringify(payload),
    });
    batchCancelId = job.id;
    progress.hidden = false;
    el("generation-status").hidden = true;
    updateBatchProgress(job);

    while (true) {
      await new Promise((r) => setTimeout(r, 1500));
      const status = await api(`/batches/${job.id}`);
      updateBatchProgress(status);
      await refreshSingleCharacterPanel(pickedId);  // stream new frames into the gallery
      if (["done", "error", "cancelled"].includes(status.status)) {
        finishBatch(status);
        break;
      }
    }
  } catch (err) {
    progress.hidden = true;
    if (err.status === 401) { setGenerating(false); openKeyDialog(); toast("Generation needs a valid API key.", true); }
    else { setGenerating(false, err.message, true); }
  } finally {
    batchCancelId = null;
  }
}

function updateBatchProgress(job) {
  const total = job.requested || 1;
  const done = (job.completed || 0) + (job.failed || 0);
  el("batch-bar-fill").style.width = `${Math.round((done / total) * 100)}%`;
  const failed = job.failed ? ` · ${job.failed} failed` : "";
  el("batch-progress-label").textContent = `${job.completed || 0} / ${total} generated${failed}`;
}

function finishBatch(job) {
  setGenerating(false);
  el("generate-image-button").disabled = false;
  el("batch-progress").hidden = true;
  if (job.status === "cancelled") toast(`Stopped — ${job.completed} of ${job.requested} generated.`);
  else if (job.status === "error") toast(job.error || "Batch failed.", true);
  else {
    el("image-prompt").value = "";
    const failed = job.failed ? ` (${job.failed} failed)` : "";
    toast(`Done — ${job.completed} images stored in the vault${failed}.`);
  }
}

async function cancelBatch() {
  if (batchCancelId == null) return;
  el("batch-cancel").disabled = true;
  try { await api(`/batches/${batchCancelId}/cancel`, { method: "POST" }); }
  catch (err) { toast(err.message, true); }
  finally { el("batch-cancel").disabled = false; }
}

/* ---------- Reference portrait, picked at creation ---------- */

// A character without a portrait is a dead end: scenes, videos and image
// batches all condition on a reference image, so creating one used to hand
// back something no other feature could act on — the portrait had to be
// brought in from outside. Creation now generates four variants straight away
// and keeps whichever one is chosen, leaving the character with exactly one
// reference. Variants are drafts: four finals cost roughly fifteen times as
// much, and the pick is about composition and likeness, not pixel polish.
const PORTRAIT_OPTION_COUNT = 4;

let portraitPickBatchId = null;

async function offerPortraitOptions(character, description) {
  // The description *is* the prompt. Without one there is nothing to draw from,
  // and inventing an appearance would defeat the point of a reference.
  if (!description) {
    toast(t("portraitPickNeedDescription"));
    return;
  }

  const dialog = el("portrait-pick-dialog");
  const note = el("portrait-pick-note");
  el("portrait-pick-grid").innerHTML = "";
  note.hidden = true;
  el("portrait-pick-progress").hidden = false;
  el("portrait-pick-keep-all").hidden = true;
  el("portrait-pick-close").hidden = true;
  el("portrait-pick-label").textContent = t("portraitPickWaiting");
  el("portrait-pick-bar").style.width = "0%";
  dialog.showModal();

  try {
    const job = await api(`/characters/${character.id}/generate/batch`, {
      method: "POST",
      headers: { "X-API-Key": apiKey() },
      body: JSON.stringify({
        mode: "variation",
        prompt: description,
        count: PORTRAIT_OPTION_COUNT,
        quality: "draft",
        model: el("image-model")?.value || "gpt-image-1",
        disclosure: "invisible",
      }),
    });
    portraitPickBatchId = job.id;

    let status = job;
    while (!["done", "error", "cancelled"].includes(status.status)) {
      await new Promise((r) => setTimeout(r, 1500));
      status = await api(`/batches/${job.id}`);
      const settled = (status.completed || 0) + (status.failed || 0);
      el("portrait-pick-bar").style.width =
        `${Math.round((settled / PORTRAIT_OPTION_COUNT) * 100)}%`;
      el("portrait-pick-label").textContent =
        `${status.completed || 0} / ${PORTRAIT_OPTION_COUNT}`;
    }
    // A stopped batch still shows whatever finished — those images exist and
    // were paid for, so throwing them away would be the wrong call.
    await showPortraitOptions(character.id, job.id);
  } catch (err) {
    el("portrait-pick-progress").hidden = true;
    if (err.status === 401) {
      dialog.close();
      openKeyDialog();
      toast(t("toastNeedKey"), true);
    } else {
      note.textContent = err.message;
      note.hidden = false;
      el("portrait-pick-close").hidden = false;
    }
  } finally {
    portraitPickBatchId = null;
  }
}

async function showPortraitOptions(characterId, batchId) {
  el("portrait-pick-progress").hidden = true;
  const note = el("portrait-pick-note");
  const grid = el("portrait-pick-grid");
  grid.innerHTML = "";

  const character = await api(`/characters/${characterId}`);
  const options = character.assets.filter(
    (a) => a.kind === "image" && a.batch_id === batchId && a.signed_url,
  );

  if (!options.length) {
    note.textContent = t("portraitPickNone");
    note.hidden = false;
    el("portrait-pick-close").hidden = false;
    return;
  }

  el("portrait-pick-label").textContent = t("portraitPickReady");
  el("portrait-pick-keep-all").hidden = false;
  for (const asset of options) {
    const figure = document.createElement("figure");
    figure.className = "portrait-option";

    const img = document.createElement("img");
    img.src = asset.signed_url;
    img.alt = "";
    img.loading = "lazy";
    figure.appendChild(img);

    const button = document.createElement("button");
    button.type = "button";
    button.className = "button primary small";
    button.textContent = t("portraitPickUse");
    button.addEventListener("click", () => keepOnePortrait(characterId, asset.id, options));
    figure.appendChild(button);

    grid.appendChild(figure);
  }
}

async function keepOnePortrait(characterId, keepAssetId, options) {
  const buttons = el("portrait-pick-grid").querySelectorAll("button");
  buttons.forEach((b) => { b.disabled = true; });
  try {
    for (const asset of options) {
      if (asset.id !== keepAssetId) await api(`/assets/${asset.id}`, { method: "DELETE" });
    }
    toast(t("portraitPickKept"));
  } catch (err) {
    toast(err.message, true);
  } finally {
    el("portrait-pick-dialog").close();
    await loadCharacters(characterId);
  }
}

async function cancelPortraitBatch() {
  if (portraitPickBatchId == null) return;
  el("portrait-pick-cancel").disabled = true;
  try { await api(`/batches/${portraitPickBatchId}/cancel`, { method: "POST" }); }
  catch (err) { toast(err.message, true); }
  finally { el("portrait-pick-cancel").disabled = false; }
}

// The picked character's own asset gallery, shown inside the Images tab
// (separate id from the read-only #asset-grid on the profile page).
async function refreshSingleCharacterPanel(id) {
  try {
    const character = await api(`/characters/${id}`);
    const imageCount = character.assets.filter((a) => a.kind === "image").length;
    el("identity-row").hidden = imageCount === 0;
    el("identity-count").textContent = String(Math.min(imageCount, 3));
    const grid = el("images-asset-grid");
    grid.innerHTML = "";
    el("images-asset-empty").hidden = character.assets.length > 0;
    for (const asset of [...character.assets].reverse()) grid.appendChild(renderAssetCard(asset));
  } catch (err) {
    toast(err.message, true);
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

// The sidebar groups several distinct workflows (image modes, studio modes,
// video sources, audio modes) under 4 collapsible headings so the nav stays
// scannable instead of listing every mode as its own top-level button. Each
// heading maps to one or more of the 4 underlying views; opening any view
// expands and highlights its heading so "where am I" stays visible.
const NAV_GROUP_OF = { scenes: "bild", studio: "bild", audio: "ton", video: "video", canvas: "canvas" };

function setActiveNavGroup(openKey) {
  // Clears "current view" highlighting only — expand/collapse state (hidden,
  // aria-expanded) of OTHER groups is left alone, since a user may
  // deliberately keep several groups open at once while browsing.
  document.querySelectorAll(".nav-group").forEach((g) => g.classList.remove("active"));
  document.querySelectorAll(".nav-subitem").forEach((b) => b.classList.remove("active"));
  const groupKey = NAV_GROUP_OF[openKey];
  if (!groupKey) return;
  const group = document.querySelector(`.nav-group[data-group="${groupKey}"]`);
  if (!group) return;
  group.classList.add("active");
  group.querySelector(".nav-group-toggle").setAttribute("aria-expanded", "true");
  group.querySelector(".nav-group-body").hidden = false;
}

function setActiveNavSubitem(openKey, mode) {
  document.querySelectorAll(".nav-subitem").forEach((b) =>
    b.classList.toggle("active", b.dataset.open === openKey && (mode == null || b.dataset.mode === mode)));
}

// Each sidebar group toggle expands/collapses its own body only — expanding
// one doesn't touch the others, so a user can keep several open at once.
// Each sub-item presets the target view's mode before opening it, so
// clicking straight from the sidebar lands exactly where its label says.
function setupNavGroups() {
  document.querySelectorAll(".nav-group-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const body = btn.parentElement.querySelector(".nav-group-body");
      const expanded = btn.getAttribute("aria-expanded") === "true";
      body.hidden = expanded;
      btn.setAttribute("aria-expanded", String(!expanded));
    });
  });

  const OPEN_VIEW = { scenes: showScenesView, studio: showStudioView, audio: showAudioView, video: showVideoView };
  // Canvas's sub-items (New template / My templates) open two genuinely
  // different views rather than presetting a mode within one — wired
  // separately in canvas.js's own setupCanvas(), which loads after this
  // script, so it can't be referenced from this generic map yet.
  document.querySelectorAll('.nav-subitem:not([data-open="canvas"])').forEach((btn) => {
    btn.addEventListener("click", () => {
      const { open, mode } = btn.dataset;
      if (open === "scenes") el("gen-mode").value = mode;
      else if (open === "studio") setStudioMode(mode);
      else if (open === "audio") setAudioMode(mode);
      else if (open === "video") el("video-source").value = mode;
      OPEN_VIEW[open]();
    });
  });
}

function showScenesView() {
  state.selectedId = null;
  renderCharacterList();
  hideStudioView();
  hideAudioView();
  hideVideoView();
  hideScriptView();
  hideCanvasView();
  hideCanvasTemplatesView();
  el("detail-placeholder").hidden = true;
  el("detail-content").hidden = true;
  el("scenes-view").hidden = false;
  setActiveNavGroup("scenes");
  setActiveNavSubitem("scenes", currentMode());
  updateModeUI();
}

function hideScenesView() {
  el("scenes-view").hidden = true;
}

// Shared picker for the Images tab: a single active radio for modes that
// generate for one character, or 2-4 checkboxes for "scene" mode — same
// DOM, the input type switches with the mode so exclusivity comes free
// from the browser instead of hand-rolled JS.
function pickedImageIds() {
  return [...document.querySelectorAll("#image-participants input:checked")].map((c) => Number(c.value));
}

function onImageParticipantsChange() {
  const ids = pickedImageIds();
  if (currentMode() !== "scene" && ids.length === 1) {
    refreshSingleCharacterPanel(ids[0]);
  } else {
    el("identity-row").hidden = true;
  }
  updateCostEstimate();
}

function renderImageParticipants() {
  const box = el("image-participants");
  const isScene = currentMode() === "scene";
  // The picker silently switches between "exactly one" and "2-4" depending
  // on mode (single-character modes need one identity to stay consistent;
  // scenes compose several) — spell that out, since the radio/checkbox
  // switch alone isn't obvious.
  el("participants-label").textContent = t(isScene ? "pickSceneCharacters" : "pickOneCharacter");
  const prevChecked = new Set([...box.querySelectorAll("input:checked")].map((c) => c.value));
  box.innerHTML = "";
  const withPortrait = state.characters.filter((c) => c.thumbnail_url);
  if (!withPortrait.length) {
    box.innerHTML = `<p class="empty-note">${t("needPortraitForImages")}</p>`;
    return;
  }
  withPortrait.forEach((character, idx) => {
    const label = document.createElement("label");
    label.className = "participant";
    const cb = document.createElement("input");
    cb.type = isScene ? "checkbox" : "radio";
    if (!isScene) cb.name = "image-participant";
    cb.value = String(character.id);
    cb.checked = prevChecked.has(String(character.id)) || (!isScene && !prevChecked.size && idx === 0);
    cb.addEventListener("change", onImageParticipantsChange);
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
  });
  onImageParticipantsChange();
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
    addDetailsButton(actions, scene);
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

async function generateSceneImage(ids) {
  const prompt = el("image-prompt").value.trim();
  if (ids.length < 2) { toast(t("toastPickTwoCharacters"), true); return; }
  if (ids.length > 4) { toast(t("toastPickAtMostFour"), true); return; }
  if (!prompt) { toast(t("toastDescribeSceneFirst"), true); el("image-prompt").focus(); return; }

  setGenerating(true, t("generatingScene"));
  try {
    await api("/scenes", {
      method: "POST",
      headers: { "X-API-Key": apiKey() },
      body: JSON.stringify({
        character_ids: ids,
        prompt,
        disclosure: document.querySelector('input[name="disclosure"]:checked').value,
      }),
    });
    el("image-prompt").value = "";
    setGenerating(false);
    await loadScenes();
    toast(t("toastSceneCreated"));
  } catch (err) {
    if (err.status === 401) { setGenerating(false); openKeyDialog(); toast(t("toastNeedKey"), true); }
    else { setGenerating(false, err.message, true); }
  }
}

/* ---------- Studio: backgrounds & photo art ---------- */

const STUDIO_MODE_HINT = { "photo-art": "studioHintPhoto", "background": "studioHintBg" };

let studioComposer = null;
let studioMode = "photo-art";

function showStudioView() {
  state.selectedId = null;
  renderCharacterList();
  hideScenesView();
  hideAudioView();
  hideVideoView();
  hideScriptView();
  hideCanvasView();
  hideCanvasTemplatesView();
  el("detail-placeholder").hidden = true;
  el("detail-content").hidden = true;
  el("studio-view").hidden = false;
  setActiveNavGroup("studio");
  setActiveNavSubitem("studio", studioMode);
  applyStudioModelUI();
  updateStudioCost();
  loadStudio();
}

function hideStudioView() {
  el("studio-view").hidden = true;
}

function populateStudioModel() {
  const select = el("studio-model");
  select.innerHTML = "";
  for (const model of state.imageModels) {
    const option = document.createElement("option");
    option.value = model.slug;
    option.textContent = model.label;
    select.appendChild(option);
  }
}

function selectedStudioModel() {
  return state.imageModels.find((m) => m.slug === el("studio-model").value);
}

function applyStudioModelUI() {
  const model = selectedStudioModel();
  if (!model) return;
  el("studio-quality-choice").hidden = !model.quality_tiers;
  updateStudioCost();
}

function updateStudioCost() {
  const box = el("studio-cost");
  const model = selectedStudioModel();
  if (!model) { box.hidden = true; return; }
  let unit;
  if (model.quality_tiers) {
    const q = document.querySelector('input[name="studio-quality"]:checked').value;
    unit = q === "final" ? model.cost_final : model.cost_draft;
  } else {
    unit = model.cost;
  }
  if (unit == null) { box.hidden = true; return; }
  box.textContent = `Estimated cost: ~$${unit.toFixed(3)} per image`;
  box.hidden = false;
}

function refreshStudioPreview() {
  if (!studioComposer) return;
  const preview = el("studio-preview");
  const mods = studioComposer.modifiers();
  const base = el("studio-prompt").value.trim();
  if (!mods) { preview.hidden = true; return; }
  preview.textContent = `Prompt: ${composePrompt(base || "…", mods)}`;
  preview.hidden = false;
}

function setStudioMode(mode) {
  studioMode = mode;
  document.querySelectorAll(".studio-mode").forEach((b) => {
    b.classList.toggle("active", b.dataset.mode === mode);
  });
  setActiveNavSubitem("studio", mode);
  el("studio-mode-hint").textContent = t(STUDIO_MODE_HINT[mode]);
}

function setupStudio() {
  studioComposer = createComposer(el("studio-composer"), refreshStudioPreview);
  el("studio-composer-reset").addEventListener("click", () => studioComposer.reset());
  el("studio-prompt").addEventListener("input", refreshStudioPreview);
  el("studio-model").addEventListener("change", applyStudioModelUI);
  el("generate-studio-button").addEventListener("click", generateStudioImage);
  document.querySelectorAll(".studio-mode").forEach((b) => {
    b.addEventListener("click", () => setStudioMode(b.dataset.mode));
  });
  document.querySelectorAll('input[name="studio-quality"]').forEach((r) =>
    r.addEventListener("change", updateStudioCost));
  setStudioMode("photo-art");
}

let studioGenerating = false;

async function generateStudioImage() {
  if (studioGenerating) return;
  const base = el("studio-prompt").value.trim();
  if (!base) { toast("Describe the image first.", true); el("studio-prompt").focus(); return; }

  const prompt = composePrompt(base, studioComposer ? studioComposer.modifiers() : "");
  studioGenerating = true;
  el("generate-studio-button").disabled = true;
  const status = el("studio-status");
  status.classList.remove("error");
  status.innerHTML = `<span class="spinner" aria-hidden="true"></span>${t("generatingAudio")}`;
  status.hidden = false;
  try {
    await api("/studio", {
      method: "POST",
      headers: { "X-API-Key": apiKey() },
      body: JSON.stringify({
        kind: studioMode,
        prompt,
        model: el("studio-model").value,
        quality: document.querySelector('input[name="studio-quality"]:checked').value,
        disclosure: document.querySelector('input[name="studio-disclosure"]:checked').value,
      }),
    });
    el("studio-prompt").value = "";
    status.hidden = true;
    await loadStudio();
    toast(t("toastImageSaved"));
  } catch (err) {
    if (err.status === 401) { status.hidden = true; openKeyDialog(); toast("Generation needs a valid API key.", true); }
    else { status.classList.add("error"); status.textContent = err.message; }
  } finally {
    studioGenerating = false;
    el("generate-studio-button").disabled = false;
  }
}

async function loadStudio() {
  try {
    renderStudio(await api("/studio"));
  } catch (err) {
    toast(err.message, true);
  }
}

function renderStudio(images) {
  const grid = el("studio-grid");
  grid.innerHTML = "";
  el("studio-empty").hidden = images.length > 0;
  for (const image of images) {
    const card = document.createElement("div");
    card.className = "asset-card";
    if (image.signed_url) {
      const img = document.createElement("img");
      img.src = image.signed_url;
      img.alt = image.prompt;
      img.loading = "lazy";
      img.tabIndex = 0;
      img.addEventListener("click", () => openLightbox(image.signed_url, image.prompt));
      card.appendChild(img);
    }
    const body = document.createElement("div");
    body.className = "asset-body";
    const tag = document.createElement("p");
    tag.className = "scene-who";
    tag.textContent = image.kind === "background" ? "Background / Scene" : "Photo Art";
    body.appendChild(tag);
    const prompt = document.createElement("p");
    prompt.className = "asset-prompt";
    prompt.textContent = image.prompt;
    prompt.title = image.prompt;
    body.appendChild(prompt);
    const meta = document.createElement("div");
    meta.className = "asset-meta";
    const time = document.createElement("span");
    const parts = [formatTimestamp(image.created_at)];
    if (image.model) parts.push(image.model.replace("gemini-2.5-flash-image", "nano-banana"));
    if (image.quality) parts.push(image.quality);
    if (typeof image.cost_usd === "number") parts.push(`$${image.cost_usd.toFixed(3)}`);
    time.textContent = parts.join(" · ");
    meta.appendChild(time);
    const actions = document.createElement("span");
    actions.className = "asset-actions";
    if (image.signed_url) {
      const open = document.createElement("a");
      open.href = image.signed_url;
      open.target = "_blank";
      open.rel = "noopener";
      open.textContent = "Open ↗";
      actions.appendChild(open);
    }
    addDetailsButton(actions, image);
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "asset-delete";
    remove.textContent = "Delete";
    remove.addEventListener("click", async () => {
      if (!confirm("Delete this image?")) return;
      try { await api(`/studio/${image.id}`, { method: "DELETE" }); loadStudio(); toast("Image deleted."); }
      catch (err) { toast(err.message, true); }
    });
    actions.appendChild(remove);
    meta.appendChild(actions);
    body.appendChild(meta);
    card.appendChild(body);
    grid.appendChild(card);
  }
}

/* ---------- Audio: narration & voiceover ---------- */

function showAudioView() {
  state.selectedId = null;
  renderCharacterList();
  hideScenesView();
  hideStudioView();
  hideVideoView();
  hideScriptView();
  hideCanvasView();
  hideCanvasTemplatesView();
  el("detail-placeholder").hidden = true;
  el("detail-content").hidden = true;
  el("audio-view").hidden = false;
  setActiveNavGroup("audio");
  setActiveNavSubitem("audio", audioMode);
  renderAudioVoices();
  loadAudio();
  renderDialogueParticipants();
  loadDialogues();
}

function hideAudioView() {
  el("audio-view").hidden = true;
}

function renderAudioVoices() {
  const select = el("audio-voice-select");
  const gender = el("audio-filter-gender").value;
  const age = el("audio-filter-age").value;
  select.innerHTML = "";
  let shown = 0;
  for (const [provider, voices] of Object.entries(state.voices)) {
    const filtered = voices.filter((v) =>
      (!gender || v.gender === gender) && (!age || v.age === age));
    if (!filtered.length) continue;
    const group = document.createElement("optgroup");
    group.label = PROVIDER_LABEL[provider] || provider;
    for (const voice of filtered) {
      const option = document.createElement("option");
      option.value = `${provider}:${voice.id}`;
      option.textContent = voiceOptionLabel(voice);
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
}

let audioMode = "single";

function setAudioMode(mode) {
  audioMode = mode;
  document.querySelectorAll(".audio-source-btn[data-audio-mode]").forEach((b) =>
    b.classList.toggle("active", b.dataset.audioMode === mode));
  setActiveNavSubitem("audio", mode);
  el("audio-single-panel").hidden = mode !== "single";
  el("audio-dialogue-panel").hidden = mode !== "dialogue";
  el("audio-single-gallery").hidden = mode !== "single";
  el("audio-dialogue-gallery").hidden = mode !== "dialogue";
}

function setupAudio() {
  el("generate-audio-button").addEventListener("click", generateAudioClip);
  el("audio-filter-gender").addEventListener("change", renderAudioVoices);
  el("audio-filter-age").addEventListener("change", renderAudioVoices);
  el("audio-voice-preview").addEventListener("click", () => previewVoice("audio-voice-select", "audio-voice-preview"));
  document.querySelectorAll(".audio-source-btn[data-audio-mode]").forEach((b) =>
    b.addEventListener("click", () => setAudioMode(b.dataset.audioMode)));
  setAudioMode("single");
  el("generate-dialogue-button").addEventListener("click", generateDialogue);
}

let audioGenerating = false;

async function generateAudioClip() {
  if (audioGenerating) return;
  const text = el("audio-text").value.trim();
  if (!text) { toast("Write the line to speak first.", true); el("audio-text").focus(); return; }

  const value = el("audio-voice-select").value;
  if (!value) { toast("Pick a voice first.", true); return; }
  const parts = value.split(":");
  const provider = parts[0];
  const voiceId = parts.slice(1).join(":");

  audioGenerating = true;
  el("generate-audio-button").disabled = true;
  const status = el("audio-status");
  status.classList.remove("error");
  status.innerHTML = `<span class="spinner" aria-hidden="true"></span>${t("generatingAudio")}`;
  status.hidden = false;
  try {
    await api("/audio", {
      method: "POST",
      headers: { "X-API-Key": apiKey() },
      body: JSON.stringify({ text, voice_provider: provider, voice_id: voiceId }),
    });
    el("audio-text").value = "";
    status.hidden = true;
    await loadAudio();
    toast(t("toastAudioSaved"));
  } catch (err) {
    if (err.status === 401) { status.hidden = true; openKeyDialog(); toast("Generation needs a valid API key.", true); }
    else { status.classList.add("error"); status.textContent = err.message; }
  } finally {
    audioGenerating = false;
    el("generate-audio-button").disabled = false;
  }
}

async function loadAudio() {
  try {
    renderAudio(await api("/audio"));
  } catch (err) {
    toast(err.message, true);
  }
}

function renderAudio(clips) {
  const grid = el("audio-grid");
  grid.innerHTML = "";
  el("audio-empty").hidden = clips.length > 0;
  for (const clip of clips) {
    const card = document.createElement("div");
    card.className = "asset-card";
    const body = document.createElement("div");
    body.className = "asset-body";
    if (clip.signed_url) {
      const audio = document.createElement("audio");
      audio.controls = true;
      audio.src = clip.signed_url;
      audio.preload = "none";
      body.appendChild(audio);
    }
    const text = document.createElement("p");
    text.className = "asset-prompt";
    text.textContent = clip.text;
    text.title = clip.text;
    body.appendChild(text);
    const meta = document.createElement("div");
    meta.className = "asset-meta";
    const time = document.createElement("span");
    const parts = [formatTimestamp(clip.created_at)];
    if (clip.voice) parts.push(clip.voice);
    if (typeof clip.cost_usd === "number") parts.push(`$${clip.cost_usd.toFixed(4)}`);
    time.textContent = parts.join(" · ");
    meta.appendChild(time);
    const actions = document.createElement("span");
    actions.className = "asset-actions";
    if (clip.signed_url) {
      const open = document.createElement("a");
      open.href = clip.signed_url;
      open.target = "_blank";
      open.rel = "noopener";
      open.textContent = "Open ↗";
      actions.appendChild(open);
    }
    addDetailsButton(actions, clip);
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "asset-delete";
    remove.textContent = "Delete";
    remove.addEventListener("click", async () => {
      if (!confirm("Delete this audio clip?")) return;
      try { await api(`/audio/${clip.id}`, { method: "DELETE" }); loadAudio(); toast("Audio deleted."); }
      catch (err) { toast(err.message, true); }
    });
    actions.appendChild(remove);
    meta.appendChild(actions);
    body.appendChild(meta);
    card.appendChild(body);
    grid.appendChild(card);
  }
}

/* ---------- Audio: dialogue between multiple characters ---------- */

function renderDialogueParticipants() {
  const box = el("dialogue-participants");
  const prevChecked = new Set([...box.querySelectorAll("input:checked")].map((c) => c.value));
  box.innerHTML = "";
  const withVoice = state.characters.filter((c) => c.voice_id);
  if (!withVoice.length) {
    box.innerHTML = `<p class="empty-note">${t("needVoiceForDialogue")}</p>`;
    return;
  }
  for (const character of withVoice) {
    const label = document.createElement("label");
    label.className = "participant";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = String(character.id);
    cb.checked = prevChecked.has(String(character.id));
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
    const name = document.createElement("span");
    name.textContent = character.name;
    label.append(cb, avatar, name);
    box.appendChild(label);
  }
}

// Parses "Name: line" per line against the checked participants (case-
// insensitive). Returns {turns} on success or {error} naming the exact
// line that didn't match, so the user can fix it instead of guessing.
function parseDialogueScript(text, checkedCharacters) {
  const byName = new Map(checkedCharacters.map((c) => [c.name.toLowerCase(), c]));
  const turns = [];
  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
  for (const line of lines) {
    const idx = line.indexOf(":");
    if (idx < 0) return { error: t("dialogueLineFormat").replace("{line}", line) };
    const name = line.slice(0, idx).trim();
    const spoken = line.slice(idx + 1).trim();
    const character = byName.get(name.toLowerCase());
    if (!character) return { error: t("dialogueUnknownSpeaker").replace("{name}", name) };
    if (!spoken) return { error: t("dialogueLineFormat").replace("{line}", line) };
    turns.push({ character_id: character.id, text: spoken });
  }
  return { turns };
}

let dialogueGenerating = false;

async function generateDialogue() {
  if (dialogueGenerating) return;
  const ids = [...document.querySelectorAll("#dialogue-participants input:checked")].map((c) => Number(c.value));
  if (ids.length < 2) { toast(t("toastPickTwoCharacters"), true); return; }
  if (ids.length > 6) { toast(t("toastPickAtMostSix"), true); return; }
  const checkedCharacters = state.characters.filter((c) => ids.includes(c.id));
  const script = el("dialogue-script").value.trim();
  if (!script) { toast(t("toastWriteScriptFirst"), true); el("dialogue-script").focus(); return; }

  const { turns, error } = parseDialogueScript(script, checkedCharacters);
  if (error) { toast(error, true); return; }

  dialogueGenerating = true;
  el("generate-dialogue-button").disabled = true;
  const status = el("audio-status");
  status.classList.remove("error");
  status.innerHTML = `<span class="spinner" aria-hidden="true"></span>${t("generatingDialogue")}`;
  status.hidden = false;
  try {
    await api("/audio/dialogue", {
      method: "POST", headers: { "X-API-Key": apiKey() }, body: JSON.stringify({ turns }),
    });
    el("dialogue-script").value = "";
    status.hidden = true;
    await loadDialogues();
    toast(t("toastDialogueCreated"));
  } catch (err) {
    if (err.status === 401) { status.hidden = true; openKeyDialog(); toast(t("toastNeedKey"), true); }
    else { status.classList.add("error"); status.textContent = err.message; }
  } finally {
    dialogueGenerating = false;
    el("generate-dialogue-button").disabled = false;
  }
}

async function loadDialogues() {
  try {
    renderDialogues(await api("/audio/dialogue"));
  } catch (err) {
    toast(err.message, true);
  }
}

function renderDialogues(dialogues) {
  const grid = el("dialogue-grid");
  grid.innerHTML = "";
  el("dialogue-empty").hidden = dialogues.length > 0;
  for (const dlg of dialogues) {
    const card = document.createElement("div");
    card.className = "asset-card";
    const body = document.createElement("div");
    body.className = "asset-body";
    if (dlg.signed_url) {
      const audio = document.createElement("audio");
      audio.controls = true;
      audio.src = dlg.signed_url;
      audio.preload = "none";
      body.appendChild(audio);
    }
    const who = document.createElement("p");
    who.className = "scene-who";
    who.textContent = (dlg.participant_names || []).join(" + ");
    body.appendChild(who);
    const transcript = document.createElement("p");
    transcript.className = "asset-prompt";
    transcript.textContent = (dlg.script || []).map((t) => `${t.character_name}: ${t.text}`).join("  ·  ");
    transcript.title = transcript.textContent;
    body.appendChild(transcript);
    const meta = document.createElement("div");
    meta.className = "asset-meta";
    const time = document.createElement("span");
    const parts = [formatTimestamp(dlg.created_at)];
    if (typeof dlg.cost_usd === "number") parts.push(`$${dlg.cost_usd.toFixed(4)}`);
    time.textContent = parts.join(" · ");
    meta.appendChild(time);
    const actions = document.createElement("span");
    actions.className = "asset-actions";
    if (dlg.signed_url) {
      const open = document.createElement("a");
      open.href = dlg.signed_url;
      open.target = "_blank";
      open.rel = "noopener";
      open.textContent = "Open ↗";
      actions.appendChild(open);
    }
    addDetailsButton(actions, dlg);
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "asset-delete";
    remove.textContent = "Delete";
    remove.addEventListener("click", async () => {
      if (!confirm("Delete this dialogue?")) return;
      try { await api(`/audio/dialogue/${dlg.id}`, { method: "DELETE" }); loadDialogues(); toast("Dialogue deleted."); }
      catch (err) { toast(err.message, true); }
    });
    actions.appendChild(remove);
    meta.appendChild(actions);
    body.appendChild(meta);
    card.appendChild(body);
    grid.appendChild(card);
  }
}

/* ---------- Video: animate characters & text-to-video ---------- */

function showVideoView() {
  state.selectedId = null;
  renderCharacterList();
  hideScenesView();
  hideStudioView();
  hideAudioView();
  hideScriptView();
  hideCanvasView();
  hideCanvasTemplatesView();
  el("detail-placeholder").hidden = true;
  el("detail-content").hidden = true;
  el("video-view").hidden = false;
  setActiveNavGroup("video");
  setActiveNavSubitem("video", el("video-source").value);
  populateVideoCharacters();
  populateVideoScenes().then(() => { if (el("video-source").value === "motion-comic") renderMotionComicPanels(); });
  applyVideoSourceUI();
  loadVideos();
}

function hideVideoView() {
  el("video-view").hidden = true;
}

function populateVideoModels() {
  const select = el("video-model");
  select.innerHTML = "";
  if (!state.videoModels.length) {
    const opt = document.createElement("option");
    opt.textContent = "No video models available (GMI key not configured)";
    opt.disabled = true;
    select.appendChild(opt);
    return;
  }
  for (const model of state.videoModels) {
    const option = document.createElement("option");
    option.value = model.slug;
    option.textContent = model.label;
    select.appendChild(option);
  }
}

function selectedVideoModel() {
  return state.videoModels.find((m) => m.slug === el("video-model").value);
}

function applyVideoSourceUI() {
  const isComic = el("video-source").value === "motion-comic";
  el("video-gmi-fields").hidden = isComic;
  el("motion-comic-fields").hidden = !isComic;
  el("generate-video-button").textContent = t(isComic ? "genMotionComicBtn" : "genVideoBtn");
  setActiveNavSubitem("video", el("video-source").value);
  if (isComic) renderMotionComicPanels();
  else applyVideoModelUI();
}

function applyVideoModelUI() {
  const model = selectedVideoModel();
  const needsImage = model ? model.needs_image : false;
  const useScene = needsImage && el("video-source").value === "scene";
  el("video-character-row").hidden = !needsImage || useScene;
  el("video-scene-row").hidden = !needsImage || !useScene;
  // No single fixed voice to lip-sync to when several characters share the
  // frame, so speech only makes sense for the single-character source.
  el("video-speech-field").hidden = !needsImage || useScene;

  const desc = el("video-model-desc");
  if (!model || !model.description) {
    desc.hidden = true;
  } else {
    el("video-model-tag").textContent = model.best_for || (needsImage ? "Character animation" : "Text-to-video");
    el("video-model-text").textContent = model.description;
    desc.hidden = false;
  }

  const hint = el("video-model-hint");
  if (!model) { hint.hidden = true; return; }
  hint.textContent = needsImage ? t("videoHintChar") : (model.audio ? t("videoHintAudio") : t("videoHintText"));
  hint.hidden = false;
}

function populateVideoCharacters() {
  const select = el("video-character");
  const withPortrait = state.characters.filter((c) => c.thumbnail_url);
  select.innerHTML = "";
  if (!withPortrait.length) {
    const opt = document.createElement("option");
    opt.textContent = "No characters with a portrait yet";
    opt.disabled = true;
    select.appendChild(opt);
    return;
  }
  for (const character of withPortrait) {
    const option = document.createElement("option");
    option.value = String(character.id);
    option.textContent = character.name;
    select.appendChild(option);
  }
}

async function populateVideoScenes() {
  const select = el("video-scene");
  select.innerHTML = "";
  try {
    const scenes = await api("/scenes");
    if (!scenes.length) {
      const opt = document.createElement("option");
      opt.textContent = t("videoNoScenes");
      opt.disabled = true;
      select.appendChild(opt);
      return;
    }
    for (const scene of scenes) {
      const option = document.createElement("option");
      option.value = String(scene.id);
      const who = (scene.participant_names || []).join(" + ");
      option.textContent = `${who} — ${scene.prompt.slice(0, 60)}`;
      select.appendChild(option);
    }
  } catch (err) {
    toast(err.message, true);
  }
}

/* ---------- Motion comic: panels + dialogue, no video model ---------- */

const MOTION_COMIC_MIN_PANELS = 2;
const MOTION_COMIC_MAX_PANELS = 12;
let motionComicPanelCount = 0;
let motionComicMusicUrl = null;

function clearMotionComicMusic() {
  motionComicMusicUrl = null;
  el("motion-comic-music").value = "";
  el("motion-comic-music-status").hidden = true;
}

async function uploadMotionComicMusic(file) {
  const data = new FormData();
  data.append("file", file);
  const resp = await fetch("/uploads/music", {
    method: "POST", headers: { "X-Workspace-Id": workspaceId() }, body: data,
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : "Upload failed");
  }
  return resp.json();
}

function motionComicSceneOptions() {
  return [...el("video-scene").options].filter((o) => !o.disabled);
}

function motionComicCharacterOptions() {
  return state.characters.filter((c) => c.voice_id);
}

function addMotionComicPanel() {
  const container = el("motion-comic-panels");
  if (container.children.length >= MOTION_COMIC_MAX_PANELS) return;
  const sceneOptions = motionComicSceneOptions();
  const charOptions = motionComicCharacterOptions();

  const row = document.createElement("div");
  row.className = "motion-comic-panel";

  const sceneSelect = document.createElement("select");
  sceneSelect.className = "mc-scene";
  if (!sceneOptions.length) {
    const opt = document.createElement("option");
    opt.textContent = t("videoNoScenes");
    opt.disabled = true;
    sceneSelect.appendChild(opt);
  } else {
    for (const src of sceneOptions) {
      const opt = document.createElement("option");
      opt.value = src.value;
      opt.textContent = src.textContent;
      sceneSelect.appendChild(opt);
    }
  }

  const charSelect = document.createElement("select");
  charSelect.className = "mc-character";
  if (!charOptions.length) {
    const opt = document.createElement("option");
    opt.textContent = t("needVoiceForDialogue");
    opt.disabled = true;
    charSelect.appendChild(opt);
  } else {
    for (const c of charOptions) {
      const opt = document.createElement("option");
      opt.value = String(c.id);
      opt.textContent = c.name;
      charSelect.appendChild(opt);
    }
  }

  const sceneLabel = document.createElement("label");
  sceneLabel.className = "model-row";
  const sceneSpan = document.createElement("span");
  sceneSpan.className = "model-label";
  sceneSpan.textContent = t("sceneLabel");
  sceneLabel.append(sceneSpan, sceneSelect);

  const charLabel = document.createElement("label");
  charLabel.className = "model-row";
  const charSpan = document.createElement("span");
  charSpan.className = "model-label";
  charSpan.textContent = t("characterLabel");
  charLabel.append(charSpan, charSelect);

  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.className = "button small danger";
  removeBtn.textContent = "✕";
  removeBtn.title = t("removePanel");
  removeBtn.addEventListener("click", () => {
    if (container.children.length <= MOTION_COMIC_MIN_PANELS) { toast(t("toastNeedTwoPanels"), true); return; }
    row.remove();
  });

  const head = document.createElement("div");
  head.className = "mc-panel-head";
  head.append(removeBtn);

  const textInput = document.createElement("textarea");
  textInput.className = "mc-text";
  textInput.rows = 2;
  textInput.maxLength = 500;
  textInput.placeholder = t("phMotionComicLine");

  const captionInput = document.createElement("input");
  captionInput.type = "text";
  captionInput.className = "mc-caption";
  captionInput.maxLength = 200;
  captionInput.placeholder = t("phMotionComicCaption");

  row.append(head, sceneLabel, charLabel, textInput, captionInput);
  container.appendChild(row);
}

function renderMotionComicPanels() {
  const container = el("motion-comic-panels");
  container.innerHTML = "";
  addMotionComicPanel();
  addMotionComicPanel();
}

async function generateMotionComic() {
  if (videoGenerating) return;
  const rows = [...el("motion-comic-panels").children];
  const panels = [];
  for (const row of rows) {
    const sceneId = row.querySelector(".mc-scene").value;
    const characterId = row.querySelector(".mc-character").value;
    const text = row.querySelector(".mc-text").value.trim();
    const caption = row.querySelector(".mc-caption").value.trim();
    if (!sceneId) { toast(t("toastPickSceneFirst"), true); return; }
    if (!characterId) { toast(t("needVoiceForDialogue"), true); return; }
    if (!text) { toast(t("toastWriteScriptFirst"), true); return; }
    panels.push({
      scene_id: Number(sceneId), character_id: Number(characterId), text,
      caption: caption || null,
    });
  }
  if (panels.length < MOTION_COMIC_MIN_PANELS) { toast(t("toastNeedTwoPanels"), true); return; }

  videoGenerating = true;
  el("generate-video-button").disabled = true;
  const status = el("video-status");
  status.classList.remove("error");
  status.innerHTML = `<span class="spinner" aria-hidden="true"></span>${t("generatingMotionComic")}`;
  status.hidden = false;
  try {
    const payload = { panels };
    if (motionComicMusicUrl) payload.music_url = motionComicMusicUrl;
    await api("/videos/motion-comic", {
      method: "POST", headers: { "X-API-Key": apiKey() }, body: JSON.stringify(payload),
    });
    status.hidden = true;
    renderMotionComicPanels();
    clearMotionComicMusic();
    await loadVideos();
    toast(t("toastMotionComicCreated"));
  } catch (err) {
    if (err.status === 401) { status.hidden = true; openKeyDialog(); toast(t("toastNeedKey"), true); }
    else { status.classList.add("error"); status.textContent = err.message; }
  } finally {
    videoGenerating = false;
    el("generate-video-button").disabled = false;
  }
}

function setupVideo() {
  el("video-model").addEventListener("change", applyVideoModelUI);
  el("video-source").addEventListener("change", applyVideoSourceUI);
  el("motion-comic-add-panel").addEventListener("click", () => addMotionComicPanel());
  el("motion-comic-music").addEventListener("change", async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    const musicStatus = el("motion-comic-music-status");
    musicStatus.classList.remove("error");
    musicStatus.textContent = t("uploadingMusic");
    musicStatus.hidden = false;
    try {
      const uploaded = await uploadMotionComicMusic(file);
      motionComicMusicUrl = uploaded.url;
      musicStatus.textContent = `${t("musicAttached")}: ${file.name}`;
    } catch (err) {
      musicStatus.classList.add("error");
      musicStatus.textContent = err.message;
    }
  });
  el("motion-comic-music-clear").addEventListener("click", clearMotionComicMusic);
  el("generate-video-button").addEventListener("click", () => {
    if (el("video-source").value === "motion-comic") generateMotionComic();
    else generateVideo();
  });
}

let videoGenerating = false;

async function generateVideo() {
  if (videoGenerating) return;
  const model = selectedVideoModel();
  if (!model) { toast("No video model available.", true); return; }
  const prompt = el("video-prompt").value.trim();
  if (!prompt) { toast("Describe the motion first.", true); el("video-prompt").focus(); return; }

  const payload = {
    prompt,
    model: model.slug,
    duration: Number(el("video-duration").value),
    aspect_ratio: el("video-aspect").value,
  };
  if (model.needs_image) {
    if (el("video-source").value === "scene") {
      const sid = el("video-scene").value;
      if (!sid) { toast(t("toastPickSceneFirst"), true); return; }
      payload.scene_id = Number(sid);
    } else {
      const cid = el("video-character").value;
      if (!cid) { toast("Pick a character with a portrait first.", true); return; }
      payload.character_id = Number(cid);
      const speech = el("video-speech").value.trim();
      if (speech) payload.speech = speech;
    }
  }

  videoGenerating = true;
  el("generate-video-button").disabled = true;
  const progress = el("video-progress");
  try {
    const job = await api("/videos", {
      method: "POST", headers: { "X-API-Key": apiKey() }, body: JSON.stringify(payload),
    });
    progress.hidden = false;
    el("video-progress-label").textContent = t("videoRendering");
    while (true) {
      await new Promise((r) => setTimeout(r, 4000));
      const status = await api(`/videos/${job.id}`);
      if (["done", "error"].includes(status.status)) {
        progress.hidden = true;
        if (status.status === "error") toast(status.error || "Video generation failed.", true);
        else { el("video-prompt").value = ""; toast(t("toastVideoSaved")); }
        await loadVideos();
        break;
      }
    }
  } catch (err) {
    progress.hidden = true;
    if (err.status === 401) { openKeyDialog(); toast("Generation needs a valid API key.", true); }
    else { toast(err.message, true); }
  } finally {
    videoGenerating = false;
    el("generate-video-button").disabled = false;
  }
}

async function loadVideos() {
  try {
    renderVideos(await api("/videos"));
  } catch (err) {
    toast(err.message, true);
  }
}

function renderVideos(videos) {
  const grid = el("video-grid");
  grid.innerHTML = "";
  el("video-empty").hidden = videos.length > 0;
  for (const video of videos) {
    const card = document.createElement("div");
    card.className = "asset-card";
    if (video.status === "done" && video.signed_url) {
      const player = document.createElement("video");
      player.controls = true;
      player.src = video.signed_url;
      player.preload = "metadata";
      player.playsInline = true;
      card.appendChild(player);
    } else {
      const ph = document.createElement("div");
      ph.className = "video-placeholder";
      ph.innerHTML = video.status === "error"
        ? '<span class="video-ph-error">✕ generation failed</span>'
        : '<span class="spinner" aria-hidden="true"></span><span>rendering…</span>';
      card.appendChild(ph);
    }
    const body = document.createElement("div");
    body.className = "asset-body";
    if (video.character_name) {
      const who = document.createElement("p");
      who.className = "scene-who";
      who.textContent = video.character_name;
      body.appendChild(who);
    }
    const prompt = document.createElement("p");
    prompt.className = "asset-prompt";
    prompt.textContent = video.kind === "motion_comic" && video.script
      ? video.script.map((t) => `${t.character_name}: ${t.text}`).join("  ·  ")
      : video.prompt;
    prompt.title = prompt.textContent;
    body.appendChild(prompt);
    const meta = document.createElement("div");
    meta.className = "asset-meta";
    const time = document.createElement("span");
    const parts = [formatTimestamp(video.created_at)];
    if (video.kind === "motion_comic") parts.push(t("videoSourceMotionComic"));
    else if (video.model) parts.push(video.model);
    if (video.duration) parts.push(`${video.duration}s`);
    if (video.aspect_ratio) parts.push(video.aspect_ratio);
    time.textContent = parts.join(" · ");
    meta.appendChild(time);
    const actions = document.createElement("span");
    actions.className = "asset-actions";
    if (video.status === "done" && video.signed_url) {
      const open = document.createElement("a");
      open.href = video.signed_url;
      open.target = "_blank";
      open.rel = "noopener";
      open.textContent = "Open ↗";
      actions.appendChild(open);
    }
    addDetailsButton(actions, video);
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "asset-delete";
    remove.textContent = "Delete";
    remove.addEventListener("click", async () => {
      if (!confirm("Delete this video?")) return;
      try { await api(`/videos/${video.id}`, { method: "DELETE" }); loadVideos(); toast("Video deleted."); }
      catch (err) { toast(err.message, true); }
    });
    actions.appendChild(remove);
    meta.appendChild(actions);
    body.appendChild(meta);
    card.appendChild(body);
    grid.appendChild(card);
  }
}

/* ---------- Idea → Script ---------- */

function showScriptView() {
  state.selectedId = null;
  renderCharacterList();
  hideScenesView();
  hideStudioView();
  hideAudioView();
  hideVideoView();
  hideScriptView();
  hideCanvasView();
  hideCanvasTemplatesView();
  el("detail-placeholder").hidden = true;
  el("detail-content").hidden = true;
  el("script-view").hidden = false;
  el("open-script").classList.add("active");
  setActiveNavGroup(null);
  renderScriptCast();
  loadScripts();
}

function hideScriptView() {
  el("script-view").hidden = true;
  el("open-script").classList.remove("active");
}

function renderScriptCast() {
  const box = el("script-cast");
  box.innerHTML = "";
  if (!state.characters.length) {
    box.innerHTML = `<p class="empty-note">${t("noCharacters")}</p>`;
    return;
  }
  for (const character of state.characters) {
    const label = document.createElement("label");
    label.className = "participant";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = String(character.id);
    const name = document.createElement("span");
    name.textContent = character.name;
    label.append(cb, name);
    box.appendChild(label);
  }
}

let scriptGenerating = false;

async function generateScript() {
  if (scriptGenerating) return;
  const idea = el("script-idea").value.trim();
  if (!idea) { toast(t("scriptIdeaPh"), true); el("script-idea").focus(); return; }

  const characterIds = [...document.querySelectorAll("#script-cast input:checked")].map((c) => Number(c.value));
  scriptGenerating = true;
  el("generate-script-button").disabled = true;
  const status = el("script-status");
  status.classList.remove("error");
  status.innerHTML = `<span class="spinner" aria-hidden="true"></span>${t("scriptGenerating")}`;
  status.hidden = false;
  try {
    const script = await api("/scripts", {
      method: "POST",
      headers: { "X-API-Key": apiKey() },
      body: JSON.stringify({
        idea,
        format: el("script-format").value,
        length: el("script-length").value,
        character_ids: characterIds,
      }),
    });
    status.hidden = true;
    showScriptOutput(script.content);
    await loadScripts();
  } catch (err) {
    if (err.status === 401) { status.hidden = true; openKeyDialog(); toast(t("scriptIdeaPh"), true); }
    else { status.classList.add("error"); status.textContent = err.message; }
  } finally {
    scriptGenerating = false;
    el("generate-script-button").disabled = false;
  }
}

function showScriptOutput(content) {
  el("script-text").textContent = content;
  el("script-output").hidden = false;
  el("script-output").scrollIntoView({ block: "nearest", behavior: "smooth" });
}

async function copyText(text) {
  try { await navigator.clipboard?.writeText(text); toast(t("scriptCopied")); }
  catch { toast(text.slice(0, 0) || "…", true); }
}

async function loadScripts() {
  try {
    renderScripts(await api("/scripts"));
  } catch (err) {
    toast(err.message, true);
  }
}

const SCRIPT_FORMAT_LABEL = { story: "fmtStory", video: "fmtVideo", manga: "fmtManga", dialogue: "fmtDialogue" };

function renderScripts(scripts) {
  const list = el("script-list");
  list.innerHTML = "";
  el("script-empty").hidden = scripts.length > 0;
  for (const script of scripts) {
    const card = document.createElement("div");
    card.className = "script-card";

    const head = document.createElement("div");
    head.className = "script-card-head";
    const idea = document.createElement("span");
    idea.className = "script-card-idea";
    idea.textContent = script.idea;
    const tag = document.createElement("span");
    tag.className = "script-card-tag";
    tag.textContent = t(SCRIPT_FORMAT_LABEL[script.format] || "scriptResult").split(" —")[0];
    head.append(idea, tag);
    card.appendChild(head);

    const pre = document.createElement("pre");
    pre.className = "script-card-text";
    pre.textContent = script.content;
    card.appendChild(pre);

    const meta = document.createElement("div");
    meta.className = "asset-meta";
    const time = document.createElement("span");
    time.textContent = formatTimestamp(script.created_at);
    meta.appendChild(time);
    const actions = document.createElement("span");
    actions.className = "asset-actions";
    const copy = document.createElement("button");
    copy.type = "button";
    copy.className = "asset-delete";
    copy.textContent = t("wsCopy");
    copy.addEventListener("click", () => copyText(script.content));
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "asset-delete";
    remove.textContent = "Delete";
    remove.addEventListener("click", async () => {
      if (!confirm("Delete this script?")) return;
      try { await api(`/scripts/${script.id}`, { method: "DELETE" }); loadScripts(); }
      catch (err) { toast(err.message, true); }
    });
    actions.append(copy, remove);
    meta.appendChild(actions);
    card.appendChild(meta);
    list.appendChild(card);
  }
}

function setupScript() {
  el("open-script").addEventListener("click", showScriptView);
  el("generate-script-button").addEventListener("click", generateScript);
  el("script-copy").addEventListener("click", () => copyText(el("script-text").textContent));
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
  setupDetailDialog();
  refreshKeyButton();
  el("generate-image-button").addEventListener("click", generateImage);
  setupImageComposer();
  el("gen-mode").addEventListener("change", updateModeUI);
  el("gen-count").addEventListener("input", updateCostEstimate);
  el("image-prompt").addEventListener("input", () => { if (currentMode() === "story") updateCostEstimate(); });
  el("batch-cancel").addEventListener("click", cancelBatch);
  el("portrait-pick-cancel").addEventListener("click", cancelPortraitBatch);
  el("portrait-pick-close").addEventListener("click", () => el("portrait-pick-dialog").close());
  el("portrait-pick-keep-all").addEventListener("click", () => {
    el("portrait-pick-dialog").close();
    toast(t("portraitPickKeptAll"));
  });
  document.querySelectorAll('input[name="quality"]').forEach((r) => r.addEventListener("change", updateCostEstimate));
  updateModeUI();
  el("create-voice-preview").addEventListener("click", () => previewPickerVoice("create-voice", "create-voice-preview"));
  el("edit-voice-preview").addEventListener("click", () => previewPickerVoice("edit-voice", "edit-voice-preview"));
  setupNavGroups();
  setupStudio();
  setupAudio();
  setupVideo();
  setupScript();
  setupWorkspace();
  applyI18n();
  el("lang-toggle").addEventListener("click", () => setLang(lang === "de" ? "en" : "de"));
  el("landing-create").addEventListener("click", () => {
    const form = el("create-form");
    form.hidden = false;
    el("create-name").focus();
    form.scrollIntoView({ block: "center", behavior: "smooth" });
  });
  ensureWorkspace().then(() =>
    Promise.all([loadImageModels(), loadVoices()])
      .catch((err) => toast(err.message, true))
      .finally(() => loadCharacters().catch((err) => toast(err.message, true)))
  );
}

init();
