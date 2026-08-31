# Storyline

Storyline is a browser-first reading app for saving, exploring, and discussing stories.
It lets you:

- save articles into a personal library
- bookmark stories for quick access later
- keep the library and bookmarks in the browser
- import/export the library as JSON
- get an overview of topic distribution and recurring themes
- open the Connections view to see related stories
- ask AI questions about a selected story
- simplify stories and generate tags with AI

The app ships with:

- a Python `Flask` backend that serves the shell and JSON API
- browser storage for the user library and bookmarks
- a text-first Storyline shell as the main experience
- a graphical shell for the shared starter framework
- opt-in capability APIs for audio analysis, search, optimization, mapping, and optional machine learning
- deployment examples for `nginx` in front of `gunicorn`
- a locked, validated cron deploy flow with backups, readiness checks, retryable rollback, and selective gunicorn reloads

## Why No Frontend Build Step

The app intentionally avoids Node and a frontend bundler. That keeps deployment and future edits simpler while still leaving room for richer rendering later. The frontend is split into small modules, and the graphical shell stays available without affecting the Storyline text experience.

## Repository Layout

- `server/` contains the Flask app, API helpers, and HTML/CSS/JS assets
- `server/gizmoapp_server/capabilities/` contains lazy backend integrations for audio, search, optimization, OpenStreetMap, and optional scikit-learn
- `server/gizmoapp_server/static/app/text/` contains the Storyline UI
- `server/gizmoapp_server/static/app/capabilities/` contains optional frontend helpers that are not imported by default
- `scripts/` contains install, deploy, and asset-generation helpers
- `deploy/` contains example `gunicorn`, `nginx`, and cron snippets
- `docs/design-overview.md` records the intended architecture, config split, and deployment model
- `docs/agent-map.md` is the short routing guide for coding agents so they can open only the files relevant to the current task
- `docs/agent-extension-guide.md` gives future coding agents concrete extension rules
- `docs/course-media.md` explains how app routes use course image generation, image editing, and speech synthesis
- `deploy/app-shell.txt` contains git-tracked shell intent for hosted/student workspaces without using a worker-denied `*.env` path
- `deploy/features.txt` contains git-tracked intent for optional public admin and capability routes
- `deploy/app.env` contains git-tracked deployment settings that should reach the server only through an explicitly requested push/deploy flow
- `deploy/non-scaffold-app-deployment.md` explains how existing non-GizmoApp apps should fit into the neutral nginx host layout
- `tests/` contains API and routing smoke tests

## Design Overview

The short operational instructions in this README assume the design choices in
[`docs/design-overview.md`](docs/design-overview.md). Read that file when you
need the reasoning behind:

- why there are two frontend shells in one repo
- why deployment is path-prefix-aware
- why `deploy/app-shell.txt`, `deploy/app.env`, and `.env` have different roles
- why cron deploys, user services, and nginx snippets are structured the way they are

## Deployment Model

There are now two separate deployment installation layers:

- Machine bootstrap: install the system packages needed on the host once
- App instance install: clone one specific repo/fork into a named directory, configure it, and make it serve at `vickrey10.cs.ubc.ca/name`

This split is meant to support multiple independent apps derived from this starter on the same machine.

## Local Development

1. Copy `.env.example` to `.env` if you want to change local machine-specific settings. For a local prefix test, set `GIZMOAPP_URL_PREFIX=/demo-app`.
2. Install dependencies:

```bash
ALLOW_NETWORK_INSTALL=1 make install
```

3. Run the development server:

```bash
ALLOW_SERVER_RUN=1 make dev
```

Or start a specific shell explicitly:

```bash
ALLOW_SERVER_RUN=1 make dev-auto
ALLOW_SERVER_RUN=1 make dev-graphical
ALLOW_SERVER_RUN=1 make dev-text
```

The development commands now auto-read `deploy/app.env` and then a repo-root `.env`. The default app URL is `http://127.0.0.1:8001/` unless you set `GIZMOAPP_URL_PREFIX`, in which case the app lives under that prefix.

Storyline keeps the personal library in browser storage, so bookmarks and saved stories persist in the user’s browser. Use the import/export controls in the Library view if you want to move data between browsers.

Run the repo-standard validation entry point with:

```bash
make validate
```

