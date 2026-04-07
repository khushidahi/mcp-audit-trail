"""
mcp-audit-trail: Lightweight observability for MCP agent interactions.

Sits between an MCP client and server, captures every tool call,
and generates a visual audit trail.
"""

from mcp_audit_trail.proxy import AuditLogger, run_proxy
from mcp_audit_trail.report import generate_report

__version__ = "0.1.0"
__all__ = ["AuditLogger", "run_proxy", "generate_report"]
