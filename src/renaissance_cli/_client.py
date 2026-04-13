"""Sync HTTP client facade for the Trigger API."""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx

from renaissance_cli._config import get_trigger_api_key, get_trigger_url
from renaissance_cli._output import ExitCode, fail

_client: httpx.Client | None = None


def _get_client() -> httpx.Client:
    global _client
    if _client is None:
        headers: dict[str, str] = {}
        api_key = get_trigger_api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        _client = httpx.Client(base_url=get_trigger_url(), timeout=30.0, headers=headers)
    return _client


def _auth_source_hint() -> tuple[bool, str]:
    """Return (key_present, hint_string) describing where the API key would come from.

    Resolution order matches `_config.get`: env var > config file > default ("").
    The hint names the *first* source that would supply a key, or — if none
    does — the canonical place the user should set one.
    """
    if os.getenv("TRIGGER_API_KEY"):
        return True, "TRIGGER_API_KEY env var"
    config_file = Path.home() / ".config" / "renaissance" / "cli.json"
    if config_file.exists():
        try:
            data = json.loads(config_file.read_text())
            if data.get("trigger_api_key"):
                return True, f"trigger_api_key in {config_file}"
        except (json.JSONDecodeError, OSError):
            pass
    return False, (
        f"set TRIGGER_API_KEY env var, or run "
        f"`ren auth login --url <URL> --key <KEY>` to write it to {config_file}"
    )


def _handle_error(exc: httpx.HTTPStatusError) -> None:
    status = exc.response.status_code
    try:
        detail = exc.response.json().get("detail", str(exc))
    except Exception:
        detail = exc.response.text or str(exc)

    if status == 400:
        fail("BAD_REQUEST", str(detail), exit_code=ExitCode.USAGE_ERROR)
    elif status == 401:
        key_present, hint = _auth_source_hint()
        if key_present:
            fail(
                "AUTH_ERROR",
                f"Server rejected the API key (source: {hint}). "
                "The key is reaching the server but does not match what the server expects.",
                fix="Verify the key against the server's TRIGGER_API_KEY, then "
                    "`ren auth login --url <URL> --key <KEY>` to update local config.",
                exit_code=ExitCode.AUTH_ERROR,
            )
        else:
            fail(
                "AUTH_ERROR",
                f"No API key configured for {get_trigger_url()}. {hint}.",
                fix="ren auth login --url <URL> --key <KEY>",
                exit_code=ExitCode.AUTH_ERROR,
            )
    elif status == 404:
        fail("NOT_FOUND", str(detail), fix="Check the resource ID", exit_code=ExitCode.NOT_FOUND)
    elif status == 409:
        fail("CONFLICT", str(detail), exit_code=ExitCode.CONFLICT)
    else:
        fail("SERVER_ERROR", f"HTTP {status}: {detail}", exit_code=ExitCode.GENERAL_ERROR)


def _connection_error() -> None:
    url = get_trigger_url()
    is_local = "localhost" in url or "127.0.0.1" in url
    if is_local:
        fix = (
            "Trigger appears to be down. Start it with `restart-trigger` "
            "(launchd alias), or override with TRIGGER_URL env var to point "
            "at a remote instance."
        )
    else:
        fix = (
            f"Verify {url} is reachable from this host. If wrong, run "
            "`ren auth login --url <URL> --key <KEY>` or set TRIGGER_URL."
        )
    fail("CONNECTION_ERROR", f"Cannot reach {url}", fix=fix,
         exit_code=ExitCode.CONNECTION_ERROR)


def api_get(path: str, params: dict | None = None, timeout: float = 30.0) -> dict:
    try:
        r = _get_client().get(path, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except httpx.ConnectError:
        _connection_error()
    except httpx.HTTPStatusError as exc:
        _handle_error(exc)
    return {}


def api_post(
    path: str,
    body: dict | None = None,
    timeout: float = 30.0,
    headers: dict[str, str] | None = None,
) -> dict:
    try:
        r = _get_client().post(
            path, json=body or {}, timeout=timeout, headers=headers or None,
        )
        r.raise_for_status()
        return r.json()
    except httpx.ConnectError:
        _connection_error()
    except httpx.HTTPStatusError as exc:
        _handle_error(exc)
    return {}


def api_patch(path: str, body: dict, timeout: float = 30.0) -> dict:
    try:
        r = _get_client().patch(path, json=body, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except httpx.ConnectError:
        _connection_error()
    except httpx.HTTPStatusError as exc:
        _handle_error(exc)
    return {}


def api_delete(path: str, timeout: float = 30.0) -> dict:
    try:
        r = _get_client().delete(path, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except httpx.ConnectError:
        _connection_error()
    except httpx.HTTPStatusError as exc:
        _handle_error(exc)
    return {}
