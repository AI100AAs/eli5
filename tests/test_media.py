from __future__ import annotations

import base64
import json
import os
import unittest
from email.message import Message
from unittest.mock import patch
from urllib.error import HTTPError

from server.gizmoapp_server import media


class FakeResponse:
    def __init__(self, body: bytes, content_type: str, status: int = 200):
        self._body = body
        self.status = status
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, limit: int) -> bytes:
        return self._body[:limit]


class CourseMediaTests(unittest.TestCase):
    def environment(self, operations: str) -> dict[str, str]:
        return {
            "GIZMO_MEDIA_API_KEY": "cwmedia_ws_secret",
            "GIZMO_MEDIA_BASE_URL": "https://course.example/media-proxy/v1",
            "GIZMO_MEDIA_OPERATIONS": operations,
            "GIZMO_MEDIA_TIMEOUT_SECONDS": "12",
        }

    def test_generate_image_uses_server_credential_and_returns_png(self):
        png = media.PNG_SIGNATURE + b"prototype"
        response = {
            "data": [{"b64_json": base64.b64encode(png).decode("ascii")}],
            "jobId": "media-0123456789abcdef0123",
            "metadata": {"seed": 7},
        }
        with patch.dict(os.environ, self.environment("image.generate"), clear=True), patch.object(
            media,
            "urlopen",
            return_value=FakeResponse(json.dumps(response).encode("utf-8"), "application/json"),
        ) as mocked:
            result = media.generate_image("A blue robot", seed=7)

        self.assertEqual(png, result.data)
        self.assertEqual("image/png", result.content_type)
        self.assertEqual({"seed": 7}, result.metadata)
        request = mocked.call_args.args[0]
        self.assertEqual("Bearer cwmedia_ws_secret", request.get_header("Authorization"))
        payload = json.loads(request.data)
        self.assertEqual("A blue robot", payload["prompt"])
        self.assertEqual(10, payload["wait_seconds"])

    def test_synthesize_speech_returns_wav(self):
        wav = b"RIFF\x04\x00\x00\x00WAVEdata"
        with patch.dict(os.environ, self.environment("audio.speech"), clear=True), patch.object(
            media,
            "urlopen",
            return_value=FakeResponse(wav, "audio/wav"),
        ):
            result = media.synthesize_speech("Hello class")
        self.assertEqual(wav, result.data)
        self.assertEqual("audio/wav", result.content_type)

    def test_new_model_options_are_forwarded_without_exposing_credentials(self):
        png = media.PNG_SIGNATURE + b"prototype"
        response = {
            "data": [{"b64_json": base64.b64encode(png).decode("ascii")}],
        }
        with patch.dict(
            os.environ,
            self.environment("image.generate"),
            clear=True,
        ), patch.object(
            media,
            "urlopen",
            return_value=FakeResponse(json.dumps(response).encode(), "application/json"),
        ) as mocked:
            media.generate_image("A cat", model="lcm-sd15", steps=4)
        payload = json.loads(mocked.call_args.args[0].data)
        self.assertEqual("lcm-sd15", payload["model"])
        self.assertEqual(4, payload["steps"])

    def test_inpainting_requires_a_mask(self):
        with patch.dict(os.environ, self.environment("image.edit"), clear=True):
            with self.assertRaisesRegex(media.CourseMediaError, "mask is required"):
                media.edit_image(
                    "replace the center",
                    b"source",
                    model="stable-diffusion-v1-5-inpainting",
                )

    def test_missing_or_ungranted_configuration_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(media.CourseMediaError, "GIZMO_MEDIA_OPERATIONS"):
                media.generate_image("hello")
        with patch.dict(os.environ, self.environment("audio.speech"), clear=True):
            with self.assertRaisesRegex(media.CourseMediaError, "not enabled"):
                media.generate_image("hello")

    def test_inputs_and_outputs_are_bounded(self):
        with patch.dict(os.environ, self.environment("image.generate,image.edit"), clear=True):
            with self.assertRaises(media.CourseMediaError):
                media.generate_image("hello", steps=31)
            with self.assertRaises(media.CourseMediaError):
                media.generate_image("x" * (media.MAX_PROMPT_CHARS + 1))
            with self.assertRaises(media.CourseMediaError):
                media.edit_image("hello", b"x" * (media.MAX_IMAGE_BYTES + 1))
            with self.assertRaises(media.CourseMediaError):
                media.generate_image("hello", model="sdxl")
            with self.assertRaises(media.CourseMediaError):
                media.synthesize_speech("hello", speed=3)

    def test_http_errors_do_not_leak_upstream_details(self):
        error = HTTPError(
            "https://course.example",
            502,
            "secret internal worker path",
            Message(),
            None,
        )
        with patch.dict(os.environ, self.environment("audio.speech"), clear=True), patch.object(
            media,
            "urlopen",
            side_effect=error,
        ):
            with self.assertRaisesRegex(media.CourseMediaError, "could not complete") as caught:
                media.synthesize_speech("Hello")
        self.assertNotIn("secret internal worker path", str(caught.exception))

    def test_busy_worker_returns_actionable_safe_error(self):
        queued = json.dumps({"id": "media-0123456789abcdef0123", "status": "queued"}).encode()
        with patch.dict(os.environ, self.environment("image.generate"), clear=True), patch.object(
            media,
            "urlopen",
            return_value=FakeResponse(queued, "application/json", status=202),
        ):
            with self.assertRaisesRegex(media.CourseMediaError, "worker is busy"):
                media.generate_image("Hello")


if __name__ == "__main__":
    unittest.main()
