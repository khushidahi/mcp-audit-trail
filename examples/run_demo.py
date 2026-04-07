"""
Demo: Run a series of MCP tool calls against the sample server
and generate an audit log + HTML report.

Usage:
    pip install mcp-audit-trail[demo]
    python -m examples.run_demo
"""

import asyncio
import json
import sys
import os
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure the repo root is on the path when running as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp_audit_trail.report import generate_report


class AuditTrailCapture:
    """Captures all MCP interactions for audit logging."""

    def __init__(self):
        self.events = []
        self.start_time = time.time()
        self.session_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    def record(self, direction, method, params=None, result=None, error=None, tool_name=None):
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": round(time.time() - self.start_time, 4),
            "direction": direction,
            "method": method,
        }
        if params:
            event["params"] = params
        if tool_name:
            event["tool_name"] = tool_name
        if result is not None:
            event["tool_result"] = result
        if error:
            event["has_error"] = True
            event["error_detail"] = error

        # Track data entities accessed
        if params and isinstance(params, dict):
            args = params.get("arguments", params)
            accessed = []
            for key, val in args.items():
                if "id" in key.lower() or "employee" in key.lower() or "region" in key.lower():
                    accessed.append({"field": key, "value": str(val)})
            if accessed:
                event["data_accessed"] = accessed

        self.events.append(event)

    def save(self, path="audit_log.json"):
        tool_calls = [e for e in self.events if e.get("method") == "tools/call"]
        tools_used = {}
        data_entities = set()
        errors = 0

        for tc in tool_calls:
            name = tc.get("tool_name", "unknown")
            tools_used[name] = tools_used.get(name, 0) + 1
            for da in tc.get("data_accessed", []):
                data_entities.add(da["value"])
            if tc.get("has_error"):
                errors += 1

        output = {
            "session_id": self.session_id,
            "start_time": datetime.fromtimestamp(self.start_time, tz=timezone.utc).isoformat(),
            "duration_seconds": round(time.time() - self.start_time, 2),
            "total_events": len(self.events),
            "summary": {
                "total_tool_calls": len(tool_calls),
                "tools_used": tools_used,
                "unique_data_entities_accessed": sorted(list(data_entities)),
                "errors": errors,
            },
            "events": self.events,
        }

        with open(path, "w") as f:
            json.dump(output, f, indent=2, default=str)

        print(f"Audit log saved to {path}")
        print(f"  Session: {self.session_id}")
        print(f"  Events: {len(self.events)}")
        print(f"  Tool calls: {len(tool_calls)}")
        print(f"  Tools used: {list(tools_used.keys())}")
        print(f"  Data entities: {sorted(list(data_entities))}")
        print(f"  Errors: {errors}")


