# Agent Extension Guide

This repo is meant to answer common setup questions before a future coding agent
has to ask them.

If you are deciding where to start, read `docs/agent-map.md` first. This guide
is for task-specific details after the map points you here.

## Default Stack

- Backend: Flask in `server/gizmoapp_server/`
- Persistence: SQLite through `server/gizmoapp_server/db.py`
- Text UI: `server/gizmoapp_server/templates/index_text.html` and `static/app/text/`
- Graphical UI: `server/gizmoapp_server/templates/index.html` and `static/app/`
- Shared styling: `server/gizmoapp_server/static/app/base.css`
- Optional frontend helpers: `server/gizmoapp_server/static/app/capabilities/`
- Optional backend helpers: `server/gizmoapp_server/capabilities/`

Keep new work prefix-aware by building routes with `scoped_path` and reading API
URLs from the injected browser config instead of hard-coding `/api`.

Optional public routes are fail-closed. When a requested feature uses admin,
audio, machine learning, mapping, optimization, sample-node, or search routes,
add the matching slug from `deploy/features.txt` in the same commit. Do not
enable unrelated routes “just in case.”

## Persistence

Use SQLite first. Add schema changes as migrations in `SCHEMA_MIGRATIONS` inside
`server/gizmoapp_server/db.py`. Keep local data under `var/`, which is ignored by
Git.

For general app state, prefer `app_state`. For append-only user-visible activity,
prefer `app_events`. Add domain tables only when the feature has real domain
data.

## UI

Use the shared app frame and tokens in `base.css` before inventing new layout
chrome. Keep cards at 8px radius. Keep text compact enough for phone, tablet,
laptop, and desktop widths.

Choose the text shell for forms, lists, dashboards, records, and workflows.
Choose the graphical shell for canvas, animation, map-like views, sprites,
games, simulations, and rich visuals.

## Graphics

The graphical shell starts as an intentionally blank canvas. It is still
sprite/bitmap-first when graphics are requested: `SceneRenderer` can turn
database-backed visual nodes into generated bitmap sprites, then render them
with `drawImage`. It supports:

- generated bitmap textures
- loaded image textures
- layered sprites with opacity and rotation
- database-backed visual nodes
- pointer-driven animation

Use direct canvas polygons, ellipses, and lines mainly for simple overlays,
debugging, masks, hit areas, or explicitly vector-styled work. For finished
graphics, prefer sprite sheets, generated bitmap textures, loaded PNG/WebP
assets, or image-generated sprite bitmaps.

Codex can produce build-time sprite bitmaps when an image-generation tool is
available. Use that path first for durable art assets and put the results under
`server/gizmoapp_server/static/app/assets/`. For images generated at app
runtime after a user action, use `server/gizmoapp_server/media.py` and follow
`docs/course-media.md`. If neither path is available, say so clearly and build
an asset slot or simple stylized placeholder instead of faking realism with
many visible primitive shapes.

SVG/vector graphics are best for intentionally stylized icons, diagrams,
simple characters, and small deformable rigs. They resize cleanly, but
photorealistic vector art generated from traces or many hand-coded paths is
usually large, brittle, and hard for a small coding model to edit well. For
realistic subjects that also need parameter controls, prefer a hybrid: a
high-resolution bitmap sprite for appearance, plus a lightweight vector mask,
skeleton, or control overlay for pose/proportion changes.

For small hosted models, use this bounded recipe for rich visual subjects:

1. If an image asset is available or can be generated, put it under
   `static/app/assets/`, load it once, and draw it with `drawImage`.
2. If no asset is available, put the main subject in `scene.js` as an offscreen
   texture function, for example `createHedgehogTexture(params)`, returning a
   canvas or image.
3. Compose fallback procedural textures at a higher internal resolution with
   gradients, noise, shadows, soft edges, and a few carefully placed paths. The
   final scene should draw the composed subject with `drawImage`, not rebuild it
   every frame from a pile of visible top-level primitives.
4. Keep parameters explicit and few at first, such as quill length, snout
   length, eye size, color, pose, or count. Add controls in `index.html`, read
   them in `main.js`, and pass them to the renderer through one method.
5. Make a visible first version before exploring optional libraries, backend
   capabilities, deployment scripts, or visual-verification implementation
   details.
6. If browser screenshots are not already available, do not block the whole turn
   on installing them. Run static/unit validation, check `git status --short`,
   and clearly say that screenshot verification was blocked.

For heavier visuals, add a renderer adapter under `static/app/` and lazy-load
the library only from the shell that needs it.

Before ending a turn that changes graphics, run the visual pipeline:

```bash
ALLOW_BROWSER_CHECK=1 make visual-check
```

Run that only when browser/server automation is already permitted and Playwright/Chromium are already available. If Playwright/Chromium is not installed, do not install it automatically; report the blocker and give this manual setup command:

```bash
ALLOW_NETWORK_INSTALL=1 make visual-install
```

The report lands in `var/visual-report/index.html` with phone, tablet, and
desktop screenshots plus canvas pixel checks. Inspect the screenshots yourself.
If the visuals are blank, awkwardly framed, overlapping, or ugly, improve them
before finalizing the task. If tooling or sandbox restrictions block the visual
check, report that blocker clearly.

## Audio

Use `static/app/capabilities/audio.js` for browser microphone capture. Send
sample arrays to `POST /api/audio/analyze` for dependency-free analysis. Add
heavier audio libraries only when the user asks for transcription, classification,
or signal processing that needs them.

Enable the route by adding `audio` to `deploy/features.txt`.

For text-to-speech, use `synthesize_speech()` from
`server/gizmoapp_server/media.py` instead of the microphone-analysis
capability. Follow `docs/course-media.md`; speech synthesis does not require an
`audio` entry in `deploy/features.txt`.

When the app is embedded in CodingWorkspace, the preview iframe grants
microphone permission policy, but the browser still requires a user gesture and
the user's permission. Keep audio setup behind an explicit button or similar
interaction. Do not depend on service workers, localStorage, sessionStorage,
IndexedDB, cookies, or same-origin access in the embedded preview; use backend
Flask/SQLite APIs for persistent state and wrap optional browser storage in
`try`/`catch`.

## Search

Start with `GET /api/search?q=...` and SQLite queries. If a feature needs richer
local search, add SQLite FTS tables in a migration before introducing an external
search service. If the requested feature needs external web search or a hosted
search API, prefer Bing or Tavily and do not use DuckDuckGo as the default
provider.

Enable this route with `search` in `deploy/features.txt`; add `sample-nodes`
only if the app also uses the scaffold's sample-record write API.

## Optimization

Start with `POST /api/optimize/route` and pure-Python algorithms. Bring in a
specialized solver only when the requested optimization problem outgrows that
simple path.

Enable this route with `optimization` in `deploy/features.txt`.

## Mapping And Location

Use OpenStreetMap when mapping is requested. `GET /api/map/default` returns the
tile URL template, attribution, and default location for mapping features.

Enable this route with `mapping` in `deploy/features.txt`.

For requested location-dependent features, assume the user is at UBC Vancouver
only when they give no different location.

## Machine Learning

Use scikit-learn when the user requests ML. Keep it optional:

```bash
ALLOW_NETWORK_INSTALL=1 make install-ml
```

Do not add scikit-learn to `server/requirements.txt` unless ML becomes mandatory
for the base template.

Enable the status and KMeans routes with `machine-learning` in
`deploy/features.txt`.