The helper first runs a Python-based JavaScript structural check, then uses `.venv`, system packages, or `.pydeps/` when they already exist. It does not install packages automatically, so it stays safe for escalation-free agent runs. Node is intentionally not required; for a JS-only sanity pass, run:

```bash
make js-check
```

Before a local source-repo commit, this helper can set a repo-local Git identity and safely clear stale index locks:

```bash
make commit-ready
```

Machine-learning features should install the optional scikit-learn dependency only when an app actually needs ML:

```bash
ALLOW_NETWORK_INSTALL=1 make install-ml
```

## Visual Verification

Graphics work should be checked with a browser screenshot pass before it is treated
as finished. The visual pipeline is optional so the base app stays lean:

```bash
ALLOW_NETWORK_INSTALL=1 make visual-install
ALLOW_BROWSER_CHECK=1 make visual-check
```

The install step may need network access, and the check step starts browser/server automation. Agents should run them only when that work is already permitted or the user explicitly asks for it. `make visual-check` starts the graphical shell, captures phone, tablet, and
desktop screenshots, checks that `#scene-canvas` is rendered, and writes:

- `var/visual-report/index.html`
- `var/visual-report/report.json`
- `var/visual-report/graphical-*.png`

Open the HTML report and inspect the screenshots. Pixel checks can catch broken
or unintentionally flat canvases, while the starter canvas may explicitly mark
itself as intentionally blank.

## Shell Selection

The project keeps both blank shells in the same codebase and shares the same backend, API, database, and deployment scripts.

- `server/wsgi_graphical.py` serves the graphical shell
- `server/wsgi_text.py` serves the text-first shell
- `server/wsgi.py` serves whichever shell is selected by `GIZMOAPP_SHELL`

On the server, the simplest approach is to keep the gunicorn target at `server.wsgi:app` and set the default shell in `deploy/app.env`. Use `GIZMOAPP_SHELL=auto` for open-ended agentic/template-derived workspaces. Auto mode inspects changed files in the checkout: text-shell template/assets select `text`, graphical template/assets select `graphical`, and mixed or unclear changes fall back to `graphical`. When a hosted CodingWorkspace app clearly chooses one public shell, set `deploy/app-shell.txt` to `text` or `graphical`; do not edit `.env` or rely on `deploy/app.env` for hosted shell intent because worker permissions may deny `*.env` edits. For non-hosted deploy flows, a concrete `GIZMOAPP_SHELL=text` or `GIZMOAPP_SHELL=graphical` in tracked `deploy/app.env` remains the env-style deployment setting. The deploy scripts merge the tracked env setting into the live `.env` and restart the service when it changes.

## Using This As A Starter

If you want future users to create their own apps from this starting point, GitHub template repositories are usually a better fit than forks.

- Use a template repository when the new project should start with the same files but become its own independent app and history.
- Use a fork when the main goal is to contribute changes back to this repository while preserving GitHub’s fork relationship.

For this repository, the intended use is as a starter/template. A derived app should usually get its own repo name, its own deployment target, and its own branding rather than staying tied to GizmoApp.

To support that use case, keep these traits intact:

- configuration lives in `.env`
- hosted shell intent lives in `deploy/app-shell.txt`
- git-controlled deployment defaults live in `deploy/app.env`
- deployment steps stay explicit in `README.md` and `deploy/`
- the backend remains shared and understandable
- shell-specific UI stays isolated so future projects can keep one shell or both

For template-derived apps, the intended workflow is:

- complete a task
- commit it with a descriptive message
- if Git identity or a stale index lock blocks the commit, run `make commit-ready` instead of changing global Git config or removing lock files by hand
- push it so the deployment cron job can pick it up only when the user explicitly asks for the push or deploy flow
- if the task installs or generates local-only files that do not belong in the repo, add them to `.gitignore`

For deployed template-derived apps, prefer this split:

- `deploy/app-shell.txt` is git-tracked and should hold hosted/student shell intent when a CodingWorkspace app clearly chooses `text` or `graphical`
- `deploy/app.env` is git-tracked and should hold non-secret runtime choices you want to reach the server through an explicit `git push` plus cron deploy flow
- `.env` on the server is machine-specific and should hold secrets, ports, DB paths, service names, and per-instance URL prefixes