async def run_demo():
    audit = AuditTrailCapture()

    # Locate the sample server relative to this file
    server_script = str(Path(__file__).resolve().parent / "sample_server.py")

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[server_script],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            audit.record("client_to_server", "initialize")

            tools = await session.list_tools()
            tool_names = [t.name for t in tools.tools]
            audit.record("client_to_server", "tools/list", result=tool_names)
            print(f"\nAvailable tools: {tool_names}\n")

            # 1. Search for engineering team
            print("1. Searching for engineering team...")
            result = await session.call_tool("search_employees", {"query": "Engineering"})
            parsed = json.loads(result.content[0].text)
            audit.record("client_to_server", "tools/call",
                         params={"arguments": {"query": "Engineering"}},
                         tool_name="search_employees", result=parsed)
            print(f"   Found {parsed['count']} employees\n")

            # 2. Look up Alice Chen
            print("2. Looking up Alice Chen (E001)...")
            result = await session.call_tool("get_employee_info", {"employee_id": "E001"})
            parsed = json.loads(result.content[0].text)
            audit.record("client_to_server", "tools/call",
                         params={"arguments": {"employee_id": "E001"}},
                         tool_name="get_employee_info", result=parsed)
            print(f"   {parsed['name']}, {parsed['role']}, PTO: {parsed['pto_balance']} days\n")

            # 3. Pay info (sensitive)
            print("3. Accessing pay information for Alice Chen...")
            result = await session.call_tool("get_pay_info", {"employee_id": "E001"})
            parsed = json.loads(result.content[0].text)
            audit.record("client_to_server", "tools/call",
                         params={"arguments": {"employee_id": "E001"}},
                         tool_name="get_pay_info", result=parsed)
            print(f"   Salary: ${parsed['base_salary']:,}\n")

            # 4. Submit time-off (write action)
            print("4. Submitting time-off request...")
            result = await session.call_tool("submit_time_off", {
                "employee_id": "E001", "start_date": "2026-04-14",
                "end_date": "2026-04-18", "reason": "Vacation",
            })
            parsed = json.loads(result.content[0].text)
            audit.record("client_to_server", "tools/call",
                         params={"arguments": {"employee_id": "E001", "start_date": "2026-04-14",
                                               "end_date": "2026-04-18", "reason": "Vacation"}},
                         tool_name="submit_time_off", result=parsed)
            print(f"   Status: {parsed['status']}, Request ID: {parsed['request_id']}\n")

            # 5. Compliance check
            print("5. Checking compliance rules for Ontario...")
            result = await session.call_tool("check_compliance", {"region": "CA-ON"})
            parsed = json.loads(result.content[0].text)
            audit.record("client_to_server", "tools/call",
                         params={"arguments": {"region": "CA-ON"}},
                         tool_name="check_compliance", result=parsed)
            print(f"   Min wage: ${parsed['min_wage']}, Overtime threshold: {parsed['overtime_threshold']}h\n")

            # 6. Cross-department pay access
            print("6. Accessing pay info for David Kim (different department)...")
            result = await session.call_tool("get_pay_info", {"employee_id": "E004"})
            parsed = json.loads(result.content[0].text)
            audit.record("client_to_server", "tools/call",
                         params={"arguments": {"employee_id": "E004"}},
                         tool_name="get_pay_info", result=parsed)
            print(f"   Salary: ${parsed['base_salary']:,}\n")

            # 7. Non-existent employee (error)
            print("7. Looking up non-existent employee E999...")
            result = await session.call_tool("get_employee_info", {"employee_id": "E999"})
            parsed = json.loads(result.content[0].text)
            audit.record("client_to_server", "tools/call",
                         params={"arguments": {"employee_id": "E999"}},
                         tool_name="get_employee_info", result=parsed,
                         error="Employee not found" if "error" in parsed else None)
            print(f"   Result: {parsed}\n")

            # 8-9. Carol Singh cross-department access
            print("8. Accessing Carol Singh (E003) employee info...")
            result = await session.call_tool("get_employee_info", {"employee_id": "E003"})
            parsed = json.loads(result.content[0].text)
            audit.record("client_to_server", "tools/call",
                         params={"arguments": {"employee_id": "E003"}},
                         tool_name="get_employee_info", result=parsed)
            print(f"   {parsed['name']}, {parsed['role']}\n")

            print("9. Accessing Carol Singh (E003) pay info...")
            result = await session.call_tool("get_pay_info", {"employee_id": "E003"})
            parsed = json.loads(result.content[0].text)
            audit.record("client_to_server", "tools/call",
                         params={"arguments": {"employee_id": "E003"}},
                         tool_name="get_pay_info", result=parsed)
            print(f"   Salary: ${parsed['base_salary']:,}\n")

    # Save
    print("\n" + "=" * 50)
    audit.save("audit_log.json")
    print("=" * 50)

    # Generate report automatically
    print("\nGenerating HTML report...")
    generate_report("audit_log.json", "audit_report.html")
    print("Done! Open audit_report.html in your browser.")


if __name__ == "__main__":
    asyncio.run(run_demo())
