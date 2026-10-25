"""Standalone per-platform senders and error helpers for send_message."""

from pm import install_hint
import logging
import os
import re

from agent.redact import redact_sensitive_text

logger = logging.getLogger("tools.send_message_tool")

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".3gp"}
_AUDIO_EXTS = {".ogg", ".opus", ".mp3", ".m2a", ".wav", ".m4a", ".flac"}
_VOICE_EXTS = {".ogg", ".opus"}
_TELEGRAM_SEND_AUDIO_EXTS = {".mp3", ".m4a"}  # sendAudio accepts only these; other audio -> sendVoice / document
# Captionable on the media bubble; voice/audio notes excluded (a caption there reads as a separate label).
_CAPTIONABLE_EXTS = _IMAGE_EXTS | _VIDEO_EXTS | {".pdf", ".doc", ".docx", ".txt", ".md", ".csv", ".xlsx", ".zip"}
# Native caption limits (chars): Telegram caps photo/video at 1024; one conservative shared ceiling elsewhere.
_TELEGRAM_CAPTION_LIMIT = 1024
_DEFAULT_CAPTION_LIMIT = 4096


def _media_caption_split(text, media_files, *, max_caption_len):
    """Single chokepoint deciding whether text rides on the media bubble as its caption:
    ``(caption, "")`` only for exactly one captionable file (not a voice/audio note) whose
    text fits ``max_caption_len``, else ``(None, text)`` — multi-file caption→file association
    is ambiguous. Length is codepoints (never under-counts Telegram's UTF-16 units for BMP
    text); the Telegram sender re-checks the *formatted* caption since escaping inflates it."""
    stripped = (text or "").strip()
    media = media_files or []
    if (not stripped or len(media) != 1 or len(stripped) > max_caption_len or media[0][1]
            or os.path.splitext(media[0][0])[1].lower() not in _CAPTIONABLE_EXTS):
        return None, text
    return stripped, ""


_URL_SECRET_QUERY_RE = re.compile(
    r"([?&](?:access_token|api[_-]?key|auth[_-]?token|token|signature|sig)=)([^&#\s]+)", re.IGNORECASE)
_GENERIC_SECRET_ASSIGN_RE = re.compile(
    r"\b(access_token|api[_-]?key|auth[_-]?token|signature|sig)\s*=\s*([^\s,;]+)", re.IGNORECASE)


def _sanitize_error_text(text) -> str:
    """Redact secrets from error text before surfacing it to users/models."""
    redacted = _URL_SECRET_QUERY_RE.sub(lambda m: f"{m.group(1)}***", redact_sensitive_text(text))
    return _GENERIC_SECRET_ASSIGN_RE.sub(lambda m: f"{m.group(1)}=***", redacted)


def _error(message: str) -> dict:
    """Build a standardized error payload with redacted content."""
    return {"error": _sanitize_error_text(message)}


def _success(platform: str, chat_id, warnings=None, **fields) -> dict:
    """Standard success payload; ``warnings`` is only included when non-empty."""
    return {"success": True, "platform": platform, "chat_id": chat_id, **fields,
            **({"warnings": warnings} if warnings else {})}


_NO_DELIVERABLE = "No deliverable text or media remained after processing MEDIA tags"

_TELEGRAM_TRANSIENT_MARKERS = ("bad gateway", "502", "too many requests", "429", "service unavailable", "503",
                               "gateway timeout", "504")














def _adapter_media_method(ext, voice, force_document=False):
    """``(adapter method, kind)``: document when forced, else image / video / voice by
    extension (``voice`` already folds in the caller's audio rule)."""
    if force_document:
        return "send_document", "document"
    if ext in _IMAGE_EXTS:
        return "send_image_file", "image"
    if ext in _VIDEO_EXTS:
        return "send_video", "video"
    return ("send_voice", "audio") if voice else ("send_document", "document")












