# Agent Map

Use this map after `AGENTS.md` to choose the smallest useful file set. Do not
read deployment, capability, or verification internals before making an
ordinary app change.

## Choose A Path

| Student request | Start here |
| --- | --- |
| Forms, lists, dashboards, text tools, records, workflows | `server/gizmoapp_server/templates/index_text.html`, `server/gizmoapp_server/static/app/text/main.js`, `server/gizmoapp_server/static/app/text/styles.css` |
| Canvas, animation, games, simulations, sprites, rich visuals | `server/gizmoapp_server/templates/index.html`, `server/gizmoapp_server/static/app/main.js`, `server/gizmoapp_server/static/app/scene.js`, `server/gizmoapp_server/static/app/styles.css` |
| Shared data, persistence, or API behavior | `server/gizmoapp_server/api.py`, `server/gizmoapp_server/db.py`, `server/gizmoapp_server/views.py` |
| Runtime shell choice | `server/gizmoapp_server/shells.py`, `server/wsgi.py`, `deploy/app-shell.txt` |

Set `deploy/app-shell.txt` to `text` or `graphical` when the request clearly
chooses a shell. Do not edit `.env` or use `deploy/app.env` for CodingWorkspace
shell intent.

## Read More Only For The Requested Capability

| Need | Read |
| --- | --- |
| Graphics, audio, search, maps, optimization, or ML | Matching section of `docs/agent-extension-guide.md`, then the matching capability module if needed |
| AI/LLM feature | `README.md` section “Course AI Model (AI100)” and `server/gizmoapp_server/llm.py` |
| Generated image, image editing, or speech | `docs/course-media.md`, then `server/gizmoapp_server/media.py` |
| Architecture rationale | `docs/design-overview.md` |
| Local setup or validation | Relevant section of `README.md` |
| Deployment, nginx, cron, services, or server install | Relevant `README.md` deployment section and matching file under `deploy/` or `scripts/` |

## Finish The Turn

- Run `make validate`; use `make js-check` only for a narrower JavaScript pass.
- For graphics, run `ALLOW_BROWSER_CHECK=1 make visual-check` only when its
  browser dependencies are already available and permitted.
- Check `git status --short` and leave a real app change or a concrete blocker.
- Canonical GizmoApp source maintenance is committed and pushed. Hosted/student
  workspaces may commit locally but must not push.

## Skip Unless The Task Needs Them

- nginx, cron, systemd, deployment, and machine-install scripts
- visual-verification implementation internals
- capability modules unrelated to the request
- historical migration and host-transition scripts

Start with a visible implementation. Broaden the search only when that version
needs another capability or validation points to a specific subsystem.
