from __future__ import annotations

import math
import json
import re
import secrets
import sqlite3
from html.parser import HTMLParser
from ipaddress import ip_address
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from flask import Flask, current_app, g, jsonify, request
from werkzeug.exceptions import BadRequest, HTTPException, RequestEntityTooLarge, UnsupportedMediaType

from .capabilities import capability_payload
from .capabilities.audio import analyze_samples
from .capabilities.mapping import openstreetmap_config
from .capabilities.ml import run_kmeans, sklearn_status
from .capabilities.optimization import nearest_neighbor_route
from .capabilities.search import search_records
from .config import scoped_path
from .db import database_readiness, fetch_sample_nodes, get_db, insert_sample_node
from .db import batch_insert_articles, delete_article, fetch_article, fetch_articles, insert_article, update_article_summary, update_article_tags
from .llm import CourseLLMError, ask, chat

HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
SLUG_RE = re.compile(r"^[a-z0-9-]{3,40}$")
MAX_LABEL_LENGTH = 120
MAX_DESCRIPTION_LENGTH = 2_000
MAX_SEARCH_QUERY_LENGTH = 200
# News sites often include several megabytes of scripts and embedded metadata
# around the article. Keep the download bounded, but do not reject those pages
# before the parser has a chance to find the readable copy.
MAX_IMPORT_HTML_BYTES = 5_000_000
MAX_IMPORT_TEXT_LENGTH = 24_000
MAX_BATCH_ARTICLES = 500


class _ArticleHTMLParser(HTMLParser):
    """Keep the article's metadata and visible copy, not page chrome."""

    SKIP_TAGS = frozenset({"script", "style", "noscript", "svg", "nav", "footer", "header", "aside"})

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.text_parts: list[str] = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() in self.SKIP_TAGS:
            self._skip_depth += 1
        if tag.lower() == "title":
            self._in_title = True
        if tag.lower() == "meta":
            key = attrs_dict.get("name", "").lower() or attrs_dict.get("property", "").lower()
            if key in {"author", "article:published_time", "og:title", "og:description"}:
                self.meta[key] = attrs_dict.get("content", "").strip()

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth or not data.strip():
            return
        cleaned = " ".join(data.split())
        if self._in_title:
            self.title_parts.append(cleaned)
            return
        self.text_parts.append(cleaned)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)


def _fetch_article_page(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Enter a complete http:// or https:// article link.")
    hostname = (parsed.hostname or "").lower()
    if hostname in {"localhost", "localhost.localdomain"}:
        raise ValueError("That link points to a local machine, not a public article.")
    try:
        address = ip_address(hostname)
    except ValueError:
        address = None
    if address and (address.is_private or address.is_loopback or address.is_link_local):
        raise ValueError("That link points to a private network address.")
    request = Request(url, headers={"User-Agent": "Storyline/1.0 article reader"})
    try:
        with urlopen(request, timeout=12) as response:
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "application/xhtml+xml"}:
                raise ValueError("That link does not appear to be an HTML article.")
            raw = response.read(MAX_IMPORT_HTML_BYTES + 1)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Storyline could not reach that article. Check the link and try again.") from exc
    # Parsing a bounded prefix is enough for most pages and avoids making a
    # large page an unbounded memory or model-input request.
    raw = raw[:MAX_IMPORT_HTML_BYTES]
    parser = _ArticleHTMLParser()
    parser.feed(raw.decode("utf-8", errors="replace"))
    title = parser.meta.get("og:title") or " ".join(parser.title_parts).strip()
    text = " ".join(parser.text_parts)
    if not text or len(text) < 120:
        raise ValueError("Storyline could not find enough readable article text on that page.")
    return title[:240], text[:MAX_IMPORT_TEXT_LENGTH]


