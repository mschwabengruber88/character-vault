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
    landingSub: "Character Vault turns a single character profile into a full library of images, scenes, voiceover and video — keeping the same face, style and identity across all of them. No model training, no LoRA.",
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
    navScenes: "Scenes / Story",
    navStudio: "Studio — backgrounds & photo art",
    navAudio: "Audio — narration & voiceover",
    navVideo: "Video — animate characters",
    scenesTitle: "Scenes & Storytelling",
    scenesDesc: "Bring two or more of your characters together in one image — manga panels, picture-book pages. Each keeps their own look via Nano Banana multi-character composition.",
    studioTitle: "Studio",
    studioDesc: "Generate images without a character — free artistic photo art like Midjourney, or empty background/scene plates. Same prompt builder, no identity lock.",
    audioTitle: "Audio",
    audioDesc: "Turn a script into spoken audio — narration, voiceover, dialogue. Pick a catalog voice, or bring your own ElevenLabs voice by its Voice ID.",
    videoTitle: "Video",
    videoDesc: "Bring a character to life — animate one of their portraits into a short clip (identity held via image-to-video), or generate video straight from a prompt.",
    wsGateTitle: "Your workspace",
    wsGateIntro: "Character Vault is multi-tenant: your characters, images, audio and videos live in your own private workspace. Create one, or open an existing workspace with its token.",
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
    navScript: "Idea → Script",
    scriptTitle: "Idea → Script",
    scriptDesc: "Describe an idea in a sentence and get a ready-to-shoot script. A story script drops straight into the Story image mode — one line becomes one panel.",
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
    imgGenTitle: "Image generation",
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
    voiceTitle: "Voice line",
    ttsHint: "Genblaze TTS → Backblaze B2",
    phVoiceText: "What should the character say?",
    voiceLabel: "Voice",
    genVoiceBtn: "Generate voice line",
    assetsHeading: "Assets",
    assetsEmpty: "No assets yet — generate a portrait or voice line above.",
    filterAnyGender: "Any gender",
    filterFemale: "Female",
    filterMale: "Male",
    filterNeutral: "Neutral",
    filterAnyAge: "Any age",
    filterYoung: "Young / teen",
    filterAdult: "Adult",
    filterMature: "Mature",
    newScene: "New scene",
    sceneHint: "Nano Banana multi-character composition → Backblaze B2",
    scenePick: "Pick the characters in the scene (2–4):",
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
    audioCatalog: "Catalog voice",
    audioCustom: "Your ElevenLabs voice (by ID)",
    voiceIdLabel: "Voice ID",
    phVoiceId: "ElevenLabs Voice ID, e.g. 21m00Tcm4TlvDq8ikWAM",
    voiceIdHint: "Copy the Voice ID from your ElevenLabs voice library. Requires an ElevenLabs plan reachable from the server — otherwise it falls back to an OpenAI voice.",
    genAudioBtn: "Generate audio",
    yourAudio: "Your audio",
    audioEmpty: "Nothing here yet — write a line and generate.",
    characterLabel: "Character",
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
    keyDialogTitle: "Generation API key",
    keyDialogBody: "Portrait and voice generation call paid provider APIs, so they require the shared key. It is stored only in this browser.",
    phKeyInput: "X-API-Key value",
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
    toastVoiceSaved: "Voice line stored in the vault.",
    toastImageSaved: "Image stored in the vault.",
    toastAudioSaved: "Audio stored in the vault.",
    toastVideoSaved: "Video stored in the vault.",
    toastSceneCreated: "Scene created.",
    toastDeleted: "Deleted.",
    toastNeedKey: "Generation needs a valid API key.",
    toastDescribeFirst: "Describe the character first.",
    generatingImage: "Generating portrait… this usually takes 15–60 seconds. The asset is uploaded to Backblaze B2 with a provenance manifest.",
    generatingVoice: "Generating voice line… this usually takes 15–60 seconds.",
    generatingAudio: "Generating audio… 15–60 seconds. Stored on Backblaze B2 with a provenance manifest.",
  },
  de: {
    provenanceNote: "Jedes Asset auf Backblaze B2 gespeichert – mit verifiziertem Herkunftsnachweis",
    apiKey: "API-Schlüssel",
    landingEyebrow: "Backblaze Generative AI Media Hackathon",
    landingTitle: "Ein Charakter. Jedes Medium. Immer konsistent.",
    landingSub: "Character Vault macht aus einem einzigen Charakter-Profil eine ganze Bibliothek aus Bildern, Szenen, Sprachausgabe und Video – mit demselben Gesicht, Stil und derselben Identität über alles hinweg. Kein Modell-Training, kein LoRA.",
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
    navScenes: "Szenen / Story",
    navStudio: "Studio – Hintergründe & Foto-Art",
    navAudio: "Audio – Erzählung & Voiceover",
    navVideo: "Video – Charaktere animieren",
    scenesTitle: "Szenen & Storytelling",
    scenesDesc: "Bring zwei oder mehr Charaktere in einem Bild zusammen – Manga-Panels, Bilderbuchseiten. Jeder behält sein Aussehen dank Nano-Banana-Multi-Charakter-Komposition.",
    studioTitle: "Studio",
    studioDesc: "Bilder ohne Charakter generieren – freie künstlerische Foto-Art wie bei Midjourney oder leere Hintergrund-/Szenen-Plates. Derselbe Prompt-Baukasten, ohne Identitäts-Lock.",
    audioTitle: "Audio",
    audioDesc: "Mach aus einem Skript gesprochenes Audio – Erzählung, Voiceover, Dialog. Wähle eine Katalog-Stimme oder bring deine eigene ElevenLabs-Stimme per Voice-ID mit.",
    videoTitle: "Video",
    videoDesc: "Erwecke einen Charakter zum Leben – animiere eines seiner Porträts zu einem kurzen Clip (Identität via Image-to-Video gehalten) oder generiere Video direkt aus einem Prompt.",
    wsGateTitle: "Dein Workspace",
    wsGateIntro: "Character Vault ist mandantenfähig: Deine Charaktere, Bilder, Audios und Videos liegen in deinem eigenen privaten Workspace. Erstelle einen – oder öffne einen bestehenden mit seinem Token.",
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
    navScript: "Idee → Skript",
    scriptTitle: "Idee → Skript",
    scriptDesc: "Beschreibe eine Idee in einem Satz und erhalte ein drehfertiges Skript. Ein Story-Skript fließt direkt in den Story-Bildmodus – eine Zeile wird ein Panel.",
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
    imgGenTitle: "Bildgenerierung",
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
    voiceTitle: "Sprachzeile",
    ttsHint: "Genblaze TTS → Backblaze B2",
    phVoiceText: "Was soll der Charakter sagen?",
    voiceLabel: "Stimme",
    genVoiceBtn: "Sprachzeile generieren",
    assetsHeading: "Assets",
    assetsEmpty: "Noch keine Assets – generiere oben ein Porträt oder eine Sprachzeile.",
    filterAnyGender: "Beliebiges Geschlecht",
    filterFemale: "Weiblich",
    filterMale: "Männlich",
    filterNeutral: "Neutral",
    filterAnyAge: "Beliebiges Alter",
    filterYoung: "Jung / Teenager",
    filterAdult: "Erwachsen",
    filterMature: "Reif",
    newScene: "Neue Szene",
    sceneHint: "Nano-Banana-Multi-Charakter-Komposition → Backblaze B2",
    scenePick: "Wähle die Charaktere der Szene (2–4):",
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
    audioCatalog: "Katalog-Stimme",
    audioCustom: "Deine ElevenLabs-Stimme (per ID)",
    voiceIdLabel: "Voice-ID",
    phVoiceId: "ElevenLabs Voice-ID, z. B. 21m00Tcm4TlvDq8ikWAM",
    voiceIdHint: "Kopiere die Voice-ID aus deiner ElevenLabs-Stimmen-Bibliothek. Benötigt einen vom Server erreichbaren ElevenLabs-Plan – sonst greift eine OpenAI-Stimme.",
    genAudioBtn: "Audio generieren",
    yourAudio: "Deine Audios",
    audioEmpty: "Noch nichts hier – schreibe eine Zeile und generiere.",
    characterLabel: "Charakter",
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
    keyDialogTitle: "Generierungs-API-Schlüssel",
    keyDialogBody: "Bild- und Sprachgenerierung rufen kostenpflichtige Anbieter-APIs auf und brauchen daher den gemeinsamen Schlüssel. Er wird nur in diesem Browser gespeichert.",
    phKeyInput: "X-API-Key-Wert",
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
    toastVoiceSaved: "Sprachzeile im Vault gespeichert.",
    toastImageSaved: "Bild im Vault gespeichert.",
    toastAudioSaved: "Audio im Vault gespeichert.",
    toastVideoSaved: "Video im Vault gespeichert.",
    toastSceneCreated: "Szene erstellt.",
    toastDeleted: "Gelöscht.",
    toastNeedKey: "Generierung braucht einen gültigen API-Schlüssel.",
    toastDescribeFirst: "Beschreibe zuerst den Charakter.",
    generatingImage: "Porträt wird generiert … dauert meist 15–60 Sekunden. Das Asset wird mit Herkunftsnachweis auf Backblaze B2 hochgeladen.",
    generatingVoice: "Sprachzeile wird generiert … dauert meist 15–60 Sekunden.",
    generatingAudio: "Audio wird generiert … 15–60 Sekunden. Auf Backblaze B2 mit Herkunftsnachweis gespeichert.",
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

function workspaceId() {
  return localStorage.getItem(WORKSPACE_STORAGE) || "";
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
      if (ws) { setWorkspaceChip(ws); return; }
      localStorage.removeItem(WORKSPACE_STORAGE);
    }
    await new Promise((resolve) => {
      workspaceResolve = resolve;
      el("ws-gate-error").hidden = true;
      el("ws-name").value = "";
      el("ws-token").value = "";
      el("workspace-gate").showModal();
    });
  })();
}

