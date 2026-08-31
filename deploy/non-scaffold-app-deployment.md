# Non-Scaffold App Deployment

The commands in this file are manual host-maintenance commands. They may use
`sudo`, contact the network, reload nginx, or write outside the repository.
Coding agents should not run them unless the user explicitly asks for that
deployment action in the current turn.

This file explains how to deploy and maintain apps on `vickrey10.cs.ubc.ca`
that do **not** use the GizmoApp scaffold.

Examples:

- `AI100` and any other existing app with its own repo, runtime, or service layout
- legacy apps that already existed before the GizmoApp deployment automation
- apps that should still be served under `http://vickrey10.cs.ubc.ca/<name>/`
  but do not have `scripts/install_deployment_instance.sh`

## Rule Of Thumb

- Use GizmoApp automation only for GizmoApp-derived apps.
- Use the neutral nginx host file for **all** path-based routing.
- For non-scaffold apps, manage the app runtime however that app requires, but
  add one explicit nginx snippet for its `/<name>/` route.

## Current Host Layout

The intended nginx structure on `vickrey10.cs.ubc.ca` is:

- host config:
  - `/etc/nginx/sites-available/vickrey10`
  - `/etc/nginx/sites-enabled/vickrey10`
- per-app snippets:
  - `/etc/nginx/gizmoapp-instances/AI100.conf`
  - `/etc/nginx/gizmoapp-instances/gizmotest.conf`
  - `/etc/nginx/gizmoapp-instances/<future-app>.conf`

The file `/etc/nginx/sites-enabled/vickrey10` should include:

```nginx
include /etc/nginx/gizmoapp-instances/*.conf;
```

This keeps one host-level server block and one snippet per routed app.

## How To Add A Non-Scaffold App

Suppose a non-scaffold app should be served at:

```text
http://vickrey10.cs.ubc.ca/myapp/
```

and its application server listens on `127.0.0.1:8123`.

Create:

```text
/etc/nginx/gizmoapp-instances/myapp.conf
```

with contents like:

```nginx
location = /myapp {
    return 302 /myapp/;
}

location /myapp/ {
    proxy_pass http://127.0.0.1:8123;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Prefix /myapp;
    proxy_redirect off;
}
```

Then manually validate nginx, reload it, and verify the route with a browser or
an explicit server-side `GET` request.

Use `GET`, not `HEAD`, when validating older apps. Some apps may respond
correctly to browser `GET` requests while still returning `404` for `HEAD`.

## How To Maintain A Non-Scaffold App

GizmoApp scripts do **not** manage these concerns for non-scaffold apps:

- cloning/updating the repo
- creating the Python or Node environment
- creating the service
- choosing the port
- reloading the app after deploy
- app-specific cron or database setup

Those steps stay app-specific.

What nginx should own:

- the public `/<name>/` route
- path-prefix forwarding headers
- optional redirect from `/<name>` to `/<name>/`

## AI100

`AI100` is the current example of a non-scaffold app.

Important facts:

- It is not managed by GizmoApp install scripts.
- It has its own repo and runtime behavior.
- Its route is currently preserved directly in `/etc/nginx/sites-available/vickrey10`.

Until AI100 gets its own explicit managed snippet, treat it as a manually managed
exception. Do not assume it has:

- a generated nginx snippet under `~/bin/AI100/var/generated/`
- GizmoApp-compatible `.env` keys
- GizmoApp-compatible service names

If AI100 is later normalized into the per-app snippet directory, move only its
nginx route there. Do not assume the rest of its deployment should use the
GizmoApp scaffold.

## Recommendation For Future Apps

For any app that is not derived from GizmoApp:

1. Deploy and operate the app using that app's own repo/runtime/service model.
2. Give it one dedicated nginx snippet in `/etc/nginx/gizmoapp-instances/`.
3. Keep the host-level file neutral and unchanged.

That keeps nginx understandable even when the underlying apps are heterogeneous.
