# AGENTS.md

## Purpose

GizmoApp is the blank Flask/SQLite starter cloned into CodingWorkspace for
student projects. Keep ordinary app-building turns focused: read this file and
`docs/agent-map.md`, then open only the files and task-specific guidance needed
for the student's request.

## Student Build Loop

1. Treat a feature, app, visual, or fix request as an implementation task. Make
   a visible working change rather than stopping after repository inspection.
2. Choose one starting path:
   - Forms, lists, dashboards, records, and workflows: edit
     `server/gizmoapp_server/templates/index_text.html` and
     `server/gizmoapp_server/static/app/text/`.
   - Canvas, animation, games, simulations, and rich visuals: edit
     `server/gizmoapp_server/templates/index.html` and
     `server/gizmoapp_server/static/app/`.
   - Shared routes, data, or persistence: edit `api.py`, `views.py`, and `db.py`
     under `server/gizmoapp_server/`.
3. When the request clearly chooses a public shell, set `deploy/app-shell.txt`
   to `text` or `graphical` in the same commit. Do not edit `.env` or use
   `deploy/app.env` for hosted shell intent.
4. Keep routes and assets path-prefix-safe. Use the provided base path/client
   configuration rather than hard-coded `/api` or `/static` URLs.
5. Use Flask/SQLite APIs for persistent state. CodingWorkspace previews do not
   guarantee cookies, service workers, localStorage, sessionStorage, IndexedDB,
   same-origin access, or access to the parent page.
6. Run `make validate`. It performs the repository's Python and JavaScript
   checks without Node or automatic dependency installation.
7. Confirm `git status` or `git log` shows the intended app change. Commit
   locally when the hosted platform asks; never push from a student workspace.

Public shells should contain only the app the student requested. Do not restore
starter Admin/Install/status chrome or demo content unless it is part of the
request.

## Task-Specific Rules

- Graphics: start with the graphical files above. Prefer supplied or generated
  PNG/WebP sprites for realistic subjects and render them with `drawImage`.
  Use procedural primitives for intentionally simple/stylized work or as a
  clearly described placeholder. See `docs/agent-extension-guide.md` for the
  detailed graphics and visual-verification path.
- AI features: use `ask()` or `chat()` from
  `server/gizmoapp_server/llm.py`. The platform supplies the app's separate
  model credentials; never hard-code keys or reuse the coding agent's key.
  Call the model only in response to user actions and surface helper errors.
- Media generation: use `server/gizmoapp_server/media.py` only from server
  routes after user actions. Never expose or log `GIZMO_MEDIA_API_KEY`.
- Audio, search, optimization, maps, and ML: use the matching lazy capability
  module, add its slug to tracked `deploy/features.txt`, and read only its
  section in `docs/agent-extension-guide.md`. Optional routes are off until
  that tracked intent enables them.
- New Python dependency: add it to `server/requirements.txt`. Keep optional ML
  dependencies in `server/requirements-ml.txt`, pin direct runtime versions,
  and validate the upgrade deliberately.

## Validation And Safety

- Do not look for or install Node. Use `make js-check` for a JavaScript-only
  check or `make validate` for the normal validation pass.
- For visual changes, run `ALLOW_BROWSER_CHECK=1 make visual-check` only when
  Playwright/Chromium are already available and browser automation is permitted.
  Inspect `var/visual-report/index.html`; otherwise report that visual checking
  was unavailable. Do not install browser tooling automatically.
- In template-derived/student repositories, do not fetch, push, install
  packages, run servers or browsers, SSH, use sudo, deploy, or write outside the
  workspace unless the user or hosted platform instructions explicitly
  authorize that action in the current turn.
- Keep secrets, `.env`, databases, logs, generated reports, and other local
  runtime artifacts out of Git; update `.gitignore` if a new artifact appears.
- Preserve the build-free frontend, Flask backend, SQLite default, two-shell
  structure, and prefix-aware routing unless the user deliberately changes one
  of those decisions.

## Starter Repository Maintenance

These rules apply when maintaining the canonical GizmoApp source repository,
not a student/template-derived clone:

- Commit completed source changes at the end of the turn and push the current
  branch to its configured remote. This is standing user approval for GizmoApp
  source-repository pushes only.
- If Git identity or a stale index lock blocks the commit, run
  `make commit-ready`; it configures only this repository and removes only stale
  locks.
- Update this file when an important workflow, safety, architecture, or
  operational rule changes. Put detailed deployment procedures in `README.md`
  or `deploy/`, not in this always-loaded file.

## Read More Only When Needed

- File routing and skip list: `docs/agent-map.md`
- Feature recipes: `docs/agent-extension-guide.md`
- Architecture rationale: `docs/design-overview.md`
- Local setup, AI/media helpers, and deployment: `README.md`
- Deployment implementation: matching files under `deploy/` and `scripts/`