function gateError(key) {
  const node = el("ws-gate-error");
  node.textContent = t(key);
  node.hidden = false;
}

function adoptWorkspace(ws) {
  localStorage.setItem(WORKSPACE_STORAGE, ws.id);
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
}

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

function previewVoice(selectId, buttonId) {
  const value = el(selectId).value;
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

function previewSelectedVoice() {
  previewVoice("voice-select", "voice-preview");
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
    method: "POST", headers: { "X-API-Key": apiKey(), "X-Workspace-Id": workspaceId() }, body: data,
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

function updateModeUI() {
  const meta = MODE_META[currentMode()];
  el("count-row").hidden = !meta.counted;
  el("image-prompt").placeholder = t(meta.phKey);
  el("image-prompt").rows = currentMode() === "story" ? 5 : 2;
  el("mode-hint").textContent = meta.hintKey ? t(meta.hintKey) : "";
  el("mode-hint").hidden = !meta.hintKey;
  el("generate-image-button").textContent = t(meta.buttonKey);
  updateCostEstimate();
}

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

async function generateImage() {
  if (state.generating || !state.selectedId) return;
  const input = el("image-prompt");
  const value = input.value.trim();
  if (!value) { toast(t("toastDescribeFirst"), true); input.focus(); return; }
  if (!apiKey()) { openKeyDialog(); return; }

  const mode = currentMode();
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
      await api(`/characters/${state.selectedId}/generate/image`, {
        method: "POST", headers: { "X-API-Key": apiKey() }, body: JSON.stringify(payload),
      });
      input.value = "";
      setGenerating(false);
      await selectCharacter(state.selectedId);
      toast(t("toastPortraitSaved"));
    } catch (err) {
      if (err.status === 401) { setGenerating(false); openKeyDialog(); toast(t("toastNeedKey"), true); }
      else { setGenerating(false, err.message, true); }
    }
    return;
  }

  await runBatch({ ...payload, mode, count: plannedCount() });
}

