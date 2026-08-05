# Demo-Video „Lena & Fips"

Briefing für ein kurzes Werbevideo, das Loomina an seiner stärksten Stelle
zeigt. Gedacht als Startpunkt für eine frische Sitzung — alles Nötige steht
hier, es braucht keinen Rückgriff auf ältere Gespräche.

## Warum dieses Konzept

Der stärkste Werbemoment ist gemischtes Medium: **eine reale Person und eine
gezeichnete Figur im selben Bild, jede in ihrem eigenen Stil.** Das versteht
ein Zuschauer in drei Sekunden ohne Erklärung — es ist die Pumuckl-Formel —
und konkurrierende Werkzeuge scheitern sichtbar daran, weil sie beide Figuren
zu einem Einheitsstil verrechnen. Ein Demo, das bloß konsistente Charaktere
zeigt, wirkt dagegen austauschbar.

Die dafür nötige Logik steckt in `SCENE_INSTRUCTION` (`app/pipelines.py`):
Jede Figur behält Medium und Stil ihrer eigenen Referenz, geteilt werden nur
Licht, Perspektive, Maßstab und Schatten.

## Die zwei Charaktere

Porträt-Prompts auf Englisch — die Bildmodelle reagieren darauf deutlich
präziser als auf Deutsch.

**Lena** — reale Illustratorin, fotorealistisch:

```
Photograph of a woman in her late twenties, short dark tousled hair, warm
brown eyes, small ink stains on her fingers, worn denim shirt, sitting at a
wooden desk under a single warm lamp at night. Natural photography, soft
shallow depth of field, no retouching, visible skin texture.
```

**Fips** — ihre gezeichnete Figur, flache 2D-Illustration:

```
A small round raven character from a children's picture book. Flat 2D ink
illustration: visible brush-pen linework, flat watercolour washes, matte
paper texture, slightly uneven hand-drawn edges. Deep blue-black feathers,
one crooked tail feather, large friendly eyes. NOT 3D, no CGI, no sculpted
volume, no glossy highlights.
```

Der letzte Satz ist wichtig: Ohne die ausdrückliche Absage an 3D rendern die
Modelle „cartoon" gern als Pixar-CGI. Genau dafür gibt es die 2D-Regel in
`SCENE_INSTRUCTION` — im Charakter-Prompt gehört sie trotzdem wiederholt.

Aus den vier Varianten wurde eine gewählt, die Fips **Strohhut und gelbe Weste**
gibt. Das steht so nicht im Prompt, ist aber bewusst behalten: Zwei kräftige,
unverwechselbare Requisiten geben dem Identitätsmodell etwas zum Festhalten und
machen ihn über Panels hinweg wiedererkennbar. Wer den Hut nicht will, muss ihn
in den Charakter-Prompt hinein *ausschließen* — sonst zieht ihn die Referenz in
jedes Folgebild.

## Vier Szenen, etwa 30 Sekunden

1. **Nur Lena** — sie zeichnet allein, spät, Lampenlicht. Etabliert sie als
   echten Menschen.
2. **Der Moment** — Fips sitzt auf ihrem Skizzenblock und schaut sie an. Flache
   Tuschezeichnung auf fotorealem Papier, gleiches Licht, echter Schatten.
   *Das ist der Shot, der das Produkt verkauft.*
3. **Nächtliche Straße** — beide unterwegs, Fips neben ihrer Schulter, dieselbe
   kalte Straßenbeleuchtung auf beiden.
4. **Schluss** — Lena eingeschlafen am Tisch, Fips zieht ihr eine Buchseite über
   die Schulter.

Szene 2 als Prompt:

```
Lena sits at her desk at night, looking down with a small surprised smile.
Fips perches on her open sketchbook, looking up at her. Warm lamp light from
the left falls on both, each casting a shadow on the desk.
```

Szenen 1 und 3 tragen die Geschichte, 2 und 4 die Werbung.

**Das Medium muss im Szenen-Prompt stehen.** Mit dem Prompt oben allein kam
Fips fotoreal zurück — echte Federn, gerendertes Licht, Hut und Weste weg.
`SCENE_INSTRUCTION` reicht dafür nicht. Erst dieser Zusatz hielt den Stil:

```
Lena stays a real photograph; Fips stays a FLAT 2D ink-and-watercolour
drawing with visible outlines and flat colour - no real feathers, no 3D
volume, no rendered lighting on him.
```

Zwei Fallstricke dabei: Das Szenenfeld nimmt **maximal 500 Zeichen** (darüber
antwortet die API mit 422), und Bindestriche statt Gedankenstriche schreiben.

## Die Comic-Seite: „Wie die Idee für Fips entstand"

Aus vier Story-Panels wird eine Seite. Das ist der zweite Werbeblock nach der
Mixed-Media-Szene — er zeigt, dass aus einem Charakter nicht nur Einzelbilder
werden, sondern eine erzählte Seite.

Erzeugt über **Bild → Story-Serie** mit **Lena** als gewähltem Charakter (nicht
Fips): Sie ist in jedem Panel dieselbe Person, und die Geschichte trägt Fips
ohnehin erst am Ende als fertige Zeichnung herein. Eine Zeile pro Panel:

