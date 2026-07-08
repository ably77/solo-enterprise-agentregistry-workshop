"""Agentregistry Workshop — local MCP client.

A small Streamlit app to make MCP requests to the gateway-fronted MCP servers
catalogued in the workshop. Pick an endpoint, Connect (runs the MCP handshake),
choose a tool from the dropdown, fill the (pre-filled) parameters, Call it, and
watch the gateway logs.

Run:  ./run.sh   →   http://localhost:8501
"""

import streamlit as st

from cluster import (
    STATUS_BADGE,
    clear_status_cache,
    endpoint_status,
    get_gateway_address,
    show_gateway_logs,
)
from mcp_client import render_mcp_client

st.set_page_config(page_title="Agentregistry MCP Client", page_icon=":material/hub:", layout="wide")

# Hide Streamlit's default top-right toolbar (Deploy button + ⋮ main menu).
st.markdown(
    """
    <style>
      [data-testid="stToolbar"], [data-testid="stMainMenu"],
      [data-testid="stToolbarActions"], .stDeployButton { display: none !important; }
      #MainMenu { visibility: hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Curated workshop endpoints (path + a working example to pre-fill) -------
# Each entry maps to an MCP server deployed to the virtual-default runtime and
# exposed under the parent route's /registry prefix.
ENDPOINTS = {
    "Solo Docs (remote)": {
        "slug": "solo-docs",
        "path": "/registry/solo-docs",
        "hint": {"tool": "search", "params": {
            "query": "MCP authentication",
            "product": "solo-enterprise-for-agentgateway",
            "limit": 2,
        }},
        "note": "Public Solo.io documentation search (search.solo.io). Tools: search, get_chunks, get_full_page.",
        "lab": "labs/mcp/solo-docs-mcp.md",
    },
    "DeepWiki (remote)": {
        "slug": "deepwiki",
        "path": "/registry/deepwiki",
        "hint": {"tool": "ask_question", "params": {
            "repoName": "solo-io/gloo",
            "question": "What is this project?",
        }},
        "note": "Q&A over public GitHub repos (mcp.deepwiki.com). Tools: read_wiki_structure, read_wiki_contents, ask_question.",
        "lab": "labs/mcp/deepwiki-mcp.md",
    },
    "arXiv (in-cluster)": {
        "slug": "arxiv",
        "path": "/registry/arxiv",
        "hint": {"tool": "search_arxiv", "params": {
            "keyword": "retrieval augmented generation",
            "max_results": 3,
        }},
        "note": "Self-hosted arXiv MCP, registered by in-cluster Service URL. Tools: search_arxiv, get_paper, …",
        "lab": "labs/mcp/in-cluster-mcp.md",
    },
    "FRED (in-cluster, credentialed)": {
        "slug": "fred",
        "path": "/registry/fred",
        "hint": {"tool": "fred_get_series", "params": {
            "series_id": "GDP",
            "observation_start": "2024-01-01",
            "observation_end": "2024-12-31",
        }},
        "note": "Federal Reserve data MCP; its API key lives in a k8s Secret, not the catalog. Tools: fred_browse, fred_search, fred_get_series.",
        "lab": "labs/mcp/fred-mcp.md",
    },
    "Custom path…": {
        "slug": "custom",
        "path": "/registry/",
        "hint": None,
        "note": "Enter any path served by the gateway.",
        "lab": None,
    },
}


# --- Sidebar: gateway address (auto-detected, overridable) -------------------
with st.sidebar:
    st.header("Gateway")
    detected = get_gateway_address()
    if detected:
        st.success(f"Detected: `{detected}`")
    else:
        st.warning("Could not auto-detect the gateway address.\nEnter it manually below.")
    if st.button("Re-detect", use_container_width=True):
        get_gateway_address(force=True)
        st.rerun()

    address = st.text_input(
        "Gateway address (IP or hostname)",
        value=detected,
        help="The agentregistry-gateway LoadBalancer address. Override if auto-detect is wrong.",
    )
    scheme = st.selectbox("Scheme", ["http", "https"], index=0)
    port = st.text_input("Port (blank = default)", value="", help="Listener is HTTP/80 by default — leave blank.")
    st.caption("MCP servers are exposed at `<scheme>://<address>[:port]/registry/<name>`.")
    if st.button("Re-check endpoints", use_container_width=True,
                 help="Re-probe each endpoint's live/not-deployed status."):
        clear_status_cache()
        st.rerun()


def _make_url(scheme: str, host: str, path: str) -> str:
    return f"{scheme}://{host}{path}"


# --- Main ---------------------------------------------------------------------
st.title("Agentregistry Workshop — MCP Client")
st.caption(
    "Make live MCP requests to the gateway-fronted servers from the workshop. "
    "Connect runs the handshake; pick a tool, fill the example parameters, and Call."
)

if not address:
    st.info("Set the gateway address in the sidebar to continue.")
    st.stop()

host = f"{address}:{port}" if port.strip() else address

# Probe each known endpoint (cached per URL) so the picker can show live status.
def _endpoint_label(label: str) -> str:
    cfg = ENDPOINTS[label]
    if cfg["slug"] == "custom":
        return label
    status = endpoint_status(_make_url(scheme, host, cfg["path"]))
    return f"{STATUS_BADGE.get(status, status)}  ·  {label}"

label = st.selectbox("Endpoint", list(ENDPOINTS.keys()), format_func=_endpoint_label)
cfg = ENDPOINTS[label]
st.caption(cfg["note"])

path = cfg["path"]
if cfg["slug"] == "custom":
    path = st.text_input("Path", value="/registry/")

if not path or not path.startswith("/"):
    st.warning("Enter a path beginning with `/` (e.g. `/registry/solo-docs`).")
    st.stop()

server_url = _make_url(scheme, host, path)
st.code(server_url, language="text")

# Live status for the selected endpoint + a hint to the lab that deploys it.
status = endpoint_status(server_url)
if status == "live":
    st.caption(f"Status: {STATUS_BADGE['live']} — ready to Connect.")
elif status == "missing":
    msg = f"Status: {STATUS_BADGE['missing']} — no route at `{path}` on the gateway."
    if cfg.get("lab"):
        msg += f" Deploy it first — see `{cfg['lab']}`."
    st.warning(msg)
elif status == "unreachable":
    st.error(
        f"Status: {STATUS_BADGE['unreachable']} — can't reach `{host}`. "
        "Check the gateway address in the sidebar and that the LB is reachable from here."
    )
else:
    st.warning(f"Status: {STATUS_BADGE.get(status, status)} — endpoint reachable but returned an error; check the upstream MCP server.")

# Per-endpoint key_prefix keeps each endpoint's session + history independent.
render_mcp_client(
    server_url=server_url,
    key_prefix=f"mcp_{cfg['slug']}",
    hints=cfg["hint"],
)

st.markdown("---")
show_gateway_logs("home")

st.caption(
    "Note: the workshop's `demo-tools` (stdio) MCP and the `Prompt` asset are catalog-only "
    "and have no gateway endpoint — inspect those with `arctl get mcps` / `arctl get prompts`."
)
