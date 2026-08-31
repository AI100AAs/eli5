# GizmoApp Design Overview

This document records the design intent behind the scaffold so future edits can
extend it without rediscovering core assumptions.

## Purpose

GizmoApp is a starter repository for building small public web apps that can be
edited incrementally by Codex. The initial state is intentionally blank, but the
shape of the project is meant to support:

- touch-friendly interaction on phones and tablets
- desktop browser support
- either a graphical shell or a text-first shell
- low-friction deployment on a single Linux host
- simple operational behavior that a non-expert user can follow

## Core Constraints

- Keep the frontend build-free unless the user explicitly chooses otherwise.
- Keep deployment centered on one host with `nginx`, `gunicorn`, and SQLite.
- Keep the app prefix-aware so it can live at `/<repo-name>/` instead of only `/`.
- Keep the code understandable enough that a future Codex session can work from
  the repository alone.
- Keep optional capabilities lazy so unused ML, audio, mapping, graphics, search,
  and optimization support does not add unnecessary runtime or install overhead.
- Keep visual verification optional but available, so agents can inspect graphics
  screenshots without forcing browser automation into the base runtime.
- Keep public starter chrome absent. Admin and diagnostics can use the full
  header, but public shells should start with no scaffold Admin/Install/status
  controls.

## High-Level Architecture

The app has three main layers:

1. Flask backend
   - Serves HTML, core JSON/health/readiness routes, opt-in capability/admin
     routes, and static assets.
2. SQLite persistence
   - Stores migration metadata and app state/events for future feature work.
3. Shell-specific frontend
   - `graphical` shell for sprite/bitmap-first canvas, animation, or game-like interaction.
   - `text` shell for forms, dashboards, and conventional application flows.
4. Lazy capability modules
   - Audio analysis, SQLite search, pure-Python optimization, OpenStreetMap helpers,
     optional scikit-learn ML, and frontend helper modules.

Both shells share the same backend, deployment process, and database.

## Capability Model

The scaffold includes capability entry points without making them mandatory for
every derived app:

- audio: browser sample capture helpers plus a backend sample-array analyzer
- search: SQLite-backed record search
- optimization: small pure-Python route/order optimization
- mapping: OpenStreetMap tile settings available when a feature requests maps
- machine learning: scikit-learn integration through `server/requirements-ml.txt`
- rich graphics: default sprite/bitmap rendering plus hooks for loaded textures
  and sprite sheets
- visual verification: Playwright screenshot capture and canvas pixel sanity
  checks through `scripts/visual_verify.py`

Use these modules first when a user asks for those domains. Install optional
dependencies only when the requested feature needs them. Public feature routes
are disabled by default and enabled through tracked `deploy/features.txt`, so a
blank starter exposes only its core shell, bootstrap, health, readiness, and
capability-discovery surfaces.

## Shell Model

Shell selection is a deployment/runtime choice, not a repo split.

- `server/wsgi.py` serves whichever shell is active.
- `server/wsgi_graphical.py` forces the graphical shell.
- `server/wsgi_text.py` forces the text shell.

For hosted CodingWorkspace apps, the intended default is to store concrete
student-facing shell intent in `deploy/app-shell.txt`. It is deliberately not an
env file because hosted workers may be denied `*.env` edits.

For non-hosted deployments, `deploy/app.env` remains the env-style place to
force `GIZMOAPP_SHELL=text` or `GIZMOAPP_SHELL=graphical`. During an explicitly
requested deploy flow, commit and push that setting so the deploy pipeline can
apply it to the live service without requiring a manual SSH edit on the server.

For open-ended agentic/student workspaces, the preferred value is
`GIZMOAPP_SHELL=auto`. Auto mode inspects changed shell-specific files in the
checkout. Text-shell template/assets select `text`, graphical template/assets
select `graphical`, and mixed or unclear changes fall back to `graphical`. When
the student prompt clearly targets one shell, the agent should write `text` or
`graphical` to tracked `deploy/app-shell.txt` instead of editing private `.env`
runtime state or env-style `deploy/app.env` files that hosted workers may be
denied from editing. This keeps the served preview aligned with the app the
coding agent built while still allowing non-hosted deployments to force
`graphical` or `text` through `GIZMOAPP_SHELL` when needed.

## Routing And Prefix Design

The scaffold is designed to run at either:

- `/`
- or a path prefix such as `/<repo-name>/`

