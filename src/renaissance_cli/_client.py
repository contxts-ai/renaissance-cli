"""Sync HTTP client facade for the Trigger API."""

from __future__ import annotations

import os

import httpx

from renaissance_cli._output import ExitCode, fail

_client: httpx.Client | None = None


def _get_url() -> str:
    return os.getenv("TRIGGER_URL", "http://localhost:58100")


def _get_client() -> httpx.Client:
    global _client
    if _client is None:
        headers: dict[str, str] = {}
        api_key = os.getenv("TRIGGER_API_KEY", "")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        _client = httpx.Client(base_url=_get_url(), timeout=30.0, headers=headers)
    return _client


def _handle_error(exc: httpx.HTTPStatusError) -> None:
    status = exc.response.status_code
    try:
        detail = exc.response.json().get("detail", str(exc))
    except Exception:
        detail = exc.response.text or str(exc)

    if status == 400:
        fail("BAD_REQUEST", str(detail), exit_code=ExitCode.USAGE_ERROR)
    elif status == 401:
        fail("AUTH_ERROR", "Authentication failed", fix="Set TRIGGER_API_KEY env var", exit_code=ExitCode.AUTH_ERROR)
    elif status == 404:
        fail("NOT_FOUND", str(detail), fix="Check the resource ID", exit_code=ExitCode.NOT_FOUND)
    elif status == 409:
        fail("CONFLICT", str(detail), exit_code=ExitCode.CONFLICT)
    else:
        fail("SERVER_ERROR", f"HTTP {status}: {detail}", exit_code=ExitCode.GENERAL_ERROR)


def api_get(path: str, params: dict | None = None, timeout: float = 30.0) -> dict:
    try:
        r = _get_client().get(path, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except httpx.ConnectError:
        url = _get_url()
        fail("CONNECTION_ERROR", f"Cannot reach {url}",
             fix=f"Check TRIGGER_URL env var (current: {url})",
             exit_code=ExitCode.CONNECTION_ERROR)
    except httpx.HTTPStatusError as exc:
        _handle_error(exc)
    return {}  # unreachable, satisfies type checker


def api_post(path: str, body: dict | None = None, timeout: float = 30.0) -> dict:
    try:
        r = _get_client().post(path, json=body or {}, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except httpx.ConnectError:
        url = _get_url()
        fail("CONNECTION_ERROR", f"Cannot reach {url}",
             fix=f"Check TRIGGER_URL env var (current: {url})",
             exit_code=ExitCode.CONNECTION_ERROR)
    except httpx.HTTPStatusError as exc:
        _handle_error(exc)
    return {}


def api_patch(path: str, body: dict, timeout: float = 30.0) -> dict:
    try:
        r = _get_client().patch(path, json=body, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except httpx.ConnectError:
        url = _get_url()
        fail("CONNECTION_ERROR", f"Cannot reach {url}",
             fix=f"Check TRIGGER_URL env var (current: {url})",
             exit_code=ExitCode.CONNECTION_ERROR)
    except httpx.HTTPStatusError as exc:
        _handle_error(exc)
    return {}


def api_delete(path: str, timeout: float = 30.0) -> dict:
    try:
        r = _get_client().delete(path, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except httpx.ConnectError:
        url = _get_url()
        fail("CONNECTION_ERROR", f"Cannot reach {url}",
             fix=f"Check TRIGGER_URL env var (current: {url})",
             exit_code=ExitCode.CONNECTION_ERROR)
    except httpx.HTTPStatusError as exc:
        _handle_error(exc)
    return {}
