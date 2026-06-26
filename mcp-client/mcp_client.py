"""Embedded MCP client for Streamlit demo UI.

Provides a reusable widget that connects to any MCP server over Streamable HTTP,
lists tools, renders parameter inputs from JSON Schema, calls tools, and shows
call history.  All state is namespaced via a caller-supplied *key_prefix* so
multiple instances can coexist on the same page.
"""

from __future__ import annotations

import json
import time
from typing import Any

import requests
import streamlit as st

# ---------------------------------------------------------------------------
# 1. Protocol helpers — low-level JSON-RPC over MCP Streamable HTTP
# ---------------------------------------------------------------------------

_MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}

# Monotonically increasing request id per session.
_REQ_ID_KEY = "__mcp_client_req_id"


def _next_id() -> int:
    """Return a session-unique JSON-RPC request id."""
    val = st.session_state.get(_REQ_ID_KEY, 0) + 1
    st.session_state[_REQ_ID_KEY] = val
    return val


def _parse_sse_body(text: str) -> dict | None:
    """Extract the first JSON-RPC result from an SSE response body.

    MCP servers may respond with ``text/event-stream`` instead of plain JSON.
    Each SSE event is formatted as ``data: <json>\\n\\n``.  We parse all data
    lines and return the first one that is valid JSON.
    """
    for line in text.splitlines():
        if line.startswith("data:"):
            payload = line[len("data:"):].strip()
            if not payload:
                continue
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                continue
    return None


def _looks_like_stale_session_error(status_code: int, body_text: str) -> bool:
    """Detect the upstream's 'No valid session ID provided' response.

    Some MCP servers (notably the official ``mcp-server-everything``) reject
    any non-initialize request whose Mcp-Session-Id header doesn't match a
    live server-side session with HTTP 400 + JSON-RPC error code -32000.
    The gateway in Stateless mode forwards this verbatim. When we see it,
    the only recovery is to drop the stale session id and retry.
    """
    if status_code != 400:
        return False
    if "-32000" not in body_text:
        return False
    return "session" in body_text.lower()


def _jsonrpc_request(
    url: str,
    method: str,
    params: dict | None = None,
    *,
    session_id: str | None = None,
    extra_headers: dict | None = None,
    is_notification: bool = False,
    timeout: int = 30,
    _retry_without_session: bool = True,
) -> dict:
    """Send a JSON-RPC request to an MCP server over Streamable HTTP.

    Returns a dict with keys:
        ok                 – True when the call succeeded
        status_code        – HTTP status code (0 on connection error)
        result             – parsed JSON-RPC result (or None)
        error              – error description string (or None)
        session_id         – Mcp-Session-Id returned by the server (if any)
        headers            – response headers dict
        elapsed_ms         – round-trip time in milliseconds
        raw                – raw response text
        session_invalidated – True if a stale session id was dropped and the
                              request was retried; callers should clear their
                              cached session_id state.
    """
    # Defense-in-depth: never let a caller smuggle Mcp-Session-Id in via
    # extra_headers. Sessions belong to the dedicated session_id parameter
    # so stale values can't sneak in from the custom-headers UI.
    if extra_headers:
        extra_headers = {k: v for k, v in extra_headers.items()
                         if k.lower() != "mcp-session-id"}

    headers: dict[str, str] = {**_MCP_HEADERS}
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    if extra_headers:
        headers.update(extra_headers)

    body: dict[str, Any] = {
        "jsonrpc": "2.0",
        "method": method,
    }
    if params is not None:
        body["params"] = params
    if not is_notification:
        body["id"] = _next_id()

    start = time.time()
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=timeout, verify=False)
    except Exception as exc:
        elapsed = int((time.time() - start) * 1000)
        return {
            "ok": False,
            "status_code": 0,
            "result": None,
            "error": str(exc),
            "session_id": session_id,
            "headers": {},
            "elapsed_ms": elapsed,
            "raw": "",
        }
    elapsed = int((time.time() - start) * 1000)

    new_session = resp.headers.get("Mcp-Session-Id") or session_id

    # For notifications the server may return 200/202 with no body.
    if is_notification:
        return {
            "ok": 200 <= resp.status_code < 300,
            "status_code": resp.status_code,
            "result": None,
            "error": None if 200 <= resp.status_code < 300 else resp.text,
            "session_id": new_session,
            "headers": dict(resp.headers),
            "elapsed_ms": elapsed,
            "raw": resp.text,
        }

    # Try plain JSON first, then SSE.
    parsed: dict | None = None
    try:
        parsed = resp.json()
    except (json.JSONDecodeError, ValueError):
        parsed = _parse_sse_body(resp.text)

    if parsed is None and 200 <= resp.status_code < 300:
        return {
            "ok": False,
            "status_code": resp.status_code,
            "result": None,
            "error": f"Could not parse response: {resp.text[:500]}",
            "session_id": new_session,
            "headers": dict(resp.headers),
            "elapsed_ms": elapsed,
            "raw": resp.text,
        }

    if not (200 <= resp.status_code < 300):
        # Auto-recover from a stale-session-id rejection. If we sent a
        # session header and the upstream rejected it as invalid, drop the
        # header and try once more. Callers see the retry's response and a
        # session_invalidated flag so they can clear their cached id.
        if (
            _retry_without_session
            and session_id
            and _looks_like_stale_session_error(resp.status_code, resp.text)
        ):
            retry = _jsonrpc_request(
                url,
                method,
                params,
                session_id=None,
                extra_headers=extra_headers,
                is_notification=is_notification,
                timeout=timeout,
                _retry_without_session=False,
            )
            retry["session_invalidated"] = True
            return retry
        return {
            "ok": False,
            "status_code": resp.status_code,
            "result": parsed,
            "error": resp.text[:500],
            "session_id": new_session,
            "headers": dict(resp.headers),
            "elapsed_ms": elapsed,
            "raw": resp.text,
        }

    # JSON-RPC level error
    if parsed and "error" in parsed:
        err = parsed["error"]
        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        return {
            "ok": False,
            "status_code": resp.status_code,
            "result": parsed,
            "error": f"MCP error: {msg}",
            "session_id": new_session,
            "headers": dict(resp.headers),
            "elapsed_ms": elapsed,
            "raw": resp.text,
        }

    return {
        "ok": True,
        "status_code": resp.status_code,
        "result": parsed.get("result") if parsed else None,
        "error": None,
        "session_id": new_session,
        "headers": dict(resp.headers),
        "elapsed_ms": elapsed,
        "raw": resp.text,
    }


