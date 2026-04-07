"""
Generate a visual HTML audit trail report from an MCP audit log.
"""

import json
import html as html_mod
from pathlib import Path


# Default classification sets — users can override via arguments.
DEFAULT_SENSITIVE_TOOLS = {"get_pay_info", "get_employee_info", "submit_time_off"}
DEFAULT_WRITE_TOOLS = {"submit_time_off"}


def classify_event(event, *, sensitive_tools=None, write_tools=None):
    """Return a list of ``(flag_type, label)`` tuples for an event."""
    sensitive_tools = sensitive_tools or DEFAULT_SENSITIVE_TOOLS
    write_tools = write_tools or DEFAULT_WRITE_TOOLS

    flags = []
    tool = event.get("tool_name", "")

    if tool in write_tools:
        flags.append(("action", "Write Action"))
    if tool in sensitive_tools:
        flags.append(("sensitive", "Sensitive Data"))
    if event.get("has_error"):
        flags.append(("error", "Error"))

    data = event.get("data_accessed", [])
    for d in data:
        if d.get("field") == "employee_id":
            flags.append(("data-access", f"Accessed: {d['value']}"))

    return flags


def generate_report(
    input_path="audit_log.json",
    output_path="audit_report.html",
    *,
    sensitive_tools=None,
    write_tools=None,
):
    """Generate an HTML audit report from a JSON audit log.

    Args:
        input_path: Path to the audit log JSON file.
        output_path: Where to write the HTML report. Pass ``None`` to
            return the HTML string without writing to disk.
        sensitive_tools: Set of tool names to flag as sensitive.
        write_tools: Set of tool names to flag as write actions.

    Returns:
        The generated HTML string.
    """
    sensitive_tools = sensitive_tools or DEFAULT_SENSITIVE_TOOLS
    write_tools = write_tools or DEFAULT_WRITE_TOOLS

    with open(input_path) as f:
        audit_data = json.load(f)

    report_html = _render_html(
        audit_data,
        sensitive_tools=sensitive_tools,
        write_tools=write_tools,
    )

    if output_path is not None:
        Path(output_path).write_text(report_html)

    return report_html


# ---------------------------------------------------------------------------
# Internal rendering
# ---------------------------------------------------------------------------

