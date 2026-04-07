"""
Tests for mcp_audit_trail.proxy — AuditLogger and JSON-RPC helpers.
"""

import io
import json
import os
import tempfile
import threading

import pytest

from mcp_audit_trail.proxy import (
    AuditLogger,
    read_jsonrpc_message,
    write_jsonrpc_message,
)


# ── AuditLogger ──────────────────────────────────────────────────────────


class TestAuditLoggerInit:
    def test_creates_session_id(self, tmp_path):
        logger = AuditLogger(str(tmp_path / "log.json"))
        assert logger.session_id  # non-empty string like "20260407_120000"
        assert len(logger.events) == 0

    def test_accepts_sensitive_and_write_tools(self, tmp_path):
        logger = AuditLogger(
            str(tmp_path / "log.json"),
            sensitive_tools={"get_ssn"},
            write_tools={"delete_user"},
        )
        assert "get_ssn" in logger.sensitive_tools
        assert "delete_user" in logger.write_tools

    def test_defaults_to_empty_sets(self, tmp_path):
        logger = AuditLogger(str(tmp_path / "log.json"))
        assert logger.sensitive_tools == set()
        assert logger.write_tools == set()


class TestAuditLoggerLog:
    def test_logs_basic_event(self, tmp_path):
        logger = AuditLogger(str(tmp_path / "log.json"))
        logger.log("client_to_server", {"method": "initialize"})
        assert len(logger.events) == 1
        event = logger.events[0]
        assert event["direction"] == "client_to_server"
        assert event["method"] == "initialize"
        assert "timestamp" in event
        assert "elapsed_seconds" in event

    def test_logs_tool_call_with_metadata(self, tmp_path):
        logger = AuditLogger(str(tmp_path / "log.json"))
        logger.log("client_to_server", {
            "method": "tools/call",
            "id": 1,
            "params": {"name": "get_info", "arguments": {"id": "E001"}},
        })
        event = logger.events[0]
        assert event["tool_name"] == "get_info"
        assert event["tool_arguments"] == {"id": "E001"}
        assert event["rpc_id"] == 1

    def test_logs_error(self, tmp_path):
        logger = AuditLogger(str(tmp_path / "log.json"))
        logger.log("server_to_client", {"error": {"code": -1, "message": "fail"}})
        assert logger.events[0]["has_error"] is True

    def test_extracts_tool_result_from_response(self, tmp_path):
        logger = AuditLogger(str(tmp_path / "log.json"))
        logger.log("server_to_client", {
            "id": 1,
            "result": {
                "content": [{"type": "text", "text": '{"name": "Alice"}'}]
            },
        })
        assert logger.events[0]["tool_result"] == {"name": "Alice"}

    def test_extracts_plain_text_result(self, tmp_path):
        logger = AuditLogger(str(tmp_path / "log.json"))
        logger.log("server_to_client", {
            "id": 1,
            "result": {
                "content": [{"type": "text", "text": "plain string"}]
            },
        })
        assert logger.events[0]["tool_result"] == "plain string"

    def test_flags_sensitive_tool(self, tmp_path):
        logger = AuditLogger(
            str(tmp_path / "log.json"),
            sensitive_tools={"get_pay_info"},
        )
        logger.log("client_to_server", {
            "method": "tools/call",
            "params": {"name": "get_pay_info", "arguments": {}},
        })
        assert "sensitive" in logger.events[0]["flags"]

    def test_flags_write_tool(self, tmp_path):
        logger = AuditLogger(
            str(tmp_path / "log.json"),
            write_tools={"delete_record"},
        )
        logger.log("client_to_server", {
            "method": "tools/call",
            "params": {"name": "delete_record", "arguments": {}},
        })
        assert "write" in logger.events[0]["flags"]

    def test_no_flags_for_normal_tool(self, tmp_path):
        logger = AuditLogger(
            str(tmp_path / "log.json"),
            sensitive_tools={"get_pay_info"},
            write_tools={"delete_record"},
        )
        logger.log("client_to_server", {
            "method": "tools/call",
            "params": {"name": "search_employees", "arguments": {}},
        })
        assert "flags" not in logger.events[0]

    def test_handles_non_dict_message(self, tmp_path):
        logger = AuditLogger(str(tmp_path / "log.json"))
        logger.log("client_to_server", "raw string message")
        assert len(logger.events) == 1
        assert logger.events[0]["message"] == "raw string message"


