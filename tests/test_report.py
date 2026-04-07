"""
Tests for mcp_audit_trail.report — classify_event + generate_report.
"""

import json
import os

import pytest

from mcp_audit_trail.report import (
    DEFAULT_SENSITIVE_TOOLS,
    DEFAULT_WRITE_TOOLS,
    classify_event,
    generate_report,
)


# ── Sample fixture data ──────────────────────────────────────────────────

SAMPLE_AUDIT_LOG = {
    "session_id": "20260407_120000",
    "start_time": "2026-04-07T12:00:00+00:00",
    "duration_seconds": 2.5,
    "total_events": 4,
    "summary": {
        "total_tool_calls": 3,
        "tools_used": {"get_employee_info": 1, "get_pay_info": 1, "submit_time_off": 1},
        "unique_data_entities_accessed": ["E001"],
        "errors": 0,
        "duration_seconds": 2.5,
    },
    "events": [
        {
            "timestamp": "2026-04-07T12:00:00+00:00",
            "elapsed_seconds": 0.0,
            "direction": "client_to_server",
            "method": "initialize",
        },
        {
            "timestamp": "2026-04-07T12:00:01+00:00",
            "elapsed_seconds": 1.0,
            "direction": "client_to_server",
            "method": "tools/call",
            "tool_name": "get_employee_info",
            "params": {"arguments": {"employee_id": "E001"}},
            "tool_result": {"name": "Alice Chen"},
            "data_accessed": [{"field": "employee_id", "value": "E001"}],
        },
        {
            "timestamp": "2026-04-07T12:00:01.5+00:00",
            "elapsed_seconds": 1.5,
            "direction": "client_to_server",
            "method": "tools/call",
            "tool_name": "get_pay_info",
            "params": {"arguments": {"employee_id": "E001"}},
            "tool_result": {"base_salary": 145000},
            "data_accessed": [{"field": "employee_id", "value": "E001"}],
        },
        {
            "timestamp": "2026-04-07T12:00:02+00:00",
            "elapsed_seconds": 2.0,
            "direction": "client_to_server",
            "method": "tools/call",
            "tool_name": "submit_time_off",
            "params": {"arguments": {"employee_id": "E001", "start_date": "2026-04-14"}},
            "tool_result": {"status": "approved"},
            "data_accessed": [{"field": "employee_id", "value": "E001"}],
        },
    ],
}


@pytest.fixture
def audit_log_file(tmp_path):
    """Write the sample audit log to a temp file and return its path."""
    path = tmp_path / "audit_log.json"
    path.write_text(json.dumps(SAMPLE_AUDIT_LOG))
    return str(path)


# ── classify_event ───────────────────────────────────────────────────────


class TestClassifyEvent:
    def test_sensitive_tool_flagged(self):
        event = {"tool_name": "get_pay_info"}
        flags = classify_event(event)
        assert any(f[0] == "sensitive" for f in flags)

    def test_write_tool_flagged(self):
        event = {"tool_name": "submit_time_off"}
        flags = classify_event(event)
        assert any(f[0] == "action" for f in flags)

    def test_write_tool_also_flagged_sensitive(self):
        event = {"tool_name": "submit_time_off"}
        flags = classify_event(event)
        flag_types = [f[0] for f in flags]
        assert "action" in flag_types
        assert "sensitive" in flag_types

    def test_error_flagged(self):
        event = {"tool_name": "get_info", "has_error": True}
        flags = classify_event(event)
        assert any(f[0] == "error" for f in flags)

    def test_data_access_flagged(self):
        event = {
            "tool_name": "get_info",
            "data_accessed": [{"field": "employee_id", "value": "E001"}],
        }
        flags = classify_event(event)
        assert any(f[0] == "data-access" for f in flags)

    def test_plain_read_tool_no_flags(self):
        event = {"tool_name": "search_employees"}
        flags = classify_event(event)
        # search_employees is not in any default set
        assert len(flags) == 0

    def test_custom_sensitive_tools(self):
        event = {"tool_name": "get_ssn"}
        flags = classify_event(event, sensitive_tools={"get_ssn"})
        assert any(f[0] == "sensitive" for f in flags)

    def test_custom_write_tools(self):
        event = {"tool_name": "delete_user"}
        flags = classify_event(event, write_tools={"delete_user"})
        assert any(f[0] == "action" for f in flags)


# ── generate_report ──────────────────────────────────────────────────────


class TestGenerateReport:
    def test_generates_html_file(self, audit_log_file, tmp_path):
        out = str(tmp_path / "report.html")
        html = generate_report(audit_log_file, out)
        assert os.path.exists(out)
        assert "<!DOCTYPE html>" in html
        assert "MCP Audit Trail" in html

    def test_html_contains_tool_names(self, audit_log_file, tmp_path):
        html = generate_report(audit_log_file, str(tmp_path / "report.html"))
        assert "get_employee_info" in html
        assert "get_pay_info" in html
        assert "submit_time_off" in html

    def test_html_contains_session_id(self, audit_log_file, tmp_path):
        html = generate_report(audit_log_file, str(tmp_path / "report.html"))
        assert "20260407_120000" in html

    def test_html_contains_summary_numbers(self, audit_log_file, tmp_path):
        html = generate_report(audit_log_file, str(tmp_path / "report.html"))
        # 3 tool calls
        assert ">3<" in html

    def test_returns_html_without_writing_when_output_none(self, audit_log_file):
        html = generate_report(audit_log_file, output_path=None)
        assert "<!DOCTYPE html>" in html

    def test_custom_tool_classification(self, audit_log_file, tmp_path):
        html = generate_report(
            audit_log_file,
            str(tmp_path / "report.html"),
            sensitive_tools={"get_employee_info"},
            write_tools=set(),
        )
        assert "SENSITIVE" in html

    def test_report_with_empty_events(self, tmp_path):
        log_data = {
            "session_id": "test",
            "start_time": "2026-04-07T00:00:00+00:00",
            "duration_seconds": 0,
            "total_events": 0,
            "summary": {
                "total_tool_calls": 0,
                "tools_used": {},
                "unique_data_entities_accessed": [],
                "errors": 0,
                "duration_seconds": 0,
            },
            "events": [],
        }
        log_path = str(tmp_path / "empty_log.json")
        with open(log_path, "w") as f:
            json.dump(log_data, f)

        html = generate_report(log_path, str(tmp_path / "report.html"))
        assert "<!DOCTYPE html>" in html
        assert "No data entities tracked" in html

    def test_report_with_error_event(self, tmp_path):
        log_data = {
            "session_id": "test_err",
            "start_time": "2026-04-07T00:00:00+00:00",
            "duration_seconds": 1,
            "total_events": 1,
            "summary": {
                "total_tool_calls": 1,
                "tools_used": {"get_employee_info": 1},
                "unique_data_entities_accessed": [],
                "errors": 1,
                "duration_seconds": 1,
            },
            "events": [
                {
                    "timestamp": "2026-04-07T00:00:00+00:00",
                    "elapsed_seconds": 0.0,
                    "direction": "client_to_server",
                    "method": "tools/call",
                    "tool_name": "get_employee_info",
                    "has_error": True,
                    "params": {"arguments": {"employee_id": "E999"}},
                    "tool_result": {"error": "not found"},
                },
            ],
        }
        log_path = str(tmp_path / "err_log.json")
        with open(log_path, "w") as f:
            json.dump(log_data, f)

        html = generate_report(log_path, str(tmp_path / "report.html"))
        assert "row-error" in html
