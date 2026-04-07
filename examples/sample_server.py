"""
Sample MCP server with demo tools for testing the audit proxy.

Run standalone:
    python -m examples.sample_server

Or use with the audit proxy:
    mcp-audit-proxy --server "python -m examples.sample_server"
"""

import json
import random
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("sample-hr-server")

# Simulated data
EMPLOYEES = {
    "E001": {"name": "Alice Chen", "department": "Engineering", "role": "Senior Developer", "pto_balance": 12},
    "E002": {"name": "Bob Martinez", "department": "Product", "role": "Product Manager", "pto_balance": 8},
    "E003": {"name": "Carol Singh", "department": "Engineering", "role": "ML Engineer", "pto_balance": 15},
    "E004": {"name": "David Kim", "department": "Finance", "role": "Analyst", "pto_balance": 5},
}

PAY_INFO = {
    "E001": {"base_salary": 145000, "currency": "USD", "pay_frequency": "biweekly", "last_pay_date": "2026-03-28"},
    "E002": {"base_salary": 135000, "currency": "USD", "pay_frequency": "biweekly", "last_pay_date": "2026-03-28"},
    "E003": {"base_salary": 155000, "currency": "USD", "pay_frequency": "biweekly", "last_pay_date": "2026-03-28"},
    "E004": {"base_salary": 95000, "currency": "USD", "pay_frequency": "biweekly", "last_pay_date": "2026-03-28"},
}

COMPLIANCE_RULES = {
    "US-CA": {"min_wage": 16.00, "overtime_threshold": 8, "meal_break_required": True},
    "US-NY": {"min_wage": 15.00, "overtime_threshold": 8, "meal_break_required": True},
    "CA-ON": {"min_wage": 16.55, "overtime_threshold": 8.5, "meal_break_required": True},
}


@mcp.tool()
def get_employee_info(employee_id: str) -> str:
    """Look up an employee's basic information by their ID."""
    if employee_id not in EMPLOYEES:
        return json.dumps({"error": f"Employee {employee_id} not found"})
    return json.dumps({"employee_id": employee_id, **EMPLOYEES[employee_id]})


@mcp.tool()
def submit_time_off(employee_id: str, start_date: str, end_date: str, reason: str = "Personal") -> str:
    """Submit a time-off request for an employee."""
    if employee_id not in EMPLOYEES:
        return json.dumps({"error": f"Employee {employee_id} not found"})
    emp = EMPLOYEES[employee_id]
    if emp["pto_balance"] <= 0:
        return json.dumps({"status": "denied", "reason": "Insufficient PTO balance"})
    request_id = f"PTO-{random.randint(1000, 9999)}"
    return json.dumps({
        "status": "approved",
        "request_id": request_id,
        "employee": emp["name"],
        "start_date": start_date,
        "end_date": end_date,
        "reason": reason,
        "remaining_pto": emp["pto_balance"] - 1,
    })


@mcp.tool()
def get_pay_info(employee_id: str) -> str:
    """Retrieve pay information for an employee."""
    if employee_id not in PAY_INFO:
        return json.dumps({"error": f"Pay info for {employee_id} not found"})
    return json.dumps({"employee_id": employee_id, **PAY_INFO[employee_id]})


@mcp.tool()
def check_compliance(region: str) -> str:
    """Check labour compliance rules for a specific region."""
    if region not in COMPLIANCE_RULES:
        return json.dumps({"error": f"No compliance data for region: {region}"})
    return json.dumps({"region": region, **COMPLIANCE_RULES[region]})


@mcp.tool()
def search_employees(query: str) -> str:
    """Search employees by name or department."""
    results = []
    for emp_id, emp in EMPLOYEES.items():
        if query.lower() in emp["name"].lower() or query.lower() in emp["department"].lower():
            results.append({"employee_id": emp_id, **emp})
    return json.dumps({"query": query, "results": results, "count": len(results)})


if __name__ == "__main__":
    mcp.run(transport="stdio")