def _render_html(audit_data, *, sensitive_tools, write_tools):
    summary = audit_data.get("summary", {})
    events = audit_data.get("events", [])
    tool_events = [e for e in events if e.get("method") == "tools/call"]

    # Entity access timeline
    entity_timeline = {}
    for e in tool_events:
        for da in e.get("data_accessed", []):
            entity = da["value"]
            if entity not in entity_timeline:
                entity_timeline[entity] = []
            entity_timeline[entity].append({
                "tool": e.get("tool_name"),
                "time": e.get("elapsed_seconds"),
                "flags": classify_event(
                    e, sensitive_tools=sensitive_tools, write_tools=write_tools
                ),
            })

    # Event rows
    event_rows = []
    for i, e in enumerate(tool_events):
        flags = classify_event(
            e, sensitive_tools=sensitive_tools, write_tools=write_tools
        )
        flag_badges = ""
        for flag_type, flag_label in flags:
            flag_badges += (
                f'<span class="badge badge-{flag_type}">'
                f"{html_mod.escape(flag_label)}</span> "
            )

        args_str = html_mod.escape(
            json.dumps(e.get("params", {}).get("arguments", {}), indent=2)
        )
        result_str = html_mod.escape(
            json.dumps(e.get("tool_result", {}), indent=2)
        )

        row_class = ""
        if any(f[0] == "error" for f in flags):
            row_class = "row-error"
        elif any(f[0] == "action" for f in flags):
            row_class = "row-action"
        elif any(f[0] == "sensitive" for f in flags):
            row_class = "row-sensitive"

        event_rows.append(f"""
        <div class="event-card {row_class}" onclick="toggleDetail(this)">
            <div class="event-header">
                <div class="event-index">#{i + 1}</div>
                <div class="event-info">
                    <div class="event-tool">{html_mod.escape(e.get("tool_name", "unknown"))}</div>
                    <div class="event-time">{e.get("elapsed_seconds", 0)}s</div>
                </div>
                <div class="event-flags">{flag_badges}</div>
            </div>
            <div class="event-detail" style="display: none;">
                <div class="detail-section">
                    <div class="detail-label">Arguments</div>
                    <pre class="detail-content">{args_str}</pre>
                </div>
                <div class="detail-section">
                    <div class="detail-label">Result</div>
                    <pre class="detail-content">{result_str}</pre>
                </div>
            </div>
        </div>
        """)

    # Tool usage breakdown
    tool_usage_items = ""
    for tool, count in summary.get("tools_used", {}).items():
        is_write = tool in write_tools
        is_sensitive = tool in sensitive_tools
        if is_write:
            indicator = '<span class="tool-indicator write">WRITE</span>'
        elif is_sensitive:
            indicator = '<span class="tool-indicator sensitive">SENSITIVE</span>'
        else:
            indicator = '<span class="tool-indicator read">READ</span>'
        tool_usage_items += f"""
        <div class="tool-usage-item">
            <span class="tool-name">{html_mod.escape(tool)}</span>
            {indicator}
            <span class="tool-count">{count}x</span>
        </div>
        """

    # Entity access map
    entity_items = ""
    for entity, accesses in entity_timeline.items():
        tools_list = ", ".join(set(a["tool"] for a in accesses))
        entity_items += f"""
        <div class="entity-item">
            <span class="entity-id">{html_mod.escape(entity)}</span>
            <span class="entity-tools">{html_mod.escape(tools_list)}</span>
            <span class="entity-count">{len(accesses)} calls</span>
        </div>
        """

    return _HTML_TEMPLATE.format(
        session_id=html_mod.escape(audit_data.get("session_id", "")),
        start_time=html_mod.escape(audit_data.get("start_time", "")),
        duration=summary.get("duration_seconds", audit_data.get("duration_seconds", 0)),
        total_tool_calls=summary.get("total_tool_calls", 0),
        tools_used_count=len(summary.get("tools_used", {})),
        data_entities_count=len(summary.get("unique_data_entities_accessed", [])),
        errors=summary.get("errors", 0),
        error_class="error" if summary.get("errors", 0) > 0 else "normal",
        tool_usage_items=tool_usage_items,
        entity_items=entity_items
        or '<div style="color: var(--text-muted); font-size: 14px;">No data entities tracked in this session.</div>',
        event_rows="".join(event_rows),
    )