For example, forcing a hosted CodingWorkspace preview from the text shell to the graphical shell should normally mean editing `deploy/app-shell.txt`. Forcing a non-hosted deployment should normally mean editing `deploy/app.env`, then committing and pushing only as part of an explicitly requested deploy flow, not SSHing into the server to edit `.env`.

## API Surface

- `GET /api/bootstrap` returns app metadata, health details, and available capability summaries
- `GET /api/capabilities` returns capability status, including whether each optional route is disabled
- `GET /healthz` is a lightweight process liveness check
- `GET /readyz` verifies that SQLite is reachable and at the expected schema version

The routes below are disabled by default. Add only the required slugs to
`deploy/features.txt`:

- `search`: `GET /api/search?q=...`
- `mapping`: `GET /api/map/default`
- `machine-learning`: `GET /api/ml/status` and `POST /api/ml/kmeans`
- `optimization`: `POST /api/optimize/route`
- `audio`: `POST /api/audio/analyze`
- `sample-nodes`: `GET` and `POST /api/sample-nodes`
- `admin`: `GET /admin/`

All JSON endpoints require object-shaped JSON, return structured JSON errors
with request IDs, reject non-finite numbers, and enforce bounded payloads. The
generated nginx route also caps request bodies.

Capability behavior:

- `GET /api/search?q=...` searches persisted sample records in SQLite
- `GET /api/map/default` returns OpenStreetMap settings and the default UBC Vancouver location when mapping is requested
- `GET /api/ml/status` reports whether scikit-learn is installed
- `POST /api/ml/kmeans` runs a small scikit-learn KMeans job when ML dependencies are installed
- `POST /api/optimize/route` runs a simple route ordering optimization
- `POST /api/audio/analyze` summarizes browser-captured sample arrays
- `GET /api/sample-nodes` lists optional sample records from SQLite
- `POST /api/sample-nodes` inserts an optional sample record for future experimentation

If `GIZMOAPP_URL_PREFIX` is set, all of those routes live under the prefix. For example, `/demo-app/api/bootstrap`.

## Course AI Model (AI100)

When GizmoApp runs on the AI100 platform, your app gets its own AI API key —
separate from the coding agent's key, with its own budget, limited to the
course model. It arrives automatically as environment variables
(`GIZMO_LLM_API_KEY`, `GIZMO_LLM_BASE_URL`, `GIZMO_LLM_MODEL`); you never need
to copy or paste a key.

Use it through the bundled helper:

```python
from .llm import ask   # inside server/gizmoapp_server/ modules

@app.post("/api/haiku")
def haiku():
    return {"text": ask("Write a haiku about debugging.")}
```

`ask(prompt)` covers one-shot questions; `llm.chat(messages)` takes a full
message list for conversations. Keep `max_tokens` generous (the default is
fine) — the course model uses part of its budget for internal reasoning and
very small limits can produce empty replies. Your app's AI budget is small:
call the model when the user asks for something, not on every page load.

The helper requires all three settings and fails closed if any are missing. It
uses a bounded timeout shorter than gunicorn's request timeout, one retry, input
validation, and safe user-displayable `CourseLLMError` messages. Outside the
platform those variables are unset, so AI features remain unavailable unless
you deliberately provide a compatible endpoint through the same variables.

## Course Image and Speech Services

CodingWorkspace also gives each running app a workspace-scoped media credential.
The app discovers the service through `GIZMO_MEDIA_BASE_URL`,
`GIZMO_MEDIA_API_KEY`, and `GIZMO_MEDIA_OPERATIONS`; you do not create, store,
or copy these values. CodingWorkspace rotates the credential when the preview
starts and revokes it when the preview stops.

See [`docs/course-media.md`](docs/course-media.md) for a complete prefix-aware
Flask and browser recipe, available function signatures, limits, and error
handling.

Use the bundled server-side helper:

```python
from flask import Response

from .media import generate_image, synthesize_speech


@app.post("/api/generated-picture")
def generated_picture():
    result = generate_image("A friendly robot teaching an AI class")
    return Response(result.data, mimetype=result.content_type)


@app.post("/api/spoken-welcome")
def spoken_welcome():
    result = synthesize_speech("Welcome to our app!")
    return Response(result.data, mimetype=result.content_type)
```

