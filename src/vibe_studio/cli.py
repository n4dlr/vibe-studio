"""CLI Interface for Vibe Studio 5.0 Omniverse.

Commands:
  vibe-studio run "prompt" [--root /path] [--file active.py]
  vibe-studio server [--host 127.0.0.1] [--port 8000]
  vibe-studio index [--root /path]
  vibe-studio search "query" [--root /path]
  vibe-studio doc [--root /path]
  vibe-studio review [--diff file.diff]
  vibe-studio audit [--root /path]
  vibe-studio plugin [list|search|install|uninstall]
  vibe-studio swarm [coordinator|worker]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from vibe_studio.agents.code_reviewer import CodeReviewerAgent
from vibe_studio.agents.orchestrator import AgentOrchestrator
from vibe_studio.api.http_server import create_api_server
from vibe_studio.api.websocket_server import get_ws_server
from vibe_studio.context.parallel_graph_builder import ParallelGraphBuilder
from vibe_studio.context.semantic_search import SemanticCodeSearch
from vibe_studio.plugins.marketplace import PluginMarketplace
from vibe_studio.project.doc_generator import AutoDocGenerator
from vibe_studio.security.security_auditor import SecurityAuditor
from vibe_studio.swarm import SwarmCoordinator, SwarmWorker


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vibe-studio",
        description="Vibe Studio 5.0 Omniverse — AI-native desktop, web, swarm & security coding agent",
    )
    parser.add_argument("--root", type=str, default=".", help="Workspace root directory")
    subparsers = parser.add_subparsers(dest="subcommand", help="Subcommand to execute")

    # --- Subcommand: run ---
    run_parser = subparsers.add_parser("run", help="Run an autonomous agent task in headless CLI mode")
    run_parser.add_argument("prompt", type=str, help="Task prompt for the agent")
    run_parser.add_argument("--file", type=str, default=None, help="Active file path hint")

    # --- Subcommand: server ---
    server_parser = subparsers.add_parser("server", help="Start REST API & Web UI HTTP server")
    server_parser.add_argument("--host", type=str, default="127.0.0.1", help="Host IP to bind")
    server_parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    server_parser.add_argument("--ws-port", type=int, default=8001, help="WebSocket port")

    # --- Subcommand: index ---
    subparsers.add_parser("index", help="Build and cache Graph RAG AST index for a codebase")

    # --- Subcommand: search ---
    search_parser = subparsers.add_parser("search", help="Natural language semantic code search")
    search_parser.add_argument("query", type=str, help="Natural language query")

    # --- Subcommand: doc ---
    subparsers.add_parser("doc", help="Generate API reference and Mermaid architecture diagrams")

    # --- Subcommand: review ---
    review_parser = subparsers.add_parser("review", help="Run automated PR code review")
    review_parser.add_argument("--diff", type=str, default=None, help="Path to diff file")

    # --- Subcommand: audit ---
    subparsers.add_parser("audit", help="Run AI Security Auditor for secret leaks & AST vulnerabilities")

    # --- Subcommand: plugin ---
    plugin_parser = subparsers.add_parser("plugin", help="Manage in-repo marketplace plugins")
    plugin_sub = plugin_parser.add_subparsers(dest="plugin_subcommand", help="Plugin action")
    plugin_sub.add_parser("list", help="List available plugins")
    p_search = plugin_sub.add_parser("search", help="Search plugins")
    p_search.add_argument("query", type=str, help="Search query")
    p_install = plugin_sub.add_parser("install", help="Install a plugin")
    p_install.add_argument("name", type=str, help="Plugin name")
    p_uninstall = plugin_sub.add_parser("uninstall", help="Uninstall a plugin")
    p_uninstall.add_argument("name", type=str, help="Plugin name")

    # --- Subcommand: swarm ---
    swarm_parser = subparsers.add_parser("swarm", help="Distributed Agent Swarm control")
    swarm_sub = swarm_parser.add_subparsers(dest="swarm_subcommand", help="Swarm action")
    c_parser = swarm_sub.add_parser("coordinator", help="Start Swarm coordinator node")
    c_parser.add_argument("--host", type=str, default="127.0.0.1")
    c_parser.add_argument("--port", type=int, default=9000)

    w_parser = swarm_sub.add_parser("worker", help="Start Swarm worker node")
    w_parser.add_argument("--id", type=str, default="worker-1")
    w_parser.add_argument("--host", type=str, default="127.0.0.1")
    w_parser.add_argument("--port", type=int, default=9100)
    w_parser.add_argument("--coordinator", type=str, default="http://127.0.0.1:9000")

    args = parser.parse_args(argv)

    if not args.subcommand:
        from vibe_studio.__main__ import main as gui_main
        return gui_main()

    root = Path(getattr(args, "root", ".")).resolve()

    if args.subcommand == "run":
        print(f"🤖 [Vibe Studio CLI] Running task: {args.prompt}")
        orch = AgentOrchestrator(workspace_root=root)
        res = orch.execute_task(prompt=args.prompt, active_file=args.file)
        print("\n" + res.summary)
        return 0 if (res.execution_result and res.execution_result.status.value == "completed") else 1

    elif args.subcommand == "server":
        print(f"🌌 [Vibe Studio 5.0 Omniverse] Starting Web UI & REST API at http://{args.host}:{args.port}")
        print(f"⚡ Starting WebSocket stream on ws://{args.host}:{args.ws_port}")
        get_ws_server(host=args.host, port=args.ws_port)
        srv = create_api_server(workspace_root=root, host=args.host, port=args.port)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")
        return 0

    elif args.subcommand == "index":
        print(f"🔍 Indexing codebase AST call graph at: {root}")
        builder = ParallelGraphBuilder(root)
        cg = builder.build()
        print(f"✅ Indexed {len(cg.symbol_file_map)} symbols across {len(cg.file_symbols_map)} files.")
        return 0

    elif args.subcommand == "search":
        print(f"🔍 Searching natural language query: '{args.query}' in {root}")
        searcher = SemanticCodeSearch(workspace_root=root)
        results = searcher.search(args.query, top_k=5)
        for r in results:
            print(f"  - [{r.symbol_type.upper()}] {r.file_path}:{r.line_number} -> {r.symbol_name} ({r.relevance_reason})")
        return 0

    elif args.subcommand == "doc":
        print(f"📚 Generating auto-documentation for: {root}")
        gen = AutoDocGenerator(workspace_root=root)
        api_md = gen.generate_api_reference()
        mermaid = gen.generate_mermaid_diagram()
        (root / "API_REFERENCE.md").write_text(api_md, encoding="utf-8")
        print(f"✅ Created API_REFERENCE.md ({len(api_md)} chars)")
        print("\nMermaid Class Diagram:\n" + mermaid)
        return 0

    elif args.subcommand == "review":
        diff_content = ""
        if args.diff:
            diff_content = Path(args.diff).read_text(encoding="utf-8")
        else:
            print("⚠️ No --diff provided. Running review demo on stdin/sample.")
            diff_content = "@@ -1,2 +1,3 @@\n+SECRET_KEY = 'demo_key'\n"

        reviewer = CodeReviewerAgent()
        report = reviewer.review_diff(diff_content)
        print("\n" + report.to_markdown())
        return 0

    elif args.subcommand == "audit":
        print(f"🛡️ Running AI Security Auditor on: {root}")
        auditor = SecurityAuditor(workspace_root=root)
        report = auditor.scan_workspace()
        print("\n" + report.to_markdown())
        return 0

    elif args.subcommand == "plugin":
        mp = PluginMarketplace(workspace_root=root)
        sub = args.plugin_subcommand
        if sub == "list" or not sub:
            plugins = mp.list_available()
            print(f"🔌 Marketplace Plugins ({len(plugins)} available):")
            for p in plugins:
                status = "✓ installed" if p["installed"] else "available"
                print(f"  - {p['name']} ({p['category']}) [{status}]: {p['description']}")
        elif sub == "search":
            results = mp.search(args.query)
            print(f"🔍 Search results for '{args.query}' ({len(results)} found):")
            for p in results:
                print(f"  - {p['name']}: {p['description']}")
        elif sub == "install":
            ok = mp.install(args.name)
            print(f"✅ Installed plugin '{args.name}'" if ok else f"❌ Failed to install '{args.name}'")
        elif sub == "uninstall":
            ok = mp.uninstall(args.name)
            print(f"✅ Uninstalled plugin '{args.name}'" if ok else f"❌ Plugin '{args.name}' not found")
        return 0

    elif args.subcommand == "swarm":
        sub = args.swarm_subcommand
        if sub == "coordinator":
            coord = SwarmCoordinator(host=args.host, port=args.port)
            coord.start_heartbeat_monitor()
            print(f"🐝 Swarm Coordinator running at http://{args.host}:{args.port}")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                coord.stop()
        elif sub == "worker":
            worker = SwarmWorker(worker_id=args.id, host=args.host, port=args.port, coordinator_url=args.coordinator, workspace_root=root)
            worker.start()
            print(f"🐝 Swarm Worker '{args.id}' running at http://{args.host}:{args.port}")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                worker.stop()
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
