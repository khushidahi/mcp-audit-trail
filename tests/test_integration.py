"""
Integration test: run the full demo against the sample server,
then verify the audit log and HTML report were generated correctly.
"""

import asyncio
import json
import sys
from pathlib import Path

import pytest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from mcp_audit_trail.proxy import AuditLogger
from mcp_audit_trail.report import generate_report


SAMPLE_SERVER = str(Path(__file__).resolve().parent.parent / "examples" / "sample_server.py")


@pytest.fixture
def log_path(tmp_path):
    return str(tmp_path / "integration_audit.json")


@pytest.fixture
def report_path(tmp_path):
    return str(tmp_path / "integration_report.html")


async def _run_session(log_path):
    """Run a small MCP session against the sample server, return the logger."""
    logger = AuditLogger(
        log_path,
        sensitive_tools={"get_pay_info"},
        write_tools={"submit_time_off"},
    )

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[SAMPLE_SERVER],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            tool_names = [t.name for t in tools.tools]

            # Call a few tools
            result = await session.call_tool("get_employee_info", {"employee_id": "E001"})
            logger.log("client_to_server", {
                "method": "tools/call",
                "params": {"name": "get_employee_info", "arguments": {"employee_id": "E001"}},
            })

            result = await session.call_tool("get_pay_info", {"employee_id": "E001"})
            logger.log("client_to_server", {
                "method": "tools/call",
                "params": {"name": "get_pay_info", "arguments": {"employee_id": "E001"}},
            })

            result = await session.call_tool("submit_time_off", {
                "employee_id": "E001",
                "start_date": "2026-04-14",
                "end_date": "2026-04-18",
            })
            logger.log("client_to_server", {
                "method": "tools/call",
                "params": {"name": "submit_time_off", "arguments": {"employee_id": "E001"}},
            })

            # Non-existent employee
            result = await session.call_tool("get_employee_info", {"employee_id": "E999"})
            logger.log("client_to_server", {
                "method": "tools/call",
                "params": {"name": "get_employee_info", "arguments": {"employee_id": "E999"}},
            })

    logger.save()
    return logger, tool_names


class TestIntegration:
    def test_full_session_creates_audit_log(self, log_path, report_path):
        """Run a real MCP session, verify audit log is correct."""
        logger, tool_names = asyncio.run(_run_session(log_path))

        # Verify the sample server has expected tools
        assert "get_employee_info" in tool_names
        assert "get_pay_info" in tool_names
        assert "submit_time_off" in tool_names
        assert "search_employees" in tool_names
        assert "check_compliance" in tool_names

        # Verify audit log file
        with open(log_path) as f:
            data = json.load(f)

        assert data["total_events"] == 4
        assert data["summary"]["total_tool_calls"] == 4
        assert "get_employee_info" in data["summary"]["tools_used"]
        assert "get_pay_info" in data["summary"]["tools_used"]

        # Verify data entities were tracked
        entities = data["summary"]["unique_data_entities_accessed"]
        assert "E001" in entities
        assert "E999" in entities

    def test_full_session_generates_report(self, log_path, report_path):
        """Run a real MCP session, generate a report, verify HTML."""
        asyncio.run(_run_session(log_path))

        html = generate_report(log_path, report_path)
        assert Path(report_path).exists()
        assert "<!DOCTYPE html>" in html
        assert "get_employee_info" in html
        assert "get_pay_info" in html

    def test_sensitive_tools_flagged_in_log(self, log_path):
        """Sensitive tools should have a 'sensitive' flag in the log."""
        logger, _ = asyncio.run(_run_session(log_path))

        pay_events = [
            e for e in logger.events
            if e.get("tool_name") == "get_pay_info"
        ]
        assert len(pay_events) == 1
        assert "sensitive" in pay_events[0].get("flags", [])

    def test_write_tools_flagged_in_log(self, log_path):
        """Write tools should have a 'write' flag in the log."""
        logger, _ = asyncio.run(_run_session(log_path))

        write_events = [
            e for e in logger.events
            if e.get("tool_name") == "submit_time_off"
        ]
        assert len(write_events) == 1
        assert "write" in write_events[0].get("flags", [])
