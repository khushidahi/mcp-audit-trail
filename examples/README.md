# Examples

This directory contains a sample MCP server and a demo runner to show `mcp-audit-trail` in action.

## Prerequisites

```bash
pip install mcp-audit-trail[demo]
# or, from the repo root:
pip install -e ".[demo]"
```

## Run the demo

```bash
python -m examples.run_demo
```

This will:
1. Start the sample HR server
2. Make 9 tool calls (employee lookups, pay info, time-off request, compliance check, and a deliberate error)
3. Save `audit_log.json`
4. Generate `audit_report.html`

Open `audit_report.html` in your browser to explore the visual audit trail.

## Use the proxy with the sample server

```bash
mcp-audit-proxy --server "python examples/sample_server.py" --log my_audit.json
```