def _live_adapter(platform, *, lookup_failed_warning=None):
    """``(runner, adapter)`` for the in-process gateway; ``(None, None)`` standalone (cron);
    ``(runner, None)`` when the lookup fails — logged when a warning is given, never silently
    swallowed (a silent fall-through could recreate a reconnect storm).

    Multiplex: the adapter is the ACTIVE PROFILE's (``_profile_adapters[profile]``), never a bare
    ``runner.adapters`` hit — that map holds the default profile's bots, so a secondary profile's turn
    would post/react with the default bot's identity. A profile with no adapter for the platform
    yields ``None`` (fail closed → the caller's scoped standalone sender or an error), never the
    default bot. Same resolver shape as ``hermes_cli/platform_actions.py::_resolve_adapter``."""
    try:
        from gateway.run import _gateway_runner_ref
        runner = _gateway_runner_ref()
    except Exception:
        runner = None
    if runner is None:
        return None, None
    try:
        resolve = getattr(runner, "_authorization_adapter", None)
        if not callable(resolve):  # bare runner stubs without the authz mixin
            return runner, runner.adapters.get(platform)
        from hermes_cli.profiles import get_active_profile_name
        return runner, resolve(platform, get_active_profile_name())
    except Exception:
        if lookup_failed_warning:
            logger.warning(lookup_failed_warning, exc_info=True)
        return runner, None


def _plugin_standalone_sender(platform_name, *, label=None, discover=True):
    """``(standalone_sender_fn, None)`` for a registered plugin or ``(None, error_dict)``;
    ``discover`` runs the idempotent plugin scan first."""
    from gateway.platform_registry import platform_registry
    if discover:
        from hermes_cli.plugins import discover_plugins
        discover_plugins()
    entry = platform_registry.get(platform_name)
    if entry is None or entry.standalone_sender_fn is None:
        return None, {"error": f"{label or platform_name} plugin not registered or missing standalone_sender_fn"}
    return entry.standalone_sender_fn, None


async def _registry_standalone_send(platform_name, pconfig, chat_id, message, thread_id=None):
    """One-shot text send through a plugin's ``standalone_sender_fn``."""
    sender, err = _plugin_standalone_sender(platform_name)
    return err or await sender(pconfig, chat_id, message, thread_id=thread_id)


async def _resolve_slack_user_target(token, chat_id):
    """Resolve ``user:U...`` / ``user_name:<handle>`` to a D... DM conversation (chat.postMessage
    needs a conversation ID); ``user_name:`` goes through users.list first (stable handle match
    only); other ids pass through. ``(chat_id, None)`` or ``(None, error_dict)``."""
    if not (chat_id.startswith("user:") or chat_id.startswith("user_name:")):
        return chat_id, None
    try:
        import aiohttp
    except ImportError:
        return None, {"error": "aiohttp not installed. Run: "
                      f"{install_hint('messaging')}"}
    try:
        from gateway.platforms.base import resolve_proxy_url, proxy_kwargs_for_aiohttp
        _sess_kw, _req_kw = proxy_kwargs_for_aiohttp(resolve_proxy_url())
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30), **_sess_kw) as session:
            async def post_api(method, payload):
                async with session.post(f"https://slack.com/api/{method}", headers=headers, json=payload,
                                        **_req_kw) as resp:
                    return await resp.json()

            if chat_id.startswith("user_name:"):
                name = chat_id[len("user_name:"):]
                query = name.strip().lstrip("@").lower()
                matches, cursor = [], None
                for _page in range(20):
                    data = await post_api("users.list", {"limit": 200, **({"cursor": cursor} if cursor else {})})
                    if not data.get("ok"):
                        return None, _error(f"Slack users.list error: {data.get('error', 'unknown')}")
                    # Stable handle only: display/real names are mutable and non-unique.
                    matches += [m for m in data.get("members", []) if not (m.get("deleted") or m.get("is_bot"))
                                and str(m.get("name", "")).strip().lower() == query]
                    cursor = (data.get("response_metadata") or {}).get("next_cursor")
                    if not cursor:
                        break
                if not matches:
                    return None, _error(f"Could not resolve Slack user '@{name}'.")
                if len(matches) > 1:
                    return None, _error(f"Slack user '@{name}' matched multiple Slack users. Use a Slack user ID instead.")
                chat_id = f"user:{matches[0].get('id')}"
            opened = await post_api("conversations.open", {"users": chat_id[len("user:"):]})
            if not opened.get("ok"):
                return None, _error(f"Slack conversations.open error: {opened.get('error', 'unknown')}. "
                                    "Check bot permissions (im:write).")
            dm_id = (opened.get("channel") or {}).get("id")
            return (dm_id, None) if dm_id else (None, _error("Slack conversations.open did not return a DM channel ID"))
    except Exception as e:
        return None, _error(f"Slack DM resolution failed: {e}")


# "ephemeral connect (may re-init E2EE per send, see #46310)",


