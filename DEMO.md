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
- **Kosten:** Szenen etwa 4 Cent pro Stück, Porträt-Auswahl rund 4 Cent pro
  Figur. Der teure Teil ist das Video, nicht die Bilder.
- **Namen:** „Mara" ist bewusst nicht verwendet — der Name war unerwünscht.
- **Workspace:** Das Demo gehört in einen **frisch angelegten Workspace**, nicht
  in den bestehenden. So bleiben die vorhandenen Charaktere unberührt und der
  Demo-Workspace lässt sich später gefahrlos teilen oder wegwerfen. Anlegen über
  `POST /workspaces` bzw. den Workspace-Dialog; den Token danach notieren.

## Offene Baustellen (nicht blockierend für das Demo)

- 40 der 65 Inworld-Stimmen haben noch keine Hörprobe. Dafür muss der
  `GENERATE_API_KEY` der Instanz lokal in `.env` stehen, sonst greift das
  geteilte Gratis-Limit (429).
- Kinderstimmen klingen blechern: `_pitch_shift` verschiebt per `asetrate` die
  Formanten mit der Tonhöhe (Chipmunk-Effekt). Abhilfe wäre
  `rubberband=pitch=…:formant=preserved` — oder echte Kinderstimmen von einem
  Anbieter, der welche hat. Für Jungen gibt es aktuell keine echte Stimme.