def _ai_article_fields(url: str, page_title: str, text: str, existing: list[dict[str, Any]]) -> dict[str, Any]:
    library = "\n".join(f"- {item['title']} ({item['published_at']}): {item['summary']}" for item in existing[:30])
    prompt = (
        "You are Storyline, a careful news-reading assistant. Extract the supplied article into JSON only. "
        "Use exactly these keys: title, source, published_at, topic, summary, relationship, relationship_type, tags. "
        "tags must be an array of 3-6 short lowercase strings describing the subject. "
        "summary must explain the article in 2-4 simple sentences for a child without losing uncertainty. "
        "relationship should describe an update, related thread, or contradiction with the saved library, or be empty. "
        "relationship_type must be one of update, related, contradiction, or empty. "
        "Use YYYY-MM-DD when the publication date is clear, otherwise use today's date. Never invent a publisher or facts. "
        f"\nURL: {url}\nPage title: {page_title}\nSaved library:\n{library or '(empty)'}\nArticle text:\n{text}"
    )
    result = ask(prompt, max_tokens=900).strip()
    result = re.sub(r"^```(?:json)?\s*|\s*```$", "", result, flags=re.IGNORECASE)
    try:
        fields = json.loads(result)
    except json.JSONDecodeError as exc:
        raise CourseLLMError("The course model returned an unreadable article extraction. Please try again.") from exc
    if not isinstance(fields, dict):
        raise CourseLLMError("The course model returned an invalid article extraction. Please try again.")
    required = ("title", "source", "published_at", "topic", "summary", "relationship", "relationship_type", "tags")
    if any(not isinstance(fields.get(key), str) for key in required):
        if not isinstance(fields.get("tags"), list) or any(not isinstance(tag, str) for tag in fields["tags"]):
            raise CourseLLMError("The course model returned incomplete article details. Please try again.")
    if any(not isinstance(fields.get(key), str) for key in required[:-1]):
        raise CourseLLMError("The course model returned incomplete article details. Please try again.")
    fields["tags"] = [tag.strip().lower()[:32] for tag in fields["tags"] if tag.strip()][:6]
    return {**{key: fields[key].strip() for key in required[:-1]}, "tags": fields["tags"]}


def _ai_article_tags(article: dict[str, Any]) -> list[str]:
    result = ask(
        "Return JSON only as an array of 3-6 short lowercase tags for this news article. "
        "Do not include punctuation or broad tags like news.\n"
        f"Headline: {article['title']}\nTopic: {article['topic']}\nSummary: {article['summary']}\n"
        f"Text: {article['body'] or article['summary']}",
        max_tokens=200,
    ).strip()
    result = re.sub(r"^```(?:json)?\s*|\s*```$", "", result, flags=re.IGNORECASE)
    try:
        tags = json.loads(result)
    except json.JSONDecodeError as exc:
        raise CourseLLMError("The course model returned unreadable tags. Please try again.") from exc
    if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
        raise CourseLLMError("The course model returned invalid tags. Please try again.")
    return [tag.strip().lower()[:32] for tag in tags if tag.strip()][:6]


def _health_payload() -> dict[str, Any]:
    return {
        "status": "ok",
        "serverTime": datetime.now(UTC).isoformat(),
    }


def _bootstrap_payload() -> dict[str, Any]:
    return {
        "app": {
            "name": current_app.config["APP_NAME"],
            "tagline": current_app.config["APP_TAGLINE"],
            "mode": "public",
            "shell": current_app.config["APP_SHELL"],
            "shellLabel": current_app.config["APP_SHELL_LABEL"],
        },
        "health": _health_payload(),
        "availableShells": current_app.config["AVAILABLE_SHELLS"],
    }


def _api_root() -> str:
    return scoped_path(current_app.config["URL_PREFIX"], "api").rstrip("/")


def _is_json_surface() -> bool:
    api_root = _api_root()
    return (
        request.path == api_root
        or request.path.startswith(f"{api_root}/")
        or request.path.endswith("/healthz")
        or request.path.endswith("/readyz")
        or request.path in {"/healthz", "/readyz"}
    )


def _error_response(message: str, status: int):
    return jsonify({"errors": [message], "requestId": getattr(g, "request_id", None)}), status


