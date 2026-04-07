"""
CLI entry points for mcp-audit-trail.

After ``pip install mcp-audit-trail`` the following commands are available:

    mcp-audit-proxy  --server "python my_server.py" --log audit.json
    mcp-audit-report --input audit.json --output report.html
"""

import argparse
import sys


def proxy_cli():
    """CLI: run the transparent audit proxy."""
    from mcp_audit_trail.proxy import run_proxy

    parser = argparse.ArgumentParser(
        prog="mcp-audit-proxy",
        description="Transparent MCP audit proxy — logs every JSON-RPC message.",
    )
    parser.add_argument(
        "--server",
        required=True,
        help='Command to start the MCP server (e.g. "python my_server.py")',
    )
    parser.add_argument(
        "--log",
        default="audit_log.json",
        help="Path for the JSON audit log (default: audit_log.json)",
    )
    parser.add_argument(
        "--sensitive-tools",
        nargs="*",
        default=[],
        help="Tool names to flag as sensitive (space-separated)",
    )
    parser.add_argument(
        "--write-tools",
        nargs="*",
        default=[],
        help="Tool names to flag as write actions (space-separated)",
    )
    args = parser.parse_args()

    run_proxy(
        args.server,
        args.log,
        sensitive_tools=set(args.sensitive_tools) if args.sensitive_tools else None,
        write_tools=set(args.write_tools) if args.write_tools else None,
    )


def report_cli():
    """CLI: generate an HTML report from an audit log."""
    from mcp_audit_trail.report import generate_report

    parser = argparse.ArgumentParser(
        prog="mcp-audit-report",
        description="Generate an interactive HTML audit trail from a JSON log.",
    )
    parser.add_argument(
        "--input",
        default="audit_log.json",
        help="Path to the audit log JSON (default: audit_log.json)",
    )
    parser.add_argument(
        "--output",
        default="audit_report.html",
        help="Path for the HTML report (default: audit_report.html)",
    )
    args = parser.parse_args()

    generate_report(args.input, args.output)
    print(f"Report generated: {args.output}")
    print("Open in a browser to view the audit trail.")
