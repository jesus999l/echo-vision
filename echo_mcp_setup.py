#!/usr/bin/env python3
"""
echo_mcp_setup.py — Wire Echo's APIs as MCP servers via mcpify
Run once to generate configs, then start MCP servers

Services exposed:
- echo_rest    :8765  → Echo main AI interface
- echo_vault   :8767  → Knowledge base search
- echo_brainbridge :8768 → Multi-AI query
- echo_task_manager :7799 → Task management
"""
import subprocess, json, os
from pathlib import Path

MCPIFY_PATH = Path.home() / "repos/mcpify"
VISION_PYTHON = Path.home() / "vision_env/bin/python3"
CONFIGS_DIR = Path.home() / ".config/echo-mcp"
CONFIGS_DIR.mkdir(parents=True, exist_ok=True)

SERVICES = [
    {
        "name": "echo-rest",
        "url": "http://localhost:8765",
        "description": "Echo main AI interface — ask questions, get responses",
        "endpoints": [
            {"path": "/ask", "method": "POST", "params": ["message"]},
            {"path": "/status", "method": "GET"},
        ]
    },
    {
        "name": "echo-vault",
        "url": "http://localhost:8767",
        "description": "Echo knowledge base — search notes and documents",
        "endpoints": [
            {"path": "/search", "method": "POST", "params": ["query", "k"]},
            {"path": "/list", "method": "GET"},
            {"path": "/ingest", "method": "POST", "params": ["title", "content"]},
        ]
    },
    {
        "name": "echo-brainbridge",
        "url": "http://localhost:8768",
        "description": "Multi-AI parallel query — asks ChatGPT+Gemini+Perplexity simultaneously",
        "endpoints": [
            {"path": "/ask", "method": "POST", "params": ["question", "providers"]},
            {"path": "/ask/fast", "method": "POST", "params": ["question", "provider"]},
        ]
    },
    {
        "name": "echo-tasks",
        "url": "http://localhost:7799",
        "description": "Echo task manager — create, list, complete tasks",
        "endpoints": [
            {"path": "/tasks", "method": "GET"},
            {"path": "/tasks", "method": "POST", "params": ["title", "priority"]},
            {"path": "/tasks/complete", "method": "POST", "params": ["id"]},
        ]
    },
]

def write_mcpify_config(service):
    """Write a mcpify-compatible config for a service"""
    config = {
        "name": service["name"],
        "base_url": service["url"],
        "description": service["description"],
        "tools": []
    }

    for ep in service["endpoints"]:
        tool_name = ep["path"].strip("/").replace("/", "_") or "root"
        method = ep["method"]
        params = ep.get("params", [])

        tool = {
            "name": f"{tool_name}_{method.lower()}",
            "method": method,
            "path": ep["path"],
            "description": f"{method} {ep['path']}",
            "parameters": {p: {"type": "string"} for p in params}
        }
        config["tools"].append(tool)

    config_path = CONFIGS_DIR / f"{service['name']}.json"
    config_path.write_text(json.dumps(config, indent=2))
    print(f"[mcp] Config written: {config_path}")
    return config_path

def start_mcp_server(service, config_path):
    """Start an MCP server for a service"""
    log_path = f"/tmp/mcp_{service['name']}.log"
    cmd = [
        str(VISION_PYTHON), "-m", "mcpify", "serve",
        "--config", str(config_path),
        "--port", str(8900 + SERVICES.index(service))
    ]
    print(f"[mcp] Starting {service['name']} MCP server...")
    proc = subprocess.Popen(
        cmd,
        stdout=open(log_path, "w"),
        stderr=subprocess.STDOUT,
        cwd=str(MCPIFY_PATH)
    )
    return proc

def generate_claude_mcp_config():
    """Generate Claude Desktop MCP config"""
    mcp_config = {"mcpServers": {}}
    for i, service in enumerate(SERVICES):
        port = 8900 + i
        mcp_config["mcpServers"][service["name"]] = {
            "command": str(VISION_PYTHON),
            "args": [
                "-m", "mcpify", "serve",
                "--config", str(CONFIGS_DIR / f"{service['name']}.json"),
                "--port", str(port)
            ],
            "cwd": str(MCPIFY_PATH)
        }

    claude_config_path = Path.home() / ".config/claude/mcp_servers.json"
    claude_config_path.parent.mkdir(parents=True, exist_ok=True)
    claude_config_path.write_text(json.dumps(mcp_config, indent=2))
    print(f"[mcp] Claude MCP config: {claude_config_path}")
    return claude_config_path

if __name__ == "__main__":
    print("[mcp] Setting up Echo MCP servers...")

    # Write configs
    config_paths = []
    for service in SERVICES:
        cp = write_mcpify_config(service)
        config_paths.append(cp)

    # Generate Claude config
    claude_cfg = generate_claude_mcp_config()

    print("\n[mcp] All configs written.")
    print("\nTo start MCP servers, run:")
    for i, service in enumerate(SERVICES):
        port = 8900 + i
        print(f"  {VISION_PYTHON} -m mcpify serve --config {CONFIGS_DIR}/{service['name']}.json --port {port} &")

    print(f"\nClaude Desktop config at: {claude_cfg}")
    print("Add this to your Claude Desktop settings to use Echo as MCP tools.")