# ---------------------------------------------------------------------------
# HTML template — kept as a constant to keep the renderer readable.
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MCP Audit Trail Report</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=DM+Sans:wght@400;500;600;700&display=swap');

        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        :root {{
            --bg: #0a0a0b;
            --surface: #141416;
            --surface-2: #1c1c20;
            --border: #2a2a30;
            --text: #e4e4e7;
            --text-muted: #71717a;
            --accent: #3b82f6;
            --red: #ef4444;
            --amber: #f59e0b;
            --green: #22c55e;
            --purple: #a855f7;
        }}

        body {{
            font-family: 'DM Sans', -apple-system, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
            padding: 0;
        }}

        .container {{
            max-width: 960px;
            margin: 0 auto;
            padding: 48px 24px;
        }}

        .header {{
            margin-bottom: 48px;
        }}

        .header h1 {{
            font-size: 28px;
            font-weight: 700;
            letter-spacing: -0.5px;
            margin-bottom: 8px;
        }}

        .header .session-info {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 13px;
            color: var(--text-muted);
        }}

        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
            margin-bottom: 40px;
        }}

        .summary-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
        }}

        .summary-card .label {{
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: var(--text-muted);
            margin-bottom: 8px;
        }}

        .summary-card .value {{
            font-size: 32px;
            font-weight: 700;
            font-family: 'JetBrains Mono', monospace;
        }}

        .summary-card .value.error {{ color: var(--red); }}
        .summary-card .value.normal {{ color: var(--text); }}

        .section {{
            margin-bottom: 40px;
        }}

        .section-title {{
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 16px;
            padding-bottom: 8px;
            border-bottom: 1px solid var(--border);
        }}

        .tool-usage-item {{
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 10px 0;
            border-bottom: 1px solid var(--border);
            font-family: 'JetBrains Mono', monospace;
            font-size: 14px;
        }}

        .tool-name {{
            flex: 1;
        }}

        .tool-indicator {{
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 0.5px;
            padding: 2px 8px;
            border-radius: 4px;
        }}

        .tool-indicator.read {{ background: #1e3a5f; color: #60a5fa; }}
        .tool-indicator.sensitive {{ background: #3b1f0b; color: #fb923c; }}
        .tool-indicator.write {{ background: #3b0f0f; color: #f87171; }}

        .tool-count {{
            color: var(--text-muted);
            min-width: 30px;
            text-align: right;
        }}

        .entity-item {{
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 10px 0;
            border-bottom: 1px solid var(--border);
            font-size: 14px;
        }}

        .entity-id {{
            font-family: 'JetBrains Mono', monospace;
            font-weight: 600;
            min-width: 60px;
        }}

        .entity-tools {{
            flex: 1;
            color: var(--text-muted);
            font-size: 13px;
        }}

        .entity-count {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 13px;
            color: var(--text-muted);
        }}

        .event-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 10px;
            margin-bottom: 8px;
            cursor: pointer;
            transition: border-color 0.15s;
        }}

        .event-card:hover {{
            border-color: #3a3a42;
        }}

        .event-card.row-error {{ border-left: 3px solid var(--red); }}
        .event-card.row-action {{ border-left: 3px solid var(--amber); }}
        .event-card.row-sensitive {{ border-left: 3px solid var(--purple); }}

        .event-header {{
            display: flex;
            align-items: center;
            gap: 16px;
            padding: 14px 20px;
        }}

        .event-index {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
            color: var(--text-muted);
            min-width: 28px;
        }}

        .event-info {{
            flex: 1;
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        .event-tool {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 14px;
            font-weight: 500;
        }}

        .event-time {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
            color: var(--text-muted);
        }}

        .event-flags {{
            display: flex;
            gap: 6px;
            flex-wrap: wrap;
        }}

        .badge {{
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 0.3px;
            padding: 3px 8px;
            border-radius: 4px;
            white-space: nowrap;
        }}

        .badge-error {{ background: #3b0f0f; color: #f87171; }}
        .badge-action {{ background: #3b2f0f; color: #fbbf24; }}
        .badge-sensitive {{ background: #2d1b4e; color: #c084fc; }}
        .badge-data-access {{ background: #0f2b1e; color: #4ade80; }}

        .event-detail {{
            padding: 0 20px 16px 64px;
        }}

        .detail-section {{
            margin-bottom: 12px;
        }}

        .detail-label {{
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: var(--text-muted);
            margin-bottom: 4px;
        }}

        .detail-content {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
            background: var(--bg);
            padding: 12px;
            border-radius: 6px;
            overflow-x: auto;
            color: #a1a1aa;
            line-height: 1.5;
        }}

        .footer {{
            margin-top: 48px;
            padding-top: 24px;
            border-top: 1px solid var(--border);
            font-size: 13px;
            color: var(--text-muted);
            text-align: center;
        }}

        .footer a {{
            color: var(--accent);
            text-decoration: none;
        }}

        @media (max-width: 640px) {{
            .summary-grid {{ grid-template-columns: repeat(2, 1fr); }}
            .event-header {{ flex-wrap: wrap; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>MCP Audit Trail</h1>
            <div class="session-info">
                Session {session_id} &middot;
                {start_time} &middot;
                {duration}s duration
            </div>
        </div>

        <div class="summary-grid">
            <div class="summary-card">
                <div class="label">Tool Calls</div>
                <div class="value normal">{total_tool_calls}</div>
            </div>
            <div class="summary-card">
                <div class="label">Tools Used</div>
                <div class="value normal">{tools_used_count}</div>
            </div>
            <div class="summary-card">
                <div class="label">Data Entities</div>
                <div class="value normal">{data_entities_count}</div>
            </div>
            <div class="summary-card">
                <div class="label">Errors</div>
                <div class="value {error_class}">{errors}</div>
            </div>
        </div>

        <div class="section">
            <div class="section-title">Tools Used</div>
            {tool_usage_items}
        </div>

        <div class="section">
            <div class="section-title">Data Access Map</div>
            {entity_items}
        </div>

        <div class="section">
            <div class="section-title">Event Timeline</div>
            {event_rows}
        </div>

        <div class="footer">
            Generated by <a href="https://github.com/khushidahi/mcp-audit-trail">mcp-audit-trail</a>
        </div>
    </div>

    <script>
        function toggleDetail(card) {{
            const detail = card.querySelector('.event-detail');
            if (detail) {{
                detail.style.display = detail.style.display === 'none' ? 'block' : 'none';
            }}
        }}
    </script>
</body>
</html>"""