That is why the backend, static asset URLs, and API routes all use a
configurable `GIZMOAPP_URL_PREFIX`.

This is important because the deployment model assumes multiple independent apps
can share one host under different path prefixes.

## Configuration Model

There are two different configuration layers by design.

### Git-tracked deployment settings

`deploy/app.env` is for non-secret settings that should reach the server through
explicitly requested Git pushes and cron-driven deploys. Today that mainly means:

- `GIZMOAPP_SHELL`

### Git-tracked hosted shell intent

`deploy/app-shell.txt` is for hosted/student shell intent and may contain one
of:

- `auto`
- `text`
- `graphical`

### Git-tracked optional feature intent

`deploy/features.txt` enables only the public surfaces a derived app actually
uses. Invalid names fail startup rather than silently expanding the app's route
surface.

### Live machine-specific settings

`.env` is for settings that should stay local to one deployed checkout:

- `GIZMOAPP_SECRET_KEY`
- `GIZMOAPP_PORT`
- `GIZMOAPP_DB_PATH`
- `GIZMOAPP_SYSTEMD_USER_SERVICE`
- `GIZMOAPP_URL_PREFIX`
- `GIZMOAPP_ENV`
- `GIZMOAPP_AUTO_MIGRATE`
- `GIZMOAPP_TRUST_PROXY`

For local development, the app reads `deploy/app.env` and then `.env`. If the
requested shell is `auto`, it also checks `deploy/app-shell.txt` before falling
back to changed-file detection.

For deployed services, systemd loads `.env` directly into the process
environment. The deploy scripts keep selected git-tracked keys synchronized from
`deploy/app.env` into `.env`.

## Deployment Model

The intended production shape is:

- one Linux host
- `nginx` as the public entry point
- one user-level `gunicorn` service per app instance
- one app checkout at `/home/kevinlb/bin/<name>`
- one once-per-minute cron entry per app instance

The deployment flow is intentionally split:

1. one-time machine bootstrap
2. per-instance install
3. explicit git push for later updates

This keeps the install model understandable while still allowing many derived
apps to coexist on one server.

## Nginx Layout

Path-based routing should live in a neutral host config, not in an app-named
site file.

Preferred shape:

- one host file such as `/etc/nginx/sites-enabled/vickrey10`
- one snippet per app in `/etc/nginx/gizmoapp-instances/<name>.conf`

That allows future app installs to register themselves without hand-editing the
main host config every time.

## Update And Reload Semantics

The deploy process is intentionally selective:

- static asset changes usually do not require a gunicorn reload
- Python or template changes do require the service to reload or restart
- `deploy/app.env` changes require a restart so the new environment takes effect

Deploys are serialized with `flock`. A candidate commit is validated, backed
up, migrated, reloaded, and checked through `/readyz` before its commit marker
is advanced. Failures restore the previous tracked checkout and restart the
previous service so the next cron run can retry. SQLite uses WAL, a busy timeout,
transactional migrations, and consistent pre-migration backups.

Cron-driven deploys that call `systemctl --user` need the user systemd bus
environment. The scaffold therefore treats `XDG_RUNTIME_DIR` and
`DBUS_SESSION_BUS_ADDRESS` as part of the deployment design, not an incidental
detail.

## Operational Boundaries

The scaffold is optimized for:

- one host
- modest traffic
- anonymous public shells with optional routes disabled by default
- incremental feature development

It is not currently optimized for:

- multi-host orchestration
- background job queues
- offline-first behavior (the starter intentionally has no service worker)
- secret management beyond per-checkout `.env`
- high-write database workloads
- account-bound map providers unless the user explicitly asks for them

## Extension Guidance

When extending the project:

- prefer shared backend changes when both shells need the feature
- keep shell-specific UI isolated under the shell’s own template/static files
- preserve the shared design tokens in `static/app/base.css`
- keep graphical features sprite/bitmap-first; direct polygon/ellipse drawing is
  for overlays, masks, debug visuals, or intentionally vector-simple work
- assume UBC Vancouver for requested location-dependent features only when the
  user specifies no other location
- use OpenStreetMap for requested mapping and scikit-learn for requested ML features
- avoid introducing hidden build steps unless they are clearly worth the added
  operational cost
- preserve prefix-aware routing and multi-app deployment assumptions

If a future change breaks any of those assumptions, update this document,
`README.md`, and `AGENTS.md` together.
