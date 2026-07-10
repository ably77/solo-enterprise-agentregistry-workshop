"""Derive the agentgateway base URL for the agent's LLM traffic.

AgentCore deployments can't receive arbitrary env vars from the registry
(Deployment.spec.runtimeConfig has no env passthrough), and this folder is
cloned from a shared Git URL at deploy time, so a per-user gateway address
can't be baked into the source either. The one per-deployment input the
registry does inject is MCP_SERVERS_CONFIG - and its server URLs point at
the same gateway that serves the /openai LLM route. So the LLM base URL is
derived from it, with OPENAI_BASE_URL as an explicit override for local runs.

This module is deliberately stdlib-only so it can be tested without the
agent's dependencies installed.
"""
import json
import os
from urllib.parse import urlsplit

_LLM_ROUTE_PATH = "/openai"


def openai_base_url() -> str:
    """Return the base URL for OpenAI-protocol LLM calls via agentgateway.

    Resolution order:
      1. OPENAI_BASE_URL env var (local runs / manual override)
      2. scheme://host[:port] of the first MCP_SERVERS_CONFIG server URL,
         plus the gateway's /openai route path

    Raises RuntimeError if neither mechanism yields a URL.
    """
    override = os.environ.get("OPENAI_BASE_URL")
    if override:
        return override

    raw = os.environ.get("MCP_SERVERS_CONFIG")
    if raw:
        try:
            servers = json.loads(raw)
        except json.JSONDecodeError:
            servers = []
        if isinstance(servers, list):
            for server in servers:
                url = server.get("url") if isinstance(server, dict) else None
                if url:
                    parts = urlsplit(url)
                    if parts.scheme and parts.netloc:
                        return f"{parts.scheme}://{parts.netloc}{_LLM_ROUTE_PATH}"

    raise RuntimeError(
        "cannot determine the agentgateway LLM base URL: set OPENAI_BASE_URL, "
        "or deploy through the registry with an MCP server ref so "
        "MCP_SERVERS_CONFIG is injected"
    )
