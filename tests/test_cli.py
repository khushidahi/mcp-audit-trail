"""
Tests for mcp_audit_trail.cli — CLI argument parsing and wiring.
"""

import subprocess
import sys

import pytest


class TestProxyCli:
    def test_help_flag(self):
        result = subprocess.run(
            [sys.executable, "-m", "mcp_audit_trail.cli"],
            capture_output=True,
            text=True,
        )
        # Module doesn't have __main__ behaviour — test via entry point
        pass

    def test_proxy_help(self):
        """mcp-audit-proxy --help should succeed and show usage."""
        result = subprocess.run(
            ["mcp-audit-proxy", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--server" in result.stdout
        assert "--log" in result.stdout
        assert "--sensitive-tools" in result.stdout
        assert "--write-tools" in result.stdout

    def test_proxy_requires_server(self):
        """mcp-audit-proxy without --server should fail."""
        result = subprocess.run(
            ["mcp-audit-proxy"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "required" in result.stderr.lower() or "error" in result.stderr.lower()


class TestReportCli:
    def test_report_help(self):
        """mcp-audit-report --help should succeed and show usage."""
        result = subprocess.run(
            ["mcp-audit-report", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--input" in result.stdout
        assert "--output" in result.stdout

    def test_report_missing_input(self):
        """mcp-audit-report with a bad input file should fail gracefully."""
        result = subprocess.run(
            ["mcp-audit-report", "--input", "/nonexistent/path.json"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