let batchCancelId = null;

async function runBatch(payload) {
  setGenerating(true, "Starting the batch…");
  const progress = el("batch-progress");
  try {
    const job = await api(`/characters/${state.selectedId}/generate/batch`, {
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
      await selectCharacter(state.selectedId);  // stream new frames into the gallery
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

async function generateVoice() {
  if (state.generating || !state.selectedId) return;
  const input = el("voice-text");
  const value = input.value.trim();
  if (!value) { toast("Enter a line for the character to say.", true); input.focus(); return; }
  if (!apiKey()) { openKeyDialog(); return; }

  setGenerating(true, t("generatingVoice"));
  try {
    await api(`/characters/${state.selectedId}/generate/voice`, {
      method: "POST", headers: { "X-API-Key": apiKey() }, body: JSON.stringify({ text: value }),
    });
    input.value = "";
    setGenerating(false);
    await selectCharacter(state.selectedId);
    toast(t("toastVoiceSaved"));
  } catch (err) {
    if (err.status === 401) { setGenerating(false); openKeyDialog(); toast(t("toastNeedKey"), true); }
    else { setGenerating(false, err.message, true); }
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
  hideStudioView();
  hideAudioView();
  hideVideoView();
  hideScriptView();
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
    toast(t("toastSceneCreated"));
  } catch (err) {
    if (err.status === 401) { status.hidden = true; openKeyDialog(); toast("Scene generation needs a valid API key.", true); }
    else { status.classList.add("error"); status.textContent = err.message; }
  } finally {
    sceneGenerating = false;
    el("generate-scene-button").disabled = false;
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
  el("detail-placeholder").hidden = true;
  el("detail-content").hidden = true;
  el("studio-view").hidden = false;
  el("open-studio").classList.add("active");
  applyStudioModelUI();
  updateStudioCost();
  loadStudio();
}

function hideStudioView() {
  el("studio-view").hidden = true;
  el("open-studio").classList.remove("active");
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
  el("studio-mode-hint").textContent = t(STUDIO_MODE_HINT[mode]);
}

function setupStudio() {
  studioComposer = createComposer(el("studio-composer"), refreshStudioPreview);
  el("studio-composer-reset").addEventListener("click", () => studioComposer.reset());
  el("studio-prompt").addEventListener("input", refreshStudioPreview);
  el("studio-model").addEventListener("change", applyStudioModelUI);
  el("open-studio").addEventListener("click", showStudioView);
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
  if (!apiKey()) { openKeyDialog(); return; }

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

let audioSource = "catalog";

function showAudioView() {
  state.selectedId = null;
  renderCharacterList();
  hideScenesView();
  hideStudioView();
  hideVideoView();
  hideScriptView();
  el("detail-placeholder").hidden = true;
  el("detail-content").hidden = true;
  el("audio-view").hidden = false;
  el("open-audio").classList.add("active");
  renderAudioVoices();
  loadAudio();
}

function hideAudioView() {
  el("audio-view").hidden = true;
  el("open-audio").classList.remove("active");
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

function setAudioSource(source) {
  audioSource = source;
  document.querySelectorAll(".audio-source-btn").forEach((b) =>
    b.classList.toggle("active", b.dataset.source === source));
  el("audio-catalog").hidden = source !== "catalog";
  el("audio-custom").hidden = source !== "custom";
}

function setupAudio() {
  el("open-audio").addEventListener("click", showAudioView);
  el("generate-audio-button").addEventListener("click", generateAudioClip);
  el("audio-filter-gender").addEventListener("change", renderAudioVoices);
  el("audio-filter-age").addEventListener("change", renderAudioVoices);
  el("audio-voice-preview").addEventListener("click", () => previewVoice("audio-voice-select", "audio-voice-preview"));
  document.querySelectorAll(".audio-source-btn").forEach((b) =>
    b.addEventListener("click", () => setAudioSource(b.dataset.source)));
  setAudioSource("catalog");
}

let audioGenerating = false;

async function generateAudioClip() {
  if (audioGenerating) return;
  const text = el("audio-text").value.trim();
  if (!text) { toast("Write the line to speak first.", true); el("audio-text").focus(); return; }
  if (!apiKey()) { openKeyDialog(); return; }

  let provider, voiceId;
  if (audioSource === "custom") {
    provider = "elevenlabs";
    voiceId = el("audio-custom-id").value.trim();
    if (!voiceId) { toast("Enter your ElevenLabs Voice ID.", true); el("audio-custom-id").focus(); return; }
  } else {
    const value = el("audio-voice-select").value;
    if (!value) { toast("Pick a voice first.", true); return; }
    const parts = value.split(":");
    provider = parts[0];
    voiceId = parts.slice(1).join(":");
  }

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

/* ---------- Video: animate characters & text-to-video ---------- */

function showVideoView() {
  state.selectedId = null;
  renderCharacterList();
  hideScenesView();
  hideStudioView();
  hideAudioView();
  hideScriptView();
  el("detail-placeholder").hidden = true;
  el("detail-content").hidden = true;
  el("video-view").hidden = false;
  el("open-video").classList.add("active");
  populateVideoCharacters();
  applyVideoModelUI();
  loadVideos();
}

function hideVideoView() {
  el("video-view").hidden = true;
  el("open-video").classList.remove("active");
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

function applyVideoModelUI() {
  const model = selectedVideoModel();
  const needsImage = model ? model.needs_image : false;
  el("video-character-row").hidden = !needsImage;

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

function setupVideo() {
  el("open-video").addEventListener("click", showVideoView);
  el("video-model").addEventListener("change", applyVideoModelUI);
  el("generate-video-button").addEventListener("click", generateVideo);
}

let videoGenerating = false;

async function generateVideo() {
  if (videoGenerating) return;
  const model = selectedVideoModel();
  if (!model) { toast("No video model available.", true); return; }
  const prompt = el("video-prompt").value.trim();
  if (!prompt) { toast("Describe the motion first.", true); el("video-prompt").focus(); return; }
  if (!apiKey()) { openKeyDialog(); return; }

  const payload = {
    prompt,
    model: model.slug,
    duration: Number(el("video-duration").value),
    aspect_ratio: el("video-aspect").value,
  };
  if (model.needs_image) {
    const cid = el("video-character").value;
    if (!cid) { toast("Pick a character with a portrait first.", true); return; }
    payload.character_id = Number(cid);
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
    prompt.textContent = video.prompt;
    prompt.title = video.prompt;
    body.appendChild(prompt);
    const meta = document.createElement("div");
    meta.className = "asset-meta";
    const time = document.createElement("span");
    const parts = [formatTimestamp(video.created_at)];
    if (video.model) parts.push(video.model);
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
  el("detail-placeholder").hidden = true;
  el("detail-content").hidden = true;
  el("script-view").hidden = false;
  el("open-script").classList.add("active");
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
  if (!apiKey()) { openKeyDialog(); return; }

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
  refreshKeyButton();
  el("generate-image-button").addEventListener("click", generateImage);
  el("generate-voice-button").addEventListener("click", generateVoice);
  setupImageComposer();
  el("gen-mode").addEventListener("change", updateModeUI);
  el("gen-count").addEventListener("input", updateCostEstimate);
  el("image-prompt").addEventListener("input", () => { if (currentMode() === "story") updateCostEstimate(); });
  el("batch-cancel").addEventListener("click", cancelBatch);
  document.querySelectorAll('input[name="quality"]').forEach((r) => r.addEventListener("change", updateCostEstimate));
  updateModeUI();
  el("voice-select").addEventListener("change", saveVoice);
  el("voice-preview").addEventListener("click", previewSelectedVoice);
  el("filter-gender").addEventListener("change", renderVoiceOptions);
  el("filter-age").addEventListener("change", renderVoiceOptions);
  el("open-scenes").addEventListener("click", showScenesView);
  el("generate-scene-button").addEventListener("click", generateScene);
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