def _json_object() -> tuple[dict[str, Any] | None, tuple[Any, int] | None]:
    if not request.is_json:
        return None, _error_response("Content-Type must be application/json", 415)
    try:
        payload = request.get_json(silent=False)
    except (BadRequest, UnsupportedMediaType):
        return None, _error_response("Request body must contain valid JSON", 400)
    if not isinstance(payload, dict):
        return None, _error_response("JSON request body must be an object", 400)
    return payload, None


def _finite_number(payload: dict[str, Any], key: str, default: float) -> float:
    value = float(payload.get(key, default))
    if not math.isfinite(value):
        raise ValueError(f"{key} must be finite")
    return value


def _normalize_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    raw_slug = payload.get("slug", "")
    raw_label = payload.get("label", "")
    raw_description = payload.get("description", "")
    raw_color = payload.get("accent_color", "#72d1c2")

    for name, value in (
        ("slug", raw_slug),
        ("label", raw_label),
        ("description", raw_description),
        ("accent_color", raw_color),
    ):
        if not isinstance(value, str):
            errors.append(f"{name} must be a string")

    cleaned = {
        "slug": raw_slug.strip() if isinstance(raw_slug, str) else "",
        "label": raw_label.strip() if isinstance(raw_label, str) else "",
        "description": raw_description.strip() if isinstance(raw_description, str) else "",
        "accent_color": raw_color.strip() if isinstance(raw_color, str) else "",
    }
    cleaned["description"] = cleaned["description"] or "Created through the sample API."

    if not SLUG_RE.fullmatch(cleaned["slug"]):
        errors.append("slug must be 3-40 characters of lowercase letters, digits, or hyphens")
    if len(cleaned["label"]) < 2 or len(cleaned["label"]) > MAX_LABEL_LENGTH:
        errors.append(f"label must be 2-{MAX_LABEL_LENGTH} characters")
    if len(cleaned["description"]) > MAX_DESCRIPTION_LENGTH:
        errors.append(f"description must be at most {MAX_DESCRIPTION_LENGTH} characters")
    if not HEX_COLOR_RE.fullmatch(cleaned["accent_color"]):
        errors.append("accent_color must be a 6-digit hex color like #72d1c2")

    try:
        cleaned["x"] = min(0.92, max(0.08, _finite_number(payload, "x", 0.5)))
        cleaned["y"] = min(0.92, max(0.08, _finite_number(payload, "y", 0.5)))
        cleaned["radius"] = min(0.2, max(0.06, _finite_number(payload, "radius", 0.11)))
    except (TypeError, ValueError, OverflowError):
        errors.append("x, y, and radius must be finite numbers")

    return cleaned, errors