class TestAuditLoggerSummary:
    def _make_logger_with_events(self, tmp_path):
        logger = AuditLogger(str(tmp_path / "log.json"))
        logger.log("client_to_server", {
            "method": "tools/call",
            "params": {"name": "get_info", "arguments": {"employee_id": "E001"}},
        })
        logger.log("client_to_server", {
            "method": "tools/call",
            "params": {"name": "get_info", "arguments": {"employee_id": "E002"}},
        })
        logger.log("client_to_server", {
            "method": "tools/call",
            "params": {"name": "get_pay", "arguments": {"employee_id": "E001"}},
        })
        logger.log("server_to_client", {"error": {"code": -1, "message": "boom"}})
        return logger

    def test_total_tool_calls(self, tmp_path):
        logger = self._make_logger_with_events(tmp_path)
        summary = logger.build_summary()
        assert summary["total_tool_calls"] == 3

    def test_tools_used_counts(self, tmp_path):
        logger = self._make_logger_with_events(tmp_path)
        summary = logger.build_summary()
        assert summary["tools_used"] == {"get_info": 2, "get_pay": 1}

    def test_unique_data_entities(self, tmp_path):
        logger = self._make_logger_with_events(tmp_path)
        summary = logger.build_summary()
        assert sorted(summary["unique_data_entities_accessed"]) == ["E001", "E002"]

    def test_error_count(self, tmp_path):
        logger = self._make_logger_with_events(tmp_path)
        summary = logger.build_summary()
        assert summary["errors"] == 1

    def test_duration_is_positive(self, tmp_path):
        logger = self._make_logger_with_events(tmp_path)
        summary = logger.build_summary()
        assert summary["duration_seconds"] >= 0


class TestAuditLoggerSave:
    def test_save_creates_valid_json(self, tmp_path):
        log_path = str(tmp_path / "log.json")
        logger = AuditLogger(log_path)
        logger.log("client_to_server", {"method": "initialize"})
        logger.log("client_to_server", {
            "method": "tools/call",
            "params": {"name": "search", "arguments": {"q": "test"}},
        })
        logger.save()

        with open(log_path) as f:
            data = json.load(f)

        assert data["session_id"] == logger.session_id
        assert data["total_events"] == 2
        assert "summary" in data
        assert "events" in data
        assert data["summary"]["total_tool_calls"] == 1

    def test_save_overwrites_existing(self, tmp_path):
        log_path = str(tmp_path / "log.json")
        logger = AuditLogger(log_path)
        logger.log("client_to_server", {"method": "initialize"})
        logger.save()
        # Save again — should overwrite without error
        logger.log("client_to_server", {"method": "tools/list"})
        logger.save()

        with open(log_path) as f:
            data = json.load(f)
        assert data["total_events"] == 2


class TestAuditLoggerThreadSafety:
    def test_concurrent_logging(self, tmp_path):
        logger = AuditLogger(str(tmp_path / "log.json"))
        errors = []

        def log_events(start, count):
            try:
                for i in range(count):
                    logger.log("client_to_server", {
                        "method": "tools/call",
                        "params": {"name": f"tool_{start + i}", "arguments": {}},
                    })
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=log_events, args=(i * 100, 100)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(logger.events) == 500


# ── JSON-RPC helpers ─────────────────────────────────────────────────────


class TestJsonRpcRoundTrip:
    def test_write_then_read(self):
        """Write a message, then read it back — should round-trip perfectly."""
        msg = {"jsonrpc": "2.0", "method": "initialize", "id": 1}

        buf = io.BytesIO()
        write_jsonrpc_message(buf, msg)

        buf.seek(0)
        result = read_jsonrpc_message(buf)
        assert result == msg

    def test_multiple_messages(self):
        msgs = [
            {"jsonrpc": "2.0", "method": "tools/list", "id": 1},
            {"jsonrpc": "2.0", "method": "tools/call", "id": 2, "params": {"name": "foo"}},
        ]

        buf = io.BytesIO()
        for m in msgs:
            write_jsonrpc_message(buf, m)

        buf.seek(0)
        results = []
        for _ in msgs:
            results.append(read_jsonrpc_message(buf))
        assert results == msgs

    def test_read_returns_none_on_empty(self):
        buf = io.BytesIO(b"")
        assert read_jsonrpc_message(buf) is None

    def test_unicode_content(self):
        msg = {"jsonrpc": "2.0", "result": {"name": "日本語テスト"}, "id": 1}
        buf = io.BytesIO()
        write_jsonrpc_message(buf, msg)
        buf.seek(0)
        assert read_jsonrpc_message(buf) == msg