```
Photoreal Lena walks home through rain at night; a scruffy raven watches her from a lamppost.
Photoreal Lena at her desk, sketching that raven from memory, crumpled failed attempts around her.
Her pencil adds a straw hat and a yellow waistcoat to the flat 2D ink drawing of the raven, and she smiles.
Photoreal Lena asleep over her sketchbook; the flat 2D drawn raven Fips stands on the page and looks up at her, warm lamp light.
```

`build_batch_prompts` stellt jeder Zeile „A single illustrated panel for this
story moment" voran — deshalb steht *photoreal* ausdrücklich in den Zeilen, sonst
zieht der Vorspann auch Lena ins Gezeichnete.

Zusammengesetzt wird die Seite im **Canvas** mit dem Manga-Layout **2×2**
(900×900). Sprechblasen kommen über „+ Sprechblase", Doppelklick bearbeitet den
Text. Die Panels liegen als Platzhalter im Raster; ein Klick auf ein Feld macht
es aktiv, dann wird das Bild hineingesetzt.

## Video

Szene 2 und 4 mit **Kling 2.1 (image→video)** animieren — das Modell hält die
Identität. Szenen 1 und 3 als Standbilder mit langsamem Zoom dazwischen
schneiden. Spart Rechenzeit und wirkt trotzdem wie ein Film.

## Stimmen

Falls gesprochen wird: für deutsche Sprache **Johanna** oder **Josef**
(Inworld, echte deutsche Stimmen). Keine englische Stimme deutschen Text lesen
lassen — das war der Grund, warum die Auswahl vorher schlecht klang.

## Was beim Umsetzen zu beachten ist

- **Porträts:** Beim Anlegen eines Charakters erzeugt die App automatisch vier
  Varianten zur Auswahl; die gewählte bleibt als Referenz. Sie entstehen in
  Draft-Qualität. Für ein Werbevideo lohnt es sich, das gewählte Referenzbild
  anschließend noch einmal in *final* nachzugenerieren.
- **KI-Kennzeichnung:** Im Demo trägt **Lena das sichtbare „✦ AI"-Wasserzeichen**,
  **Fips nicht**. Das ist kein Zufall, sondern das Argument: Ein fotorealistischer
  Mensch ist genau der Fall, den man kennzeichnen muss; eine gezeichnete Figur gibt
  sich selbst als Zeichnung zu erkennen und trägt den Nachweis unsichtbar im
  Manifest. In der Asset-Karte steht der Unterschied als `AI · watermark` gegen
  `AI · metadata` — beide sind `manifest verified`. Das Wasserzeichen landet nur auf
  der Kopie; als Identitäts-Referenz nutzt die App immer das unberührte Original,
  die Folgebilder bleiben also sauber.
- **Kosten (gpt-image-2):** Entwurf $0,006, Final $0,211 pro Bild. Porträt-Auswahl
  also rund 2,4 Cent pro Figur, eine Mixed-Media-Szene 3,9 Cent (Nano Banana),
  die vierteilige Comic-Seite in Final $0,84. Der teure Teil ist das Video, nicht
  die Bilder — aber Final ist jetzt 35× so teuer wie Entwurf, entsprechend lohnt
  sich das Iterieren im Entwurf mehr als früher.
- **Namen:** „Mara" ist bewusst nicht verwendet — der Name war unerwünscht.
- **Workspace:** Das Demo gehört in einen **frisch angelegten Workspace**, nicht
  in den bestehenden. So bleiben die vorhandenen Charaktere unberührt und der
  Demo-Workspace lässt sich später gefahrlos teilen oder wegwerfen. Anlegen über
  `POST /workspaces` bzw. den Workspace-Dialog; den Token danach notieren.

- **Backblaze-Tageslimit einplanen.** Beim ersten Durchlauf riss das B2-Konto sein
  Tageslimit: `AccessDenied … download bandwidth or transaction (Class B) cap
  exceeded`. Wirkung ist doppelt und auf den ersten Blick verwirrend — in der UI
  laden schlagartig *alle* Vorschaubilder nicht mehr, und gleichzeitig scheitert
  jede weitere Generierung, weil die App das Referenzporträt nicht mehr von B2
  holen kann. Jeder Seitenaufruf zieht sämtliche Thumbnails frisch über
  presignte URLs (Gültigkeit 1 h), das summiert sich schnell. Vor einer
  Aufnahmesession das Cap unter **Backblaze → Caps & Alerts** hochsetzen; sonst
  bricht die Session mitten im Dreh ab und setzt sich erst zum UTC-Mitternacht
  zurück.

## Offene Baustellen (nicht blockierend für das Demo)

- 40 der 65 Inworld-Stimmen haben noch keine Hörprobe. Dafür muss der
  `GENERATE_API_KEY` der Instanz lokal in `.env` stehen, sonst greift das
  geteilte Gratis-Limit (429).
- Kinderstimmen klingen blechern: `_pitch_shift` verschiebt per `asetrate` die
  Formanten mit der Tonhöhe (Chipmunk-Effekt). Abhilfe wäre
  `rubberband=pitch=…:formant=preserved` — oder echte Kinderstimmen von einem
  Anbieter, der welche hat. Für Jungen gibt es aktuell keine echte Stimme.