`generate_image(..., model="lcm-sd15", steps=4)` provides fast drafts.
`edit_image()` supports ordinary image-to-image editing, mask-based SD1.5
inpainting, and InstructPix2Pix. Speech supports multilingual Kokoro. See the
model table and language codes in
[`docs/course-media.md`](docs/course-media.md). Images are 512×512 PNGs and
speech is WAV audio. These small models run on the course's older Ada cluster,
so requests can take several seconds and may report that the worker is busy.

Call these functions only from Python routes in
`server/gizmoapp_server/`. Never put `GIZMO_MEDIA_API_KEY` in HTML, JavaScript,
JSON responses, logs, or the database. Browser code should call your own Flask
route, as in the examples above. Generate media only after a user action, and
catch `CourseMediaError` when the UI needs to show a friendly retry message.

Voice cloning is deliberately not granted to student apps in the initial
service. It requires separate consent, abuse controls, and a larger model.

## Deployment Notes

The commands in this section are manual deployment actions. They may install packages, use `sudo`, write outside the checkout, contact GitHub, edit nginx, reload services, or change cron. Coding agents should not run them unless the user explicitly asks for that deployment action in the current turn.

### One-time machine bootstrap

Run this once per deployment machine:

```bash
ALLOW_DEPLOY_ACTIONS=1 ./scripts/install_machine_dependencies.sh
```

This installs the required Ubuntu/Debian packages such as Python, `python3-venv`, Git, SQLite, curl, and cron.

### One-time nginx bootstrap for single-command future deployments

If you want future app installs to become one command with no manual nginx edits,
run this once on the server:

```bash
ALLOW_DEPLOY_ACTIONS=1 ./scripts/install_nginx_instance_router.sh \
  --server-config /etc/nginx/sites-enabled/vickrey10 \
  --server-name vickrey10.cs.ubc.ca
```

That creates a managed nginx include directory at `/etc/nginx/gizmoapp-instances`,
patches the chosen site config to include `*.conf` files from that directory inside
the matching `server` block, validates nginx, and reloads it.

If your site file does not contain an explicit `server_name vickrey10.cs.ubc.ca`
line but the file itself is clearly the right site config and contains only one
`server { ... }` block, you can omit `--server-name` and point directly at that
file:

```bash
ALLOW_DEPLOY_ACTIONS=1 ./scripts/install_nginx_instance_router.sh \
  --server-config /etc/nginx/sites-enabled/vickrey10
```

After that one-time bootstrap, future `install_deployment_instance.sh` runs will
copy each app's generated snippet into `/etc/nginx/gizmoapp-instances/<name>.conf`
and reload nginx automatically.

### Recommended nginx layout on `vickrey10.cs.ubc.ca`

For long-term clarity, do not use an app-specific nginx filename such as
`/etc/nginx/sites-enabled/ai100` as the permanent home for all path-based apps.
Prefer this structure instead:

- neutral host file:
  - `/etc/nginx/sites-available/vickrey10`
  - `/etc/nginx/sites-enabled/vickrey10`
- one snippet per routed app:
  - `/etc/nginx/gizmoapp-instances/AI100.conf`
  - `/etc/nginx/gizmoapp-instances/gizmotest.conf`
  - `/etc/nginx/gizmoapp-instances/myapp.conf`

An example neutral host file is provided at `deploy/nginx-host.example.conf`.
That file owns the host-level `server { ... }` block and includes
`/etc/nginx/gizmoapp-instances/*.conf`.

### Safe migration from `ai100` to a neutral `vickrey10` host file

If the current live path `/AI100` is still served from an nginx file named
`/etc/nginx/sites-enabled/ai100`, migrate in this order so `/AI100` keeps
working throughout:

1. Create the managed snippet directory once. This is a manual server-admin step
   that writes under `/etc/nginx`.

2. Create `/etc/nginx/gizmoapp-instances/AI100.conf` containing the existing
`/AI100` location block. If `~/bin/AI100` is based on this scaffold, you can
reuse its generated snippet or match the existing live config exactly.

3. Create a neutral host config file from `deploy/nginx-host.example.conf`.

4. Adjust the copied host file if needed for your host-level defaults, then enable it.

5. Validate nginx and confirm `/AI100/` still responds before removing the old file.