def mcp_initialize(
    url: str,
    *,
    extra_headers: dict | None = None,
    timeout: int = 30,
) -> dict:
    """Two-step MCP handshake: ``initialize`` then ``notifications/initialized``.

    Returns the result dict from :func:`_jsonrpc_request` for the initialize call
    (with ``session_id`` already set from the server response).  The notification
    is fire-and-forget.
    """
    res = _jsonrpc_request(
        url,
        "initialize",
        params={
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "agentregistry-workshop-client", "version": "1.0"},
        },
        extra_headers=extra_headers,
        timeout=timeout,
    )
    if res["ok"] and res["session_id"]:
        # Fire-and-forget initialized notification.  Skipped when the server
        # doesn't return a Mcp-Session-Id (some servers use connection-scoped
        # sessions instead), which can leave those servers partially initialized.
        _jsonrpc_request(
            url,
            "notifications/initialized",
            is_notification=True,
            session_id=res["session_id"],
            extra_headers=extra_headers,
            timeout=timeout,
        )
    return res


def mcp_list_tools(
    url: str,
    *,
    session_id: str | None = None,
    extra_headers: dict | None = None,
    timeout: int = 30,
) -> dict:
    """Call ``tools/list`` and return the result dict."""
    return _jsonrpc_request(
        url,
        "tools/list",
        session_id=session_id,
        extra_headers=extra_headers,
        timeout=timeout,
    )


