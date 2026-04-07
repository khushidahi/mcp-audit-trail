"""
MCP Audit Proxy

A transparent stdio proxy that sits between an MCP client and server,
capturing every JSON-RPC message for audit and observability.
"""

import sys
import json
import subprocess
import threading
import time
from datetime import datetime, timezone


class AuditLogger:
    """Structured logger for MCP interactions.

    Captures JSON-RPC messages flowing between an MCP client and server,
    extracting tool call metadata, arguments, results, and errors.

    Usage::

        logger = AuditLogger("audit_log.json")
        logger.log("client_to_server", {"method": "tools/call", ...})
        logger.save()

    You can also add custom sensitive-tool or write-tool rules::

        logger = AuditLogger(
            "audit_log.json",
            sensitive_tools={"get_pay_info", "get_ssn"},
            write_tools={"submit_time_off", "delete_record"},
        )
    """

    def __init__(self, log_path, *, sensitive_tools=None, write_tools=None):
        self.log_path = log_path
        self.session_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.events = []
        self.start_time = time.time()
        self.lock = threading.Lock()
        self.sensitive_tools = sensitive_tools or set()
        self.write_tools = write_tools or set()

    def log(self, direction, message):
        """Record a single JSON-RPC message.

        Args:
            direction: One of ``"client_to_server"`` or ``"server_to_client"``.
            message: The parsed JSON-RPC message dict.
        """
        elapsed = round(time.time() - self.start_time, 4)
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": elapsed,
            "direction": direction,
            "message": message,
        }

        if isinstance(message, dict):
            if "method" in message:
                event["method"] = message["method"]
            if "id" in message:
                event["rpc_id"] = message["id"]
            if "error" in message:
                event["has_error"] = True

            # Extract tool call details
            if message.get("method") == "tools/call":
                params = message.get("params", {})
                tool_name = params.get("name", "unknown")
                event["tool_name"] = tool_name
                event["tool_arguments"] = params.get("arguments", {})

                # Auto-flag sensitive / write tools
                if tool_name in self.sensitive_tools:
                    event["flags"] = event.get("flags", [])
                    event["flags"].append("sensitive")
                if tool_name in self.write_tools:
                    event["flags"] = event.get("flags", [])
                    event["flags"].append("write")

            # Extract tool results
            if "result" in message and isinstance(message["result"], dict):
                content = message["result"].get("content", [])
                if content and isinstance(content, list):
                    for item in content:
                        if item.get("type") == "text":
                            try:
                                event["tool_result"] = json.loads(item["text"])
                            except (json.JSONDecodeError, TypeError):
                                event["tool_result"] = item.get("text", "")

        with self.lock:
            self.events.append(event)

    def build_summary(self):
        """Build an aggregate summary of the recorded session."""
        tool_calls = [e for e in self.events if e.get("method") == "tools/call"]
        tools_used = {}
        for tc in tool_calls:
            name = tc.get("tool_name", "unknown")
            tools_used[name] = tools_used.get(name, 0) + 1

        errors = [e for e in self.events if e.get("has_error")]

        data_accessed = set()
        for e in self.events:
            args = e.get("tool_arguments", {})
            for key, val in args.items():
                if "id" in key.lower() or "employee" in key.lower():
                    data_accessed.add(str(val))

        return {
            "total_tool_calls": len(tool_calls),
            "tools_used": tools_used,
            "unique_data_entities_accessed": sorted(data_accessed),
            "errors": len(errors),
            "duration_seconds": round(time.time() - self.start_time, 2),
        }

    def save(self):
        """Write the audit log to disk as JSON."""
        summary = self.build_summary()
        output = {
            "session_id": self.session_id,
            "start_time": datetime.fromtimestamp(
                self.start_time, tz=timezone.utc
            ).isoformat(),
            "total_events": len(self.events),
            "summary": summary,
            "events": self.events,
        }
        with open(self.log_path, "w") as f:
            json.dump(output, f, indent=2, default=str)


# ---------------------------------------------------------------------------
# Stdio JSON-RPC helpers
# ---------------------------------------------------------------------------

def read_jsonrpc_message(stream):
    """Read a JSON-RPC message from a byte/text stream using Content-Length."""
    headers = {}
    while True:
        line = stream.readline()
        if not line:
            return None
        line = line.strip()
        if line == b"" or line == "":
            break
        if isinstance(line, bytes):
            line = line.decode("utf-8")
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip()] = value.strip()

    content_length = int(headers.get("Content-Length", 0))
    if content_length == 0:
        return None

    body = stream.read(content_length)
    if isinstance(body, bytes):
        body = body.decode("utf-8")

    return json.loads(body)


def write_jsonrpc_message(stream, message):
    """Write a JSON-RPC message with Content-Length header."""
    body = json.dumps(message)
    if isinstance(body, str):
        body_bytes = body.encode("utf-8")
    else:
        body_bytes = body

    header = f"Content-Length: {len(body_bytes)}\r\n\r\n"

    if hasattr(stream, "buffer"):
        stream.buffer.write(header.encode("utf-8"))
        stream.buffer.write(body_bytes)
        stream.buffer.flush()
    else:
        stream.write(header.encode("utf-8"))
        stream.write(body_bytes)
        stream.flush()


# ---------------------------------------------------------------------------
# Proxy threads
# ---------------------------------------------------------------------------

def _proxy_client_to_server(client_stdin, server_stdin, logger):
    try:
        while True:
            msg = read_jsonrpc_message(client_stdin)
            if msg is None:
                break
            logger.log("client_to_server", msg)
            write_jsonrpc_message(server_stdin, msg)
    except Exception as e:
        logger.log("error", {"type": "client_to_server_error", "detail": str(e)})


def _proxy_server_to_client(server_stdout, client_stdout, logger):
    try:
        while True:
            msg = read_jsonrpc_message(server_stdout)
            if msg is None:
                break
            logger.log("server_to_client", msg)
            write_jsonrpc_message(client_stdout, msg)
    except Exception as e:
        logger.log("error", {"type": "server_to_client_error", "detail": str(e)})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_proxy(server_command, log_path="audit_log.json", *, sensitive_tools=None, write_tools=None):
    """Start an MCP server and proxy all stdio communication through the audit logger.

    This is the main entry point for running the proxy programmatically.

    Args:
        server_command: Shell command to start the MCP server
            (e.g. ``"python my_server.py"``).
        log_path: Where to write the JSON audit log.
        sensitive_tools: Optional set of tool names to flag as sensitive.
        write_tools: Optional set of tool names to flag as write actions.
    """
    logger = AuditLogger(
        log_path,
        sensitive_tools=sensitive_tools,
        write_tools=write_tools,
    )

    print(f"[audit-proxy] Starting server: {server_command}", file=sys.stderr)
    print(f"[audit-proxy] Logging to: {log_path}", file=sys.stderr)

    server_process = subprocess.Popen(
        server_command,
        shell=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    client_thread = threading.Thread(
        target=_proxy_client_to_server,
        args=(sys.stdin.buffer, server_process.stdin, logger),
        daemon=True,
    )
    server_thread = threading.Thread(
        target=_proxy_server_to_client,
        args=(server_process.stdout, sys.stdout, logger),
        daemon=True,
    )

    client_thread.start()
    server_thread.start()

    try:
        server_process.wait()
    except KeyboardInterrupt:
        server_process.terminate()
    finally:
        logger.save()
        print(
            f"\n[audit-proxy] Session complete. "
            f"{len(logger.events)} events logged to {log_path}",
            file=sys.stderr,
        )