6. Only after `/AI100/` still works through the new host file, disable the old
app-named site file if it is no longer needed, validate nginx again, and reload it.

After that migration, run the one-time router bootstrap against the neutral host file:

```bash
cd /home/kevinlb/bin/GizmoApp
ALLOW_DEPLOY_ACTIONS=1 ./scripts/install_nginx_instance_router.sh \
  --server-config /etc/nginx/sites-enabled/vickrey10
```

From that point on, future app installs can register themselves automatically
without editing nginx by hand.

For the current server, a more direct migration helper is available:

```bash
cd /home/kevinlb/bin/GizmoApp
ALLOW_DEPLOY_ACTIONS=1 ./scripts/migrate_nginx_to_neutral_host.sh
```

That helper is tailored to the existing `ai100` to `vickrey10` rename and will:

- copy the live enabled site from `/etc/nginx/sites-enabled/ai100`
- create `/etc/nginx/sites-available/vickrey10`
- enable `/etc/nginx/sites-enabled/vickrey10`
- disable the old `/etc/nginx/sites-enabled/ai100` path
- bootstrap `/etc/nginx/gizmoapp-instances/*.conf`
- validate and reload nginx

Because it copies the current live host config first, the existing `/AI100`
route should keep working after the migration. That route may remain inline in
the neutral host file until you choose to normalize it into its own managed
snippet.

If you have already-installed app instances that predate automatic nginx
registration, register them once with:

```bash
ALLOW_DEPLOY_ACTIONS=1 ./scripts/register_nginx_instance_snippet.sh \
  --name gizmotest \
  --snippet /home/kevinlb/bin/gizmotest/var/generated/nginx-location.conf
```

### Current-checkout install

If the current checkout is itself the live deployment checkout, run:

```bash
ALLOW_DEPLOY_ACTIONS=1 ./scripts/install_server.sh
```

That convenience wrapper runs both the machine bootstrap and the current-checkout initialization.

If machine dependencies are already installed and you only want to initialize the current checkout, run:

```bash
ALLOW_NETWORK_INSTALL=1 ./scripts/install_checkout.sh
```

That script also normalizes `.env` to owner-only permissions so secrets do not stay world-readable on shared machines, and merges any git-tracked settings from `deploy/app.env` into the live `.env`.

### Install a fork/template-derived app at `/name`

After a derived repo exists on GitHub, install it onto the server with:

```bash
ALLOW_DEPLOY_ACTIONS=1 ./scripts/install_deployment_instance.sh \
  --name myapp \
  --repo-url git@github.com:YOUR_ACCOUNT/YOUR_REPO.git \
  --branch main \
  --shell text
```

This script:

- creates or updates `/home/kevinlb/bin/myapp`
- checks out `origin/main`
- writes `/home/kevinlb/bin/myapp/.env`
- locks `/home/kevinlb/bin/myapp/.env` to owner-only permissions and safely quotes values such as app titles with spaces
- merges git-tracked settings from `deploy/app.env` into the live `.env`
- picks a free local gunicorn port unless you specify `--port`
- creates the virtualenv and installs Python dependencies
- initializes the SQLite database
- writes a user-level systemd service at `~/.config/systemd/user/myapp.service`
- installs a once-per-minute cron entry through `scripts/run_deploy_cron.sh`,
  which bounds deploy-log growth
- generates an nginx location snippet at `/home/kevinlb/bin/myapp/var/generated/nginx-location.conf`, including a redirect from `/myapp` to `/myapp/`
- if the one-time nginx router bootstrap has been installed, copies the snippet into `/etc/nginx/gizmoapp-instances/myapp.conf` and reloads nginx automatically

The default public URL becomes `http://vickrey10.cs.ubc.ca/myapp/`.

### Fastest server command for new GizmoApp-derived repos

If you want a one-argument deployment command, use:

```bash
ALLOW_DEPLOY_ACTIONS=1 ./scripts/deploy_gizmoapp_repo.sh git@github.com:YOUR_ACCOUNT/YOUR_REPO.git
```

That wrapper:

- infers the app name from the repository name
- checks the repo out under `/home/kevinlb/bin/<repo-name>`
- serves it at `http://vickrey10.cs.ubc.ca/<repo-name>/`
- uses the shell declared in `deploy/app.env`, or falls back to `auto` if that file does not set one. With `auto`, `deploy/app-shell.txt` can still pin hosted/student shell intent inside the app.
- installs the per-minute git deploy cron job
- registers the nginx route during the approved deploy action if the one-time router bootstrap has been run

