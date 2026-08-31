# Course Image and Speech

CodingWorkspace can run small image and speech models on the course Ada GPU
workers. GizmoApp exposes them through the dependency-free, server-side helper
in `server/gizmoapp_server/media.py`.

Use this service when an app needs:

- a generated 512×512 PNG;
- fast drafts or higher-quality final image generation;
- image-to-image, mask-based, or instruction-based editing; or
- multilingual Kokoro speech synthesis as WAV audio.

The browser must call a Flask route in the app. Never call the course service
directly from JavaScript or expose `GIZMO_MEDIA_API_KEY` in HTML, JSON, logs,
SQLite, or browser storage.

## Available Functions

```python
from .media import (
    CourseMediaError,
    edit_image,
    generate_image,
    synthesize_speech,
)
```

- `generate_image(prompt, model="stable-diffusion-v1-5", steps=20, seed=None)`
  returns `GeneratedMedia`. Select `model="lcm-sd15"` and `steps=4` for a fast
  draft.
- `edit_image(prompt, image, model="stable-diffusion-v1-5", strength=0.6,
  steps=20, seed=None)` accepts image
  bytes or a `pathlib.Path` and returns `GeneratedMedia`.
- `edit_image(..., model="stable-diffusion-v1-5-inpainting", mask=mask_bytes)`
  changes white mask regions while preserving black regions.
- `edit_image(..., model="instruct-pix2pix")` follows a natural-language
  editing instruction.
- `synthesize_speech(text, model="kokoro-82m", voice="af_heart",
  language="a", speed=1.0)` returns `GeneratedMedia`.

Read binary output from `result.data` and its MIME type from
`result.content_type`. Image results can also include `result.job_id` and
`result.metadata`.

`available_operations()` reports what CodingWorkspace granted to the running
app. The normal grant is `image.generate`, `image.edit`, and `audio.speech`.
Voice cloning is not enabled for student apps.

## Hosted Model Choices

| Task | Model | Guidance |
| --- | --- | --- |
| Fast image draft | `lcm-sd15` | Use 4 steps and iterate quickly. |
| Final image | `stable-diffusion-v1-5` | Use 15–25 steps. |
| General image variation | `stable-diffusion-v1-5` with `edit_image()` | Adjust `strength` to control how much changes. |
| Masked replacement | `stable-diffusion-v1-5-inpainting` | Supply a same-subject black/white mask; white is edited. |
| Instruction edit | `instruct-pix2pix` | Write a direct command such as “make the cat orange.” |
| Fast expressive speech | `kokoro-82m` | Preferred default. |

Kokoro language codes are `a` (American English), `b` (British English), `e`
(Spanish), `f` (French), `h` (Hindi), `i` (Italian), `p`
(Brazilian Portuguese), and `z` (Mandarin Chinese). Use a voice intended for
the selected language; invalid model voice/language combinations fail safely.

The authenticated platform endpoint `GET
${GIZMO_MEDIA_BASE_URL}/models` provides the current machine-readable catalog.
Application browser code must not call it directly because the bearer token is
server-only.

## Add Prefix-Aware Flask Routes

Add routes inside `register_api_routes()` in
`server/gizmoapp_server/api.py`, before its catch-all unknown API route. Reuse
the existing `prefix` variable and `scoped_path()` so the app continues to work
under its CodingWorkspace URL prefix.

```python
from flask import Response, jsonify, request

from .media import CourseMediaError, generate_image, synthesize_speech


@app.post(scoped_path(prefix, "api/media/image"))
def media_image():
    payload, error = _json_object()
    if error:
        return error
    try:
        result = generate_image(
            str(payload.get("prompt", "")),
            model=str(payload.get("model", "lcm-sd15")),
            steps=int(payload.get("steps", 4)),
            seed=payload.get("seed"),
        )
    except CourseMediaError as exc:
        return jsonify({"errors": [str(exc)]}), 503
    return Response(result.data, mimetype=result.content_type)


@app.post(scoped_path(prefix, "api/media/speech"))
def media_speech():
    payload, error = _json_object()
    if error:
        return error
    try:
        result = synthesize_speech(
            str(payload.get("text", "")),
            model=str(payload.get("model", "kokoro-82m")),
            voice=str(payload.get("voice", "af_heart")),
            language=str(payload.get("language", "a")),
        )
    except CourseMediaError as exc:
        return jsonify({"errors": [str(exc)]}), 503
    return Response(result.data, mimetype=result.content_type)
```

For production-facing apps, distinguish invalid user input with a 400 response
before calling the helper. The compact example returns all safe helper failures
as 503 so the browser can offer a retry.

No `deploy/features.txt` entry is required for these custom routes. That file
controls GizmoApp's optional built-in capability routes, not the
CodingWorkspace media credential.

## Call the App Route from JavaScript

Use the injected `apiBase`; do not hard-code `/api`:

```javascript
const response = await fetch(`${config.apiBase}/media/image`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ prompt: "A friendly robot teaching an AI class" }),
});

if (!response.ok) {
  throw new Error("Image generation is temporarily unavailable.");
}

const imageUrl = URL.createObjectURL(await response.blob());
imageElement.src = imageUrl;
```

Speech uses the same pattern with `${config.apiBase}/media/speech`. Set the
returned blob URL on an `<audio>` element. Revoke old object URLs with
`URL.revokeObjectURL()` when replacing or removing generated media.

## Runtime and Safety Notes

CodingWorkspace injects `GIZMO_MEDIA_BASE_URL`, `GIZMO_MEDIA_API_KEY`, and
`GIZMO_MEDIA_OPERATIONS` only into the app's server process. The token belongs
to one workspace, permits only listed operations, rotates when the preview
restarts, and is revoked when the preview stops.

The helper validates inputs, bounds output size, uses a timeout shorter than
the app server timeout, and raises user-displayable `CourseMediaError`
messages. Requests can take several seconds or report that the GPU worker is
busy. Trigger them only after a user action, disable duplicate submissions
while one is running, and let the user retry.

Current helper limits include:

- image prompts: 2,000 characters;
- speech text: 4,000 characters;
- image steps: 1–30; and
- source images for editing: 8 MB.

All current image models return 512×512 PNGs. The older M60 GPUs have limited
memory, so do not submit duplicate requests or assume a modern cloud-model
latency. Keep the previous image/audio visible while a replacement is being
generated and show a retryable busy message.

Outside CodingWorkspace the media environment variables are normally absent,
so the helper fails closed. Do not commit a real token to make local
development work.
