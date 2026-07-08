"""Cluster helpers for the Agentregistry Workshop MCP client.

Two responsibilities:
  1. Auto-detect the Enterprise Agentgateway LoadBalancer address for the
     workshop's ``agentregistry-gateway`` Gateway.
  2. Render the gateway proxy's access logs so you can watch MCP requests land.

Adapted from solo-field-installer's demo-ui (utils/gateway.py + utils/logs.py),
retargeted to the workshop gateway name and trimmed to the fields MCP traffic
actually emits (status / method / path / duration / request-id).
"""

from __future__ import annotations

import json
import re
import subprocess

import requests
import streamlit as st

NAMESPACE = "agentgateway-system"
GATEWAY_NAME = "agentregistry-gateway"          # the workshop's parent Gateway
PROXY_POD_PREFIX = "agentregistry-gateway"      # proxy Deployment/pods for that Gateway

# RFC3339-ish timestamp emitted by agentgateway, e.g. "2026-06-25T17:54:30.485407Z".
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z?$")


# ---------------------------------------------------------------------------
# kubectl
# ---------------------------------------------------------------------------
def run_kubectl(cmd: str, timeout: int = 30) -> tuple[int, str, str]:
    """Execute a kubectl command, returning (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
        return 1, "", str(exc)


def get_gateway_address(force: bool = False) -> str:
    """Return the gateway LoadBalancer IP/hostname (cached in session state)."""
    if not force and st.session_state.get("_gw_addr_auto"):
        return st.session_state["_gw_addr_auto"]
    rc, out, _ = run_kubectl(
        f"kubectl -n {NAMESPACE} get gateway {GATEWAY_NAME} "
        "-o jsonpath='{.status.addresses[0].value}'"
    )
    addr = out.strip().strip("'")
    if rc == 0 and addr:
        st.session_state["_gw_addr_auto"] = addr
    return addr


# ---------------------------------------------------------------------------
# Endpoint status probe
# ---------------------------------------------------------------------------
# Status values:
#   "live"        – endpoint answered initialize with HTTP 2xx (callable)
#   "missing"     – HTTP 404: gateway is up but no route at this path (not deployed)
#   "error"       – reachable but returned another non-2xx (e.g. upstream down)
#   "unreachable" – connection failed (gateway address wrong / not reachable)
_PROBE_BODY = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2024-11-05", "capabilities": {},
               "clientInfo": {"name": "agentregistry-workshop-client", "version": "1.0"}},
}
_PROBE_HEADERS = {"Content-Type": "application/json",
                  "Accept": "application/json, text/event-stream"}


def probe_endpoint(url: str, timeout: int = 5) -> str:
    """Return the status of an MCP endpoint by attempting initialize (read-only)."""
    try:
        r = requests.post(url, headers=_PROBE_HEADERS, json=_PROBE_BODY,
                          timeout=timeout, verify=False)
    except requests.RequestException:
        return "unreachable"
    if r.status_code == 404:
        return "missing"
    if 200 <= r.status_code < 300:
        return "live"
    return "error"


def endpoint_status(url: str, force: bool = False) -> str:
    """Probe an endpoint, caching the result per-URL in session state."""
    cache = st.session_state.setdefault("_ep_status", {})
    if force or url not in cache:
        cache[url] = probe_endpoint(url)
    return cache[url]


def clear_status_cache() -> None:
    st.session_state["_ep_status"] = {}


STATUS_BADGE = {
    "live": "🟢 live",
    "missing": "⚪ not deployed",
    "error": "🟠 error",
    "unreachable": "🔴 unreachable",
}


# ---------------------------------------------------------------------------
# Log parsing  (JSON lines, with a key=value fallback)
# ---------------------------------------------------------------------------
def _strip_kubectl_prefix(line: str) -> tuple[str, str]:
    """Strip the kubectl --prefix header '[pod/NAME/container] ' from a line."""
    if line.startswith("["):
        end = line.find("] ")
        if end != -1:
            parts = line[1:end].split("/")
            pod = parts[1] if len(parts) >= 2 else line[1:end]
            return pod, line[end + 2:]
    return "", line


def _parse_kv_line(line: str) -> dict | None:
    """Parse 'timestamp level key=val key=val ...' lines; None if not log-shaped."""
    parts = line.split()
    if len(parts) < 3 or not _TIMESTAMP_RE.match(parts[0]):
        return None
    entry: dict = {"time": parts[0], "level": parts[1]}
    found = False
    for tok in parts[2:]:
        if "=" not in tok:
            continue
        key, _, val = tok.partition("=")
        if len(val) >= 2 and val[0] == '"' and val[-1] == '"':
            val = val[1:-1]
        if key in ("http.status", "status") and val.isdigit():
            val = int(val)
        entry[key] = val
        found = True
    return entry if found else None


def _parse_log_lines(raw: str) -> list[dict]:
    """Parse JSON log lines (or kv fallback), skipping non-log content."""
    entries: list[dict] = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        pod, line = _strip_kubectl_prefix(line)
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            entry = _parse_kv_line(line)
        if not isinstance(entry, dict):
            continue
        if pod:
            entry.setdefault("pod", pod)
        entries.append(entry)
    return entries


def _status_icon(status) -> str:
    if isinstance(status, int):
        if 200 <= status < 300:
            return "🟢"
        if status == 429:
            return "🟡"
        if status in (401, 403):
            return "🔴"
        return "🟠"
    return "⚪"


def _render_log_entry(entry: dict) -> None:
    """Render one parsed log entry as a compact card (MCP-relevant fields)."""
    status = entry.get("http.status", entry.get("status", "—"))
    method = entry.get("http.method", "")
    path = entry.get("http.path", "")
    duration = entry.get("duration", "—")
    ts = entry.get("time", "")
    if "T" in ts:
        ts = ts.split("T")[1].split(".")[0]

    if method or path or isinstance(status, int):
        st.markdown(f"{_status_icon(status)} **{status}** `{method} {path}` · {duration}")
    else:
        label = entry.get("message") or entry.get("scope") or ""
        if not label:
            return
        st.markdown(f"{_status_icon(status)} {label}")

    chips = []
    if ts:
        chips.append(f"⏱ {ts}")
    if entry.get("pod"):
        chips.append(f"pod: `{entry['pod']}`")
    req_id = entry.get("x-request-id") or entry.get("request_id")
    if req_id:
        chips.append(f"req-id: `{req_id}`")
    if entry.get("error"):
        chips.append(f"error: {entry['error']}")
    if chips:
        st.caption(" · ".join(chips))

    with st.expander("Details"):
        st.json(entry)
    st.markdown("---")


def _get_proxy_pods() -> list[str]:
    """Names of gateway proxy pods (all replicas of agentregistry-gateway)."""
    rc, out, _ = run_kubectl(f"kubectl get pods -n {NAMESPACE} -o name")
    if rc != 0:
        return []
    return [
        ln.removeprefix("pod/")
        for ln in out.strip().splitlines()
        if ln.removeprefix("pod/").startswith(PROXY_POD_PREFIX)
    ]


def show_gateway_logs(step_key: str, tail: int = 10) -> None:
    """Render an expander with the gateway proxy's recent logs.

    Logs are fetched fresh each render so they reflect current cluster state.
    Uses a pod-name prefix so all replicas are included.
    """
    with st.expander("View Gateway Logs", expanded=False):
        _, btn = st.columns([5, 1])
        with btn:
            if st.button("Refresh", key=f"_logs_refresh_{step_key}"):
                st.rerun()

        pods = _get_proxy_pods()
        if not pods:
            st.caption(
                f"No `{PROXY_POD_PREFIX}` pods found in `{NAMESPACE}`. "
                "Is the parent Gateway deployed and kubectl pointed at the cluster?"
            )
            return

        fetch_per_pod = max(50, tail * 10)
        combined, rc = "", 0
        for pod in pods:
            _rc, _out, _ = run_kubectl(
                f"kubectl logs -n {NAMESPACE} {pod} --tail {fetch_per_pod} --prefix"
            )
            if _rc != 0:
                rc = _rc
            combined += _out

        if rc != 0 and not combined.strip():
            st.error("Failed to fetch logs (is kubectl configured for this cluster?)")
            return

        entries = _parse_log_lines(combined)
        if not entries:
            st.caption("No structured log entries yet — send a request, then Refresh.")
            if combined.strip():
                with st.expander("Raw"):
                    st.code(combined, language="text")
            return

        entries.sort(key=lambda e: e.get("time", ""))
        for entry in reversed(entries[-tail:]):
            _render_log_entry(entry)