For example:

```bash
ALLOW_DEPLOY_ACTIONS=1 ./scripts/deploy_gizmoapp_repo.sh git@github.com:kevinlb1/GizmoAppKLB1.git
```

To make this easy to run from anywhere on the server, a server administrator can
copy `scripts/deploy_gizmoapp_repo.sh` into `~/bin/deploy-gizmoapp-repo`.

Then future installs become:

```bash
ALLOW_DEPLOY_ACTIONS=1 ~/bin/deploy-gizmoapp-repo git@github.com:YOUR_ACCOUNT/YOUR_REPO.git
```

Optional overrides:

```bash
ALLOW_DEPLOY_ACTIONS=1 ~/bin/deploy-gizmoapp-repo git@github.com:YOUR_ACCOUNT/YOUR_REPO.git --shell text
ALLOW_DEPLOY_ACTIONS=1 ~/bin/deploy-gizmoapp-repo git@github.com:YOUR_ACCOUNT/YOUR_REPO.git --branch develop
```

### After running `install_deployment_instance.sh`

1. Review `/home/kevinlb/bin/myapp/.env`.
   Treat it as machine-specific state, not the normal place for app-level settings that should come from git.
2. If you already ran `install_nginx_instance_router.sh`, the approved installer updates nginx and you can skip to checking the service.
3. If you did not run the one-time router bootstrap, add the generated nginx snippet from `/home/kevinlb/bin/myapp/var/generated/nginx-location.conf` to the `vickrey10.cs.ubc.ca` nginx server block.
4. Reload nginx manually on the server if you edited the host config.

5. Check the user service on the server.

6. Visit `https://vickrey10.cs.ubc.ca/myapp/`.

If the app should stay running even when the deployment user is logged out, a
privileged user may also need to enable linger for the deployment account.

### `gunicorn` reload behavior

Static asset changes do not require a `gunicorn` reload because Flask serves them from disk on each request. Backend Python and template changes do require a reload so workers pick up the new code. The deploy script detects that difference and only attempts a reload when needed.

Gunicorn writes access/error output to stdout/stderr for journald rotation, uses
`/dev/shm` for worker heartbeats when available, and disables the optional
single-path control socket so multiple app instances cannot collide.

### Cron deployment

The example cron entry calls `scripts/run_deploy_cron.sh` once per minute. The
wrapper rotates bounded deploy logs and calls the locked deploy transaction,
which:

- Refuses to deploy if tracked files are dirty
- Refuses to overlap another deploy and preserves local commits
- Fast-forwards the live checkout from `origin/main`, while keeping the prior
  commit available for rollback
- Merges git-tracked deployment settings from `deploy/app.env` into the live `.env`
- Reinstalls Python packages only when `server/requirements.txt` changes
- Runs the full validation suite before activation
- Creates a consistent SQLite backup and applies transactional migrations
- Reloads `gunicorn` when runtime files changed and a reload strategy is configured
- Requires `/readyz` to pass before advancing the deployed-commit marker
- Restores the prior checkout and restarts it if activation fails, allowing the
  next cron run to retry

If a pushed commit changes `deploy/app.env`, the deploy script restarts the user service so the new environment takes effect. This is the intended way to send settings such as shell changes to the server without manual SSH edits.

The installed cron entry also exports `XDG_RUNTIME_DIR` and `DBUS_SESSION_BUS_ADDRESS` so `systemctl --user` can talk to the user systemd bus even when the deploy runs from cron.

When you use `scripts/install_deployment_instance.sh` with `ALLOW_DEPLOY_ACTIONS=1`, the script installs a real cron entry for that specific checkout unless you pass `--skip-cron`.

If you have older app installs that were created before this cron hardening, re-run `scripts/install_deployment_instance.sh` for that app or update the crontab entry so it includes those two environment variables before calling `scripts/deploy_from_git.sh`.

### HTTPS

Generated deployment instructions use the host's HTTPS URL. The blank starter
does not register a service worker or advertise offline installation; a derived
app should add a versioned cache and explicit offline/update UX only when its
requirements genuinely include offline behavior.
