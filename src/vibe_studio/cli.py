"""CLI Interface for Vibe Studio 3.0.

Commands:
  vibe-studio run "prompt" [--root /path] [--file active.py]
  vibe-studio server [--host 127.0.0.1] [--port 8000]
  vibe-studio index [--root /path]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from vibe_studio.agents.orchestrator import AgentOrchestrator
from vibe_studio.api.http_server import create_api_server
from vibe_studio.context.parallel_graph_builder import ParallelGraphBuilder


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vibe-studio",
        description="Vibe Studio 3.0 — AI-native desktop & headless coding agent",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Subcommand to execute")

    # --- Subcommand: run ---
    run_parser = subparsers.add_parser("run", help="Run an autonomous agent task in headless CLI mode")
    run_parser.add_argument("prompt", type=str, help="Task prompt for the agent")
    run_parser.add_argument("--root", type=str, default=".", help="Workspace root directory")
    run_parser.add_argument("--file", type=str, default=None, help="Active file path hint")

    # --- Subcommand: server ---
    server_parser = subparsers.add_parser("server", help="Start the Vibe Studio REST API HTTP server")
    server_parser.add_argument("--host", type=str, default="127.0.0.1", help="Host IP to bind")
    server_parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    server_parser.add_argument("--root", type=str, default=".", help="Workspace root directory")

    # --- Subcommand: index ---
    index_parser = subparsers.add_parser("index", help="Build and cache Graph RAG AST index for a codebase")
    index_parser.add_argument("--root", type=str, default=".", help="Workspace root directory")

    args = parser.parse_args(argv)

    if not args.subcommand:
        # Default to launching the GUI app if no subcommand given
        from vibe_studio.__main__ import main as gui_main
        return gui_main()

    root = Path(args.root).resolve()

    if args.subcommand == "run":
        print(f"🤖 [Vibe Studio CLI] Running task: {args.prompt}")
        print(f"📁 Workspace: {root}")
        orch = AgentOrchestrator(workspace_root=root)
        res = orch.execute_task(prompt=args.prompt, active_file=args.file)
        print("\n" + res.summary)
        return 0 if (res.execution_result and res.execution_result.status.value == "completed") else 1

    elif args.subcommand == "server":
        print(f"🌐 Starting REST API server at http://{args.host}:{args.port} (Workspace: {root})")
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

    return 0


if __name__ == "__main__":
    sys.exit(main())