def register_api_routes(app: Flask) -> None:
    prefix = app.config["URL_PREFIX"]
    enabled_features = frozenset(app.config["ENABLED_FEATURES"])

    @app.before_request
    def assign_request_id():
        g.request_id = secrets.token_hex(8)

    @app.after_request
    def harden_response(response):
        response.headers.setdefault("X-Request-ID", getattr(g, "request_id", ""))
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        return response

    @app.errorhandler(RequestEntityTooLarge)
    def request_too_large(_: RequestEntityTooLarge):
        if _is_json_surface():
            return _error_response("Request body is too large", 413)
        return "Request body is too large", 413

    @app.errorhandler(HTTPException)
    def http_error(error: HTTPException):
        if _is_json_surface():
            return _error_response(error.description or error.name, error.code or 500)
        return error

    @app.errorhandler(Exception)
    def unexpected_error(error: Exception):
        current_app.logger.exception("Unhandled request error")
        if _is_json_surface():
            return _error_response("The server could not complete the request", 500)
        return "The server could not complete the request", 500

    @app.get(scoped_path(prefix, "healthz"))
    def healthz():
        return jsonify(_health_payload())

    @app.get(scoped_path(prefix, "readyz"))
    def readyz():
        ready, detail = database_readiness(current_app.config)
        return jsonify({"status": "ready" if ready else "not-ready", **detail}), 200 if ready else 503

    @app.get(scoped_path(prefix, "api/bootstrap"))
    def bootstrap():
        return jsonify(_bootstrap_payload())

    @app.get(scoped_path(prefix, "api/capabilities"))
    def capabilities():
        api_base = scoped_path(prefix, "api").rstrip("/")
        return jsonify(capability_payload(api_base, enabled_features))

    if "search" in enabled_features:
        @app.get(scoped_path(prefix, "api/search"))
        def search():
            query = request.args.get("q", "")
            if len(query) > MAX_SEARCH_QUERY_LENGTH:
                return _error_response(f"q must be at most {MAX_SEARCH_QUERY_LENGTH} characters", 400)
            return jsonify(search_records(get_db(), query))

    if "mapping" in enabled_features:
        @app.get(scoped_path(prefix, "api/map/default"))
        def map_default():
            return jsonify(openstreetmap_config())

    if "machine-learning" in enabled_features:
        @app.get(scoped_path(prefix, "api/ml/status"))
        def ml_status():
            return jsonify(sklearn_status())

        @app.post(scoped_path(prefix, "api/ml/kmeans"))
        def ml_kmeans():
            payload, error = _json_object()
            if error:
                return error
            result, errors, status = run_kmeans(payload)
            if errors:
                return jsonify({"errors": errors, "requestId": g.request_id, **result}), status
            return jsonify(result)

    if "optimization" in enabled_features:
        @app.post(scoped_path(prefix, "api/optimize/route"))
        def optimize_route():
            payload, error = _json_object()
            if error:
                return error
            result, errors = nearest_neighbor_route(payload)
            if errors:
                return jsonify({"errors": errors, "requestId": g.request_id}), 400
            return jsonify(result)

    if "audio" in enabled_features:
        @app.post(scoped_path(prefix, "api/audio/analyze"))
        def audio_analyze():
            payload, error = _json_object()
            if error:
                return error
            result, errors = analyze_samples(payload)
            if errors:
                return jsonify({"errors": errors, "requestId": g.request_id}), 400
            return jsonify(result)

    if "sample-nodes" in enabled_features:
        @app.route(scoped_path(prefix, "api/sample-nodes"), methods=["GET", "POST"])
        def sample_nodes():
            connection = get_db()
            if request.method == "GET":
                return jsonify({"sampleNodes": fetch_sample_nodes(connection)})

            payload, error = _json_object()
            if error:
                return error
            cleaned, errors = _normalize_payload(payload)
            if errors:
                return jsonify({"errors": errors, "requestId": g.request_id}), 400

            try:
                record = insert_sample_node(connection, cleaned)
            except sqlite3.IntegrityError:
                return jsonify({"errors": ["slug already exists"], "requestId": g.request_id}), 409
            except sqlite3.OperationalError:
                current_app.logger.exception("Database write remained unavailable after retries")
                return _error_response("Database is temporarily busy; retry shortly", 503)

            return jsonify({"sampleNode": record}), 201

    @app.route(scoped_path(prefix, "api/articles"), methods=["GET", "POST"])
    def articles():
        connection = get_db()
        if request.method == "GET":
            query = request.args.get("q", "")[:200]
            return jsonify({"articles": fetch_articles(connection, query)})

        payload, error = _json_object()
        if error:
            return error
        required = ("title", "source")
        errors = [f"{key} is required" for key in required if not isinstance(payload.get(key), str) or not payload[key].strip()]
        if len(str(payload.get("title", ""))) > 240 or len(str(payload.get("source", ""))) > 120:
            errors.append("title or source is too long")
        if errors:
            return jsonify({"errors": errors, "requestId": g.request_id}), 400
        record = insert_article(connection, {
            "title": payload["title"].strip(),
            "source": payload["source"].strip(),
            "url": str(payload.get("url", "")).strip()[:500],
            "published_at": str(payload.get("published_at", datetime.now(UTC).date().isoformat()))[:30],
            "topic": str(payload.get("topic", "Saved story")).strip()[:80] or "Saved story",
            "summary": str(payload.get("summary", "Not simplified yet.")).strip()[:2000] or "Not simplified yet.",
            "body": str(payload.get("body", "")).strip()[:10000],
            "tags": [str(tag).strip().lower()[:32] for tag in payload.get("tags", []) if str(tag).strip()][:6],
        })
        return jsonify({"article": record}), 201

    @app.get(scoped_path(prefix, "api/articles/export"))
    def export_articles():
        records = fetch_articles(get_db())
        export_records = [{key: article.get(key) for key in (
            "title", "source", "url", "published_at", "topic", "summary", "body",
            "relationship", "relationship_type", "is_recommended", "tags",
        )} for article in records]
        response = jsonify({"format": "storyline-articles", "version": 1, "articles": export_records})
        response.headers["Content-Disposition"] = "attachment; filename=storyline-articles.json"
        return response

    @app.post(scoped_path(prefix, "api/articles/import-batch"))
    def import_articles_batch():
        payload, error = _json_object()
        if error:
            return error
        raw_articles = payload.get("articles")
        if not isinstance(raw_articles, list):
            return _error_response("articles must be an array from a Storyline JSON export", 400)
        if len(raw_articles) > MAX_BATCH_ARTICLES:
            return _error_response(f"Import up to {MAX_BATCH_ARTICLES} articles at a time", 400)

        valid: list[dict[str, Any]] = []
        errors: list[str] = []
        for index, raw in enumerate(raw_articles, 1):
            if not isinstance(raw, dict):
                errors.append(f"Article {index} must be an object")
                continue
            title, source = raw.get("title", ""), raw.get("source", "")
            if not isinstance(title, str) or not title.strip() or not isinstance(source, str) or not source.strip():
                errors.append(f"Article {index} needs a title and source")
                continue
            tags = raw.get("tags", [])
            if not isinstance(tags, list):
                tags = []
            valid.append({
                "title": title.strip()[:240], "source": source.strip()[:120],
                "url": str(raw.get("url", "")).strip()[:500],
                "published_at": str(raw.get("published_at", datetime.now(UTC).date().isoformat()))[:30],
                "topic": str(raw.get("topic", "Saved story")).strip()[:80] or "Saved story",
                "summary": str(raw.get("summary", "Not simplified yet.")).strip()[:2000] or "Not simplified yet.",
                "body": str(raw.get("body", "")).strip()[:10000],
                "relationship": str(raw.get("relationship", "")).strip()[:500],
                "relationship_type": str(raw.get("relationship_type", "")).strip()[:30],
                "is_recommended": 1 if raw.get("is_recommended") else 0,
                "tags": [str(tag).strip().lower()[:32] for tag in tags if str(tag).strip()][:6],
            })
        if not valid:
            return jsonify({"errors": errors or ["The file contains no articles"], "requestId": g.request_id}), 400
        try:
            imported, skipped = batch_insert_articles(get_db(), valid)
        except sqlite3.OperationalError:
            current_app.logger.exception("Batch article import failed")
            return _error_response("Database is temporarily busy; retry shortly", 503)
        return jsonify({"imported": len(imported), "skipped": skipped, "invalid": len(errors), "errors": errors, "articles": imported})

    @app.post(scoped_path(prefix, "api/articles/import"))
    def import_article():
        payload, error = _json_object()
        if error:
            return error
        url = payload.get("url", "")
        if not isinstance(url, str) or len(url.strip()) > 500:
            return _error_response("url must be a link up to 500 characters", 400)
        url = url.strip()
        try:
            page_title, article_text = _fetch_article_page(url)
            fields = _ai_article_fields(url, page_title, article_text, fetch_articles(get_db()))
        except ValueError as exc:
            return _error_response(str(exc), 400)
        except CourseLLMError as exc:
            return _error_response(str(exc), 503)
        record = insert_article(get_db(), {
            **fields,
            "title": fields["title"][:240] or page_title or "Imported story",
            "source": fields["source"][:120] or urlparse(url).netloc,
            "url": url,
            "published_at": fields["published_at"][:30] or datetime.now(UTC).date().isoformat(),
            "topic": fields["topic"][:80] or "Saved story",
            "summary": fields["summary"][:2000],
            "body": article_text,
            "relationship": fields["relationship"][:500],
            "relationship_type": fields["relationship_type"][:30],
            "tags": fields["tags"],
        })
        return jsonify({"article": record}), 201

    @app.delete(scoped_path(prefix, "api/articles/<int:article_id>"))
    def remove_article(article_id: int):
        if not delete_article(get_db(), article_id):
            return _error_response("Article not found", 404)
        return jsonify({"deleted": article_id})

    @app.post(scoped_path(prefix, "api/articles/<int:article_id>/tags"))
    def tag_article(article_id: int):
        payload = {}
        if request.data:
            payload, error = _json_object()
            if error:
                return error
        article = payload.get("article") or fetch_article(get_db(), article_id)
        if not article:
            return _error_response("Article not found", 404)
        try:
            tags = _ai_article_tags(article)
        except CourseLLMError as exc:
            return _error_response(str(exc), 503)
        updated = update_article_tags(get_db(), article_id, tags) if not payload.get("article") else {**article, "tags": tags}
        return jsonify({"article": updated})

    @app.post(scoped_path(prefix, "api/articles/<int:article_id>/simplify"))
    def simplify_article(article_id: int):
        payload = {}
        if request.data:
            payload, error = _json_object()
            if error:
                return error
        article = payload.get("article") or fetch_article(get_db(), article_id)
        if not article:
            return _error_response("Article not found", 404)
        source_text = article["body"] or article["summary"]
        prompt = (
            "Rewrite this news article summary for a busy reader using very simple language. "
            "Use 2-4 short sentences. Keep uncertainty and do not invent facts. Return only the rewrite.\n\n"
            f"Headline: {article['title']}\nSource: {article['source']}\nText: {source_text}"
        )
        try:
            summary = ask(prompt, max_tokens=350)
        except CourseLLMError as exc:
            return _error_response(str(exc), 503)
        updated = update_article_summary(get_db(), article_id, summary.strip()) if not payload.get("article") else {**article, "summary": summary.strip()}
        return jsonify({"article": updated})

    @app.post(scoped_path(prefix, "api/articles/<int:article_id>/chat"))
    def chat_about_article(article_id: int):
        payload, error = _json_object()
        if error:
            return error
        article = payload.get("article")
        messages = payload.get("messages")
        if not isinstance(article, dict) or not isinstance(article.get("title"), str):
            article = fetch_article(get_db(), article_id)
        if not article:
            return _error_response("Article not found", 404)
        if not isinstance(messages, list) or not messages or len(messages) > 10:
            return _error_response("messages must contain 1-10 chat messages", 400)
        cleaned_messages = []
        for message in messages:
            if not isinstance(message, dict) or message.get("role") not in {"user", "assistant"}:
                return _error_response("chat messages must be user or assistant messages", 400)
            content = message.get("content")
            if not isinstance(content, str) or not content.strip() or len(content) > 2000:
                return _error_response("each chat message must contain 1-2000 characters", 400)
            cleaned_messages.append({"role": message["role"], "content": content.strip()})
        if cleaned_messages[-1]["role"] != "user":
            return _error_response("the latest chat message must be from the user", 400)
        context = (
            "You are Storyline's thoughtful article companion. Answer questions using only the article context. "
            "Be clear about uncertainty, do not invent facts, and say when the article does not provide an answer. "
            "Keep responses focused and conversational.\n\n"
            f"Headline: {str(article.get('title', ''))[:240]}\n"
            f"Source: {str(article.get('source', ''))[:120]}\n"
            f"Topic: {str(article.get('topic', ''))[:80]}\n"
            f"Summary: {str(article.get('summary', ''))[:2000]}\n"
            f"Article text: {str(article.get('body', '') or article.get('summary', ''))[:12000]}"
        )
        try:
            answer = chat([{"role": "system", "content": context}, *cleaned_messages], max_tokens=500)
        except CourseLLMError as exc:
            return _error_response(str(exc), 503)
        return jsonify({"answer": answer.strip()})

    @app.route(
        scoped_path(prefix, "api/<path:unmatched_path>"),
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    )
    def unknown_api_route(unmatched_path: str):
        return _error_response(f"Unknown or disabled API route: {unmatched_path}", 404)
