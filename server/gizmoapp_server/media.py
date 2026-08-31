"""Fail-closed helpers for CodingWorkspace image and speech services.

Credentials belong to the server process. Browser code should call a Flask
route which uses these helpers; it must never receive ``GIZMO_MEDIA_API_KEY``.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

DEFAULT_TIMEOUT_SECONDS = 50.0
MAX_TIMEOUT_SECONDS = 55.0
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_OUTPUT_BYTES = 12 * 1024 * 1024
MAX_PROMPT_CHARS = 2000
MAX_SPEECH_CHARS = 4000
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class CourseMediaError(RuntimeError):
    """A safe, user-displayable course-media failure."""


@dataclass(frozen=True)
class GeneratedMedia:
    """Binary output returned by a course media service."""

    data: bytes
    content_type: str
    job_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise CourseMediaError(
            f"{name} is not set. The AI100 platform supplies all course-media settings; "
            "restart the app or server session and try again."
        )
    return value


def available_operations() -> frozenset[str]:
    """Return the operations granted to this app by CodingWorkspace."""
    raw = _required_environment("GIZMO_MEDIA_OPERATIONS")
    return frozenset(item.strip() for item in raw.split(",") if item.strip())


def _require_operation(operation: str) -> None:
    if operation not in available_operations():
        raise CourseMediaError(f"The course platform has not enabled {operation} for this app.")


def _timeout_seconds() -> float:
    raw_value = os.environ.get("GIZMO_MEDIA_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise CourseMediaError("GIZMO_MEDIA_TIMEOUT_SECONDS must be numeric.") from exc
    if value <= 0 or value > MAX_TIMEOUT_SECONDS:
        raise CourseMediaError(
            f"GIZMO_MEDIA_TIMEOUT_SECONDS must be greater than zero and at most "
            f"{MAX_TIMEOUT_SECONDS:g}."
        )
    return value


def _endpoint(path: str) -> str:
    base_url = _required_environment("GIZMO_MEDIA_BASE_URL").rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise CourseMediaError("GIZMO_MEDIA_BASE_URL must be an HTTP(S) URL.")
    return f"{base_url}/{path.lstrip('/')}"


def _validate_text(value: str, *, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CourseMediaError(f"{name} must be non-empty text.")
    if len(value) > maximum:
        raise CourseMediaError(f"{name} must contain at most {maximum} characters.")
    return value


def _validate_steps(steps: int) -> int:
    if isinstance(steps, bool) or not isinstance(steps, int) or not 1 <= steps <= 30:
        raise CourseMediaError("steps must be an integer between 1 and 30.")
    return steps


def _validate_seed(seed: int | None) -> int | None:
    if seed is None:
        return None
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**32:
        raise CourseMediaError("seed must be an integer between 0 and 4294967295.")
    return seed


def _post(path: str, payload: dict[str, Any]) -> tuple[int, str, bytes]:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = Request(
        _endpoint(path),
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {_required_environment('GIZMO_MEDIA_API_KEY')}",
            "Content-Type": "application/json",
            "Accept": "application/json, image/png, audio/wav",
        },
    )
    try:
        with urlopen(request, timeout=_timeout_seconds()) as response:
            status = int(getattr(response, "status", 200))
            content_type = str(response.headers.get_content_type()).lower()
            output = response.read(MAX_OUTPUT_BYTES + 1)
    except HTTPError as exc:
        if exc.code == 403:
            message = "This app is not allowed to use that course-media operation."
        elif exc.code in {401, 404}:
            message = "The course-media credentials are no longer valid. Restart the app and try again."
        else:
            message = "The course-media service could not complete the request. Please try again."
        raise CourseMediaError(message) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise CourseMediaError(
            "The course-media service is temporarily unavailable. Please try again."
        ) from exc
    if len(output) > MAX_OUTPUT_BYTES:
        raise CourseMediaError("The course-media service returned an unexpectedly large result.")
    return status, content_type, output


def _json_result(status: int, content_type: str, body: bytes) -> dict[str, Any]:
    if content_type != "application/json":
        raise CourseMediaError("The course-media service returned an unexpected response.")
    try:
        result = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CourseMediaError("The course-media service returned an invalid response.") from exc
    if status == 202:
        raise CourseMediaError(
            "The course-media worker is busy. Please wait a moment and try again."
        )
    if not isinstance(result, dict):
        raise CourseMediaError("The course-media service returned an invalid response.")
    return result


def generate_image(
    prompt: str,
    *,
    model: str = "stable-diffusion-v1-5",
    steps: int = 20,
    seed: int | None = None,
) -> GeneratedMedia:
    """Generate one 512×512 PNG using a reviewed course GPU model."""
    if model not in {"stable-diffusion-v1-5", "lcm-sd15"}:
        raise CourseMediaError("model must be stable-diffusion-v1-5 or lcm-sd15.")
    _require_operation("image.generate")
    status, content_type, body = _post(
        "images/generations",
        {
            "model": model,
            "prompt": _validate_text(prompt, name="prompt", maximum=MAX_PROMPT_CHARS),
            "size": "512x512",
            "steps": _validate_steps(steps),
            "seed": _validate_seed(seed),
            "wait": True,
            "wait_seconds": int(_timeout_seconds()) - 2,
        },
    )
    result = _json_result(status, content_type, body)
    try:
        image_data = base64.b64decode(result["data"][0]["b64_json"], validate=True)
    except (KeyError, IndexError, TypeError, ValueError, binascii.Error) as exc:
        raise CourseMediaError("The course-media service returned an invalid image.") from exc
    if len(image_data) > MAX_OUTPUT_BYTES or not image_data.startswith(PNG_SIGNATURE):
        raise CourseMediaError("The course-media service returned an invalid image.")
    metadata = result.get("metadata")
    return GeneratedMedia(
        data=image_data,
        content_type="image/png",
        job_id=str(result["jobId"]) if result.get("jobId") else None,
        metadata=metadata if isinstance(metadata, dict) else {},
    )


def edit_image(
    prompt: str,
    image: bytes | bytearray | Path,
    *,
    model: str = "stable-diffusion-v1-5",
    mask: bytes | bytearray | Path | None = None,
    image_guidance_scale: float = 1.5,
    strength: float = 0.6,
    steps: int = 20,
    seed: int | None = None,
) -> GeneratedMedia:
    """Edit a source image and return one 512×512 PNG.

    Select ``stable-diffusion-v1-5-inpainting`` and supply a black/white mask
    to replace only white regions, or select ``instruct-pix2pix`` for
    instruction-oriented edits.
    """
    _require_operation("image.edit")
    if model not in {
        "stable-diffusion-v1-5",
        "stable-diffusion-v1-5-inpainting",
        "instruct-pix2pix",
    }:
        raise CourseMediaError(
            "model must be stable-diffusion-v1-5, "
            "stable-diffusion-v1-5-inpainting, or instruct-pix2pix."
        )
    if isinstance(image, Path):
        try:
            image_data = image.read_bytes()
        except OSError as exc:
            raise CourseMediaError("The source image could not be read.") from exc
    elif isinstance(image, (bytes, bytearray)):
        image_data = bytes(image)
    else:
        raise CourseMediaError("image must be bytes or a pathlib.Path.")
    if not image_data or len(image_data) > MAX_IMAGE_BYTES:
        raise CourseMediaError(f"image must contain between 1 byte and {MAX_IMAGE_BYTES} bytes.")
    if isinstance(strength, bool) or not isinstance(strength, (int, float)):
        raise CourseMediaError("strength must be a number.")
    strength_value = float(strength)
    if not 0 < strength_value <= 1:
        raise CourseMediaError("strength must be greater than zero and at most 1.")
    mask_data: bytes | None = None
    if mask is not None:
        if isinstance(mask, Path):
            try:
                mask_data = mask.read_bytes()
            except OSError as exc:
                raise CourseMediaError("The mask image could not be read.") from exc
        elif isinstance(mask, (bytes, bytearray)):
            mask_data = bytes(mask)
        else:
            raise CourseMediaError("mask must be bytes or a pathlib.Path.")
        if not mask_data or len(mask_data) > MAX_IMAGE_BYTES:
            raise CourseMediaError(
                f"mask must contain between 1 byte and {MAX_IMAGE_BYTES} bytes."
            )
    if model == "stable-diffusion-v1-5-inpainting" and mask_data is None:
        raise CourseMediaError("mask is required for stable-diffusion-v1-5-inpainting.")
    if isinstance(image_guidance_scale, bool) or not isinstance(
        image_guidance_scale, (int, float)
    ):
        raise CourseMediaError("image_guidance_scale must be numeric.")
    image_guidance_value = float(image_guidance_scale)
    if not 0 <= image_guidance_value <= 10:
        raise CourseMediaError("image_guidance_scale must be between 0 and 10.")

    status, content_type, body = _post(
        "images/edits",
        {
            "model": model,
            "prompt": _validate_text(prompt, name="prompt", maximum=MAX_PROMPT_CHARS),
            "image_base64": base64.b64encode(image_data).decode("ascii"),
            "mask_base64": (
                base64.b64encode(mask_data).decode("ascii") if mask_data is not None else None
            ),
            "strength": strength_value,
            "image_guidance_scale": image_guidance_value,
            "steps": _validate_steps(steps),
            "seed": _validate_seed(seed),
            "wait": True,
            "wait_seconds": int(_timeout_seconds()) - 2,
        },
    )
    result = _json_result(status, content_type, body)
    try:
        edited_data = base64.b64decode(result["data"][0]["b64_json"], validate=True)
    except (KeyError, IndexError, TypeError, ValueError, binascii.Error) as exc:
        raise CourseMediaError("The course-media service returned an invalid image.") from exc
    if len(edited_data) > MAX_OUTPUT_BYTES or not edited_data.startswith(PNG_SIGNATURE):
        raise CourseMediaError("The course-media service returned an invalid image.")
    metadata = result.get("metadata")
    return GeneratedMedia(
        data=edited_data,
        content_type="image/png",
        job_id=str(result["jobId"]) if result.get("jobId") else None,
        metadata=metadata if isinstance(metadata, dict) else {},
    )


def synthesize_speech(
    text: str,
    *,
    model: str = "kokoro-82m",
    voice: str = "af_heart",
    language: str = "a",
    speed: float = 1.0,
) -> GeneratedMedia:
    """Synthesize speech with the hosted Kokoro model."""
    _require_operation("audio.speech")
    if model != "kokoro-82m":
        raise CourseMediaError("model must be kokoro-82m.")
    text = _validate_text(text, name="text", maximum=MAX_SPEECH_CHARS)
    if not isinstance(voice, str) or not voice.strip() or len(voice) > 80:
        raise CourseMediaError("voice must be a non-empty name of at most 80 characters.")
    if not isinstance(language, str) or not language.strip() or len(language) > 16:
        raise CourseMediaError("language must be a non-empty code of at most 16 characters.")
    if isinstance(speed, bool) or not isinstance(speed, (int, float)) or not 0.5 <= speed <= 2:
        raise CourseMediaError("speed must be a number between 0.5 and 2.")
    status, content_type, body = _post(
        "audio/speech",
        {
            "model": model,
            "input": text,
            "voice": voice,
            "language": language,
            "speed": float(speed),
            "wait": True,
            "wait_seconds": int(_timeout_seconds()) - 2,
        },
    )
    if status == 202:
        _json_result(status, content_type, body)
    if content_type not in {"audio/wav", "audio/x-wav", "audio/wave"}:
        raise CourseMediaError("The course-media service returned invalid audio.")
    if len(body) < 12 or body[:4] != b"RIFF" or body[8:12] != b"WAVE":
        raise CourseMediaError("The course-media service returned invalid audio.")
    return GeneratedMedia(data=body, content_type="audio/wav")