def mcp_call_tool(
    url: str,
    tool_name: str,
    arguments: dict,
    *,
    session_id: str | None = None,
    extra_headers: dict | None = None,
    timeout: int = 60,
) -> dict:
    """Call ``tools/call`` for *tool_name* with *arguments*."""
    return _jsonrpc_request(
        url,
        "tools/call",
        params={"name": tool_name, "arguments": arguments},
        session_id=session_id,
        extra_headers=extra_headers,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# 2. Custom headers UI
# ---------------------------------------------------------------------------

def _render_custom_headers(prefix: str) -> dict[str, str]:
    """Render an expander for managing arbitrary HTTP headers.

    Each header has an enabled/disabled checkbox so it can be toggled
    without removing it — useful for demoing 401/403 vs 200 flows.

    Returns a merged dict of enabled headers only.
    """
    hdr_key = f"{prefix}_custom_headers"
    if hdr_key not in st.session_state:
        st.session_state[hdr_key] = []  # list of {"name": ..., "value": ..., "enabled": bool}

    headers_list: list[dict] = st.session_state[hdr_key]

    # Backfill "enabled" for headers seeded before toggle existed.
    for h in headers_list:
        h.setdefault("enabled", True)

    enabled_count = sum(1 for h in headers_list if h.get("enabled"))
    total_count = len(headers_list)
    badge = f"{enabled_count}/{total_count}" if total_count else "0"

    with st.expander(f"Custom HTTP Headers ({badge})", expanded=bool(headers_list)):
        st.caption("Add headers sent with every MCP request. Uncheck to disable without removing.")

        # Render existing rows
        to_remove: int | None = None
        for idx, entry in enumerate(headers_list):
            cols = st.columns([0.5, 2.5, 5, 1])
            with cols[0]:
                enabled = st.checkbox(
                    "on",
                    value=entry.get("enabled", True),
                    key=f"{prefix}_hdr_on_{idx}",
                    label_visibility="collapsed",
                )
                entry["enabled"] = enabled
            with cols[1]:
                new_name = st.text_input(
                    "Header",
                    value=entry["name"],
                    key=f"{prefix}_hdr_name_{idx}",
                    label_visibility="collapsed",
                    placeholder="Header name",
                    disabled=not enabled,
                )
            with cols[2]:
                new_value = st.text_input(
                    "Value",
                    value=entry["value"],
                    key=f"{prefix}_hdr_val_{idx}",
                    label_visibility="collapsed",
                    placeholder="Header value",
                    disabled=not enabled,
                )
            with cols[3]:
                if st.button(
                    ":material/delete:",
                    key=f"{prefix}_hdr_del_{idx}",
                    help="Remove header",
                ):
                    to_remove = idx
            # Sync edits back.
            entry["name"] = new_name
            entry["value"] = new_value

        if to_remove is not None:
            headers_list.pop(to_remove)
            st.rerun()

        if st.button("Add header", key=f"{prefix}_hdr_add"):
            headers_list.append({"name": "", "value": "", "enabled": True})
            st.rerun()

    # Build merged dict — only enabled headers with non-empty names.
    return {
        h["name"]: h["value"]
        for h in headers_list
        if h["name"].strip() and h.get("enabled", True)
    }


# ---------------------------------------------------------------------------
# 3. Parameter rendering from JSON Schema
# ---------------------------------------------------------------------------

def _render_tool_params(
    prefix: str,
    tool: dict,
    hints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Render Streamlit widgets for a tool's ``inputSchema`` and collect values.

    *hints* is an optional dict of ``{param_name: default_value}`` used to
    pre-fill the inputs on first render.

    Returns the collected arguments dict.
    """
    tool_name = tool.get("name", "")
    schema: dict = tool.get("inputSchema") or {}
    properties: dict = schema.get("properties", {})
    required_set: set[str] = set(schema.get("required", []))
    hints = hints or {}

    if not properties:
        st.caption("This tool takes no parameters.")
        return {}

    args: dict[str, Any] = {}
    for name, prop in properties.items():
        prop_type = prop.get("type", "string")
        description = prop.get("description", "")
        label = f"{name} *" if name in required_set else name
        if description:
            label = f"{label}  —  {description}"
        widget_key = f"{prefix}_{tool_name}_param_{name}"
        default = hints.get(name)

        if prop_type == "boolean":
            val = st.checkbox(
                label,
                value=bool(default) if default is not None else False,
                key=widget_key,
            )
            args[name] = val

        elif prop_type == "integer":
            val = st.number_input(
                label,
                value=int(default) if default is not None else 0,
                step=1,
                key=widget_key,
            )
            args[name] = int(val)

        elif prop_type == "number":
            val = st.number_input(
                label,
                value=float(default) if default is not None else 0.0,
                step=0.1,
                format="%.2f",
                key=widget_key,
            )
            args[name] = float(val)

        elif prop_type in ("object", "array"):
            default_text = ""
            if default is not None:
                default_text = json.dumps(default, indent=2) if not isinstance(default, str) else default
            raw = st.text_area(
                label,
                value=default_text,
                key=widget_key,
                help="Enter valid JSON.",
            )
            if raw.strip():
                try:
                    args[name] = json.loads(raw)
                except json.JSONDecodeError:
                    st.warning(f"Invalid JSON for **{name}** — will be sent as-is.")
                    args[name] = raw
            # Omit empty optional object/array params.

        else:
            # Default: string
            val = st.text_input(
                label,
                value=str(default) if default is not None else "",
                key=widget_key,
            )
            if val or name in required_set:
                args[name] = val

    return args


# ---------------------------------------------------------------------------
# 4. Call history
# ---------------------------------------------------------------------------

def _render_call_history(prefix: str) -> None:
    """Render expandable rows of past tool calls."""
    history_key = f"{prefix}_call_history"
    history: list[dict] = st.session_state.get(history_key, [])

    if not history:
        return

    st.markdown("---")
    st.markdown("**Call History**")

    if st.button("Clear History", key=f"{prefix}_clear_history"):
        st.session_state[history_key] = []
        st.rerun()

    for idx, entry in enumerate(reversed(history)):
        # Build compact summary line.
        tool_name = entry.get("tool", "?")
        status = entry.get("status_code", "?")
        elapsed = entry.get("elapsed_ms", "?")
        args_summary = _args_summary(entry.get("arguments", {}))
        label = f"`{tool_name}` — HTTP {status} — {elapsed}ms"
        if args_summary:
            label += f"  ({args_summary})"

        with st.expander(label, expanded=(idx == 0)):
            # Request details
            req_headers = entry.get("request_headers")
            if req_headers:
                st.markdown("**Request Headers**")
                for k, v in req_headers.items():
                    st.caption(f"{k}: {v}")

            st.markdown("**Arguments**")
            st.json(entry.get("arguments", {}))

            # Response details
            resp_headers = entry.get("response_headers", {})
            if resp_headers:
                # Highlight notable headers.
                notable = ["x-opa-decision", "x-validated-by", "mcp-session-id"]
                notable_lower = {h.lower() for h in notable}
                matched = {k: v for k, v in resp_headers.items() if k.lower() in notable_lower}
                if matched:
                    st.markdown("**Notable Response Headers**")
                    for k, v in matched.items():
                        st.success(f"**{k}:** `{v}`")
                with st.expander("All Response Headers"):
                    for k, v in resp_headers.items():
                        st.caption(f"{k}: {v}")

            st.markdown("**Response Body**")
            raw = entry.get("raw", "")
            try:
                st.json(json.loads(raw))
            except (json.JSONDecodeError, TypeError):
                st.code(raw or "(empty)")


def _args_summary(args: dict, max_len: int = 60) -> str:
    """Create a short one-line summary of call arguments."""
    if not args:
        return ""
    parts: list[str] = []
    for k, v in args.items():
        s = f"{k}={v!r}"
        parts.append(s)
    combined = ", ".join(parts)
    if len(combined) > max_len:
        combined = combined[:max_len] + "..."
    return combined


def _record_call(
    prefix: str,
    tool_name: str,
    arguments: dict,
    request_headers: dict,
    result: dict,
) -> None:
    """Append a call to the history list in session state."""
    history_key = f"{prefix}_call_history"
    if history_key not in st.session_state:
        st.session_state[history_key] = []
    st.session_state[history_key].append({
        "tool": tool_name,
        "arguments": arguments,
        "status_code": result.get("status_code", 0),
        "elapsed_ms": result.get("elapsed_ms", 0),
        "request_headers": request_headers,
        "response_headers": result.get("headers", {}),
        "raw": result.get("raw", ""),
        "error": result.get("error"),
    })


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _render_error(res: dict) -> None:
    """Display an error result with status code and response headers."""
    status = res.get("status_code", 0)
    error = res.get("error", "Unknown error")

    if status == 0:
        st.error(f"Connection failed: {error}")
    elif status == 401:
        st.error(f"HTTP {status} — Unauthorized")
    elif status == 403:
        st.error(f"HTTP {status} — Forbidden")
    else:
        st.error(f"HTTP {status} — {error}")

    # Show response headers for auth failures — they often contain useful info.
    resp_headers = res.get("headers", {})
    if resp_headers and status in (401, 403, 0):
        with st.expander("Response Headers"):
            for k, v in resp_headers.items():
                st.caption(f"{k}: {v}")
    elif resp_headers and not res.get("ok"):
        notable = ["x-opa-decision", "x-validated-by", "www-authenticate"]
        notable_lower = {h.lower() for h in notable}
        matched = {k: v for k, v in resp_headers.items() if k.lower() in notable_lower}
        if matched:
            for k, v in matched.items():
                st.warning(f"**{k}:** `{v}`")


def _render_result(res: dict) -> None:
    """Render the latest tool call result with a polished layout."""
    status = res.get("status_code", 0)
    elapsed = res.get("elapsed_ms", 0)
    tool_name = ""

    # Pull tool name from the most recent history entry if available.
    # (The result dict itself doesn't carry it, but the caller always
    # records history before storing last_result.)

    if not res["ok"]:
        _render_error(res)
        return

    # ---- status bar --------------------------------------------------------
    cols = st.columns([3, 1])
    with cols[0]:
        st.success(f"**{status}** OK")
    with cols[1]:
        st.caption(f"{elapsed} ms")

    # ---- content -----------------------------------------------------------
    result_data = res.get("result")
    if result_data is None:
        return

    content_items = result_data.get("content", []) if isinstance(result_data, dict) else []

    if not content_items:
        # No content array — show raw result
        st.json(result_data)
        return

    for item in content_items:
        item_type = item.get("type", "text")
        text = item.get("text", "")

        if item_type == "text" and text:
            # Try to detect and pretty-print JSON text
            stripped = text.strip()
            if stripped.startswith(("{", "[")):
                try:
                    parsed = json.loads(stripped)
                    st.json(parsed)
                    continue
                except json.JSONDecodeError:
                    pass
            # Plain text — render in a code block for readability
            st.code(text, language="text")

        elif item_type == "image":
            # MCP image content: {"type": "image", "data": "base64...", "mimeType": "image/png"}
            mime = item.get("mimeType", "image/png")
            data = item.get("data", "")
            if data:
                import base64
                st.image(base64.b64decode(data), caption=mime)

        elif item_type == "resource":
            # Embedded resource
            resource = item.get("resource", {})
            uri = resource.get("uri", "")
            r_text = resource.get("text", "")
            if uri:
                st.caption(f"Resource: `{uri}`")
            if r_text:
                st.code(r_text, language="text")

        else:
            # Unknown content type — show as JSON
            st.json(item)


# ---------------------------------------------------------------------------
# 5. Main public function
# ---------------------------------------------------------------------------

def render_mcp_client(
    server_url: str,
    key_prefix: str = "mcp",
    hints: dict | None = None,
    default_headers: list[dict[str, str]] | None = None,
    system_headers: dict[str, str] | None = None,
) -> None:
    """Render the full embedded MCP client widget.

    Parameters
    ----------
    server_url:
        Base URL of the MCP server (e.g. ``http://10.0.0.1:8080/mcp``).
    key_prefix:
        Unique prefix for all ``st.session_state`` keys so multiple
        instances can coexist.
    hints:
        Optional dict with ``tool`` (str) to pre-select in the tool
        dropdown and ``params`` (dict) to pre-fill parameter values.
        Example: ``{"tool": "search", "params": {"query": "JWT"}}``.
    default_headers:
        Optional list of ``{"name": ..., "value": ...}`` dicts to seed
        the custom headers on first render.
    system_headers:
        Dict of headers always sent with every request. Not shown in the
        custom-headers UI. Used for infrastructure headers like X-Tenant-ID.
    """
    hint_tool: str = (hints or {}).get("tool", "")
    hint_params: dict = (hints or {}).get("params", {})
    prefix = key_prefix

    # ---- state keys ---------------------------------------------------------
    connected_key = f"{prefix}_connected"
    session_key = f"{prefix}_session_id"
    server_info_key = f"{prefix}_server_info"
    tools_key = f"{prefix}_tools"
    selected_key = f"{prefix}_selected_tool"
    last_result_key = f"{prefix}_last_result"

    # ---- custom headers -----------------------------------------------------
    # Seed defaults on first render only (key doesn't exist yet).
    hdr_key = f"{prefix}_custom_headers"
    if default_headers and hdr_key not in st.session_state:
        st.session_state[hdr_key] = [dict(h) for h in default_headers]
    # system_headers are merged last so they can't be accidentally removed via UI.
    extra_headers = {**(system_headers or {}), **_render_custom_headers(prefix)}

    # ---- connection controls ------------------------------------------------
    st.markdown("---")
    st.markdown("**Initialize MCP session**")
    st.caption(
        "Open an MCP session against the gateway route. Connect runs `initialize` "
        "and fetches `tools/list`; Disconnect closes the session and clears the catalog."
    )
    is_connected = st.session_state.get(connected_key, False)

    col_connect, col_disconnect = st.columns(2)
    with col_connect:
        connect_clicked = st.button(
            "Connect",
            key=f"{prefix}_btn_connect",
            disabled=is_connected,
            use_container_width=True,
        )
    with col_disconnect:
        disconnect_clicked = st.button(
            "Disconnect",
            key=f"{prefix}_btn_disconnect",
            disabled=not is_connected,
            use_container_width=True,
        )

    # ---- handle connect -----------------------------------------------------
    if connect_clicked:
        with st.spinner("Connecting to MCP server..."):
            init_res = mcp_initialize(server_url, extra_headers=extra_headers)

        if not init_res["ok"]:
            _render_error(init_res)
            return

        session_id = init_res["session_id"]

        # Immediately list tools.
        with st.spinner("Listing tools..."):
            tools_res = mcp_list_tools(
                server_url,
                session_id=session_id,
                extra_headers=extra_headers,
            )

        if not tools_res["ok"]:
            _render_error(tools_res)
            return

        # Persist connection state.
        st.session_state[connected_key] = True
        st.session_state[session_key] = session_id
        st.session_state[server_info_key] = init_res["result"]
        tools_list = (tools_res["result"] or {}).get("tools", [])
        st.session_state[tools_key] = tools_list
        st.session_state.pop(selected_key, None)
        st.session_state.pop(last_result_key, None)
        st.rerun()

    # ---- handle disconnect --------------------------------------------------
    if disconnect_clicked:
        for k in [connected_key, session_key, server_info_key, tools_key,
                   selected_key, last_result_key]:
            st.session_state.pop(k, None)
        st.rerun()

    # ---- not connected — stop here ------------------------------------------
    if not is_connected:
        st.info("Click **Connect** to initialize the MCP session.")
        return

    # ---- server info --------------------------------------------------------
    server_info: dict | None = st.session_state.get(server_info_key)
    if server_info:
        srv_name = server_info.get("serverInfo", {}).get("name", "Unknown")
        srv_version = server_info.get("serverInfo", {}).get("version", "")
        proto_ver = server_info.get("protocolVersion", "")
        st.success(f"Connected to **{srv_name}** {srv_version}  (protocol {proto_ver})")

    # ---- tool selector ------------------------------------------------------
    tools_list: list[dict] = st.session_state.get(tools_key, [])
    if not tools_list:
        st.warning("Server reported no tools.")
        _render_call_history(prefix)
        return

    tool_names = [t["name"] for t in tools_list]
    default_idx = tool_names.index(hint_tool) if hint_tool in tool_names else 0
    selected_name = st.selectbox(
        "Tool",
        tool_names,
        index=default_idx,
        key=selected_key,
    )

    # Find tool definition.
    tool_def: dict = next(t for t in tools_list if t["name"] == selected_name)

    # Show tool description if available.
    desc = tool_def.get("description", "")
    if desc:
        st.caption(desc)

    # ---- parameter inputs ---------------------------------------------------
    active_hints = hint_params if selected_name == hint_tool else {}
    args = _render_tool_params(prefix, tool_def, active_hints)

    # ---- call tool ----------------------------------------------------------
    if st.button("Call Tool", key=f"{prefix}_btn_call", type="primary"):
        session_id = st.session_state.get(session_key)
        with st.spinner(f"Calling `{selected_name}`..."):
            call_res = mcp_call_tool(
                server_url,
                selected_name,
                args,
                session_id=session_id,
                extra_headers=extra_headers,
            )

        # If the helper auto-retried after a stale-session rejection, drop the
        # cached id so subsequent calls don't keep hitting the same wall, and
        # surface a one-time toast so the user knows recovery happened.
        if call_res.get("session_invalidated"):
            st.session_state[session_key] = None
            st.toast(
                "Stale MCP session dropped — retried without it.",
                icon=":material/autorenew:",
            )

        # Merge request headers for history.
        req_headers: dict[str, str] = {**_MCP_HEADERS}
        if session_id:
            req_headers["Mcp-Session-Id"] = session_id
        req_headers.update(extra_headers)

        _record_call(prefix, selected_name, args, req_headers, call_res)
        st.session_state[last_result_key] = call_res
        st.rerun()

    # ---- latest result ------------------------------------------------------
    last = st.session_state.get(last_result_key)
    if last:
        st.markdown("---")
        _render_result(last)

    # ---- call history -------------------------------------------------------
    _render_call_history(prefix)
