"""
A2A Test Report Generation

Generate JSON and HTML reports from validation and test results.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tester import TestReport
    from .validator import ValidationReport


# ═══════════════════════════════════════════════════════════════════════════════
# JSON EXPORT
# ═══════════════════════════════════════════════════════════════════════════════


def export_json(
    report: TestReport | ValidationReport,
    path: str | Path | None = None,
    indent: int = 2,
) -> str:
    """
    Export a report to JSON.

    Args:
        report: TestReport or ValidationReport
        path: Optional file path to write to
        indent: JSON indentation

    Returns:
        JSON string
    """
    data = report.to_dict()
    data["exported_at"] = datetime.utcnow().isoformat() + "Z"

    json_str = json.dumps(data, indent=indent, default=str)

    if path:
        Path(path).write_text(json_str)

    return json_str


# ═══════════════════════════════════════════════════════════════════════════════
# HTML EXPORT
# ═══════════════════════════════════════════════════════════════════════════════


def _status_color(status: str) -> str:
    """Get color for status."""
    colors = {
        "passed": "#22c55e",
        "failed": "#ef4444",
        "warning": "#f59e0b",
        "skipped": "#6b7280",
    }
    return colors.get(status, "#6b7280")


def _status_icon(status: str) -> str:
    """Get icon for status."""
    icons = {
        "passed": "✓",
        "failed": "✗",
        "warning": "⚠",
        "skipped": "○",
    }
    return icons.get(status, "?")


def _severity_color(severity: str) -> str:
    """Get color for severity."""
    colors = {
        "error": "#ef4444",
        "warning": "#f59e0b",
        "info": "#3b82f6",
    }
    return colors.get(severity, "#6b7280")


def export_html_test_report(report: TestReport, path: str | Path | None = None) -> str:
    """
    Export a TestReport to HTML.

    Args:
        report: TestReport to export
        path: Optional file path to write to

    Returns:
        HTML string
    """
    # Build results HTML
    results_html = ""
    for r in report.results:
        color = _status_color(r.status.value)
        icon = _status_icon(r.status.value)
        results_html += f"""
        <div class="result" style="border-left: 3px solid {color};">
            <div class="result-header">
                <span class="status-icon" style="color: {color};">{icon}</span>
                <span class="test-name">{r.name}</span>
                <span class="duration">{r.duration_ms:.1f}ms</span>
            </div>
            <div class="result-message">{r.message}</div>
            {'<div class="result-error">Error: ' + r.error + '</div>' if r.error else ''}
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>A2Apex Test Report</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #1f2937;
            max-width: 800px;
            margin: 0 auto;
            padding: 2rem;
            background: #f9fafb;
        }}
        h1 {{ color: #111827; margin-bottom: 0.5rem; }}
        .subtitle {{ color: #6b7280; margin-bottom: 2rem; }}
        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        .summary-card {{
            background: white;
            padding: 1rem;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            text-align: center;
        }}
        .summary-card .value {{
            font-size: 2rem;
            font-weight: bold;
            color: #111827;
        }}
        .summary-card .label {{
            font-size: 0.875rem;
            color: #6b7280;
        }}
        .score {{ color: {_status_color('passed' if report.score >= 80 else ('warning' if report.score >= 50 else 'failed'))} !important; }}
        .results {{ display: flex; flex-direction: column; gap: 0.5rem; }}
        .result {{
            background: white;
            padding: 1rem;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .result-header {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            margin-bottom: 0.25rem;
        }}
        .status-icon {{ font-weight: bold; }}
        .test-name {{ font-weight: 600; flex-grow: 1; }}
        .duration {{ color: #6b7280; font-size: 0.875rem; }}
        .result-message {{ color: #4b5563; }}
        .result-error {{ color: #ef4444; font-size: 0.875rem; margin-top: 0.5rem; }}
        .footer {{
            margin-top: 2rem;
            padding-top: 1rem;
            border-top: 1px solid #e5e7eb;
            color: #9ca3af;
            font-size: 0.875rem;
            text-align: center;
        }}
    </style>
</head>
<body>
    <h1>🔬 A2Apex Test Report</h1>
    <p class="subtitle">{report.agent_url}</p>

    <div class="summary">
        <div class="summary-card">
            <div class="value score">{report.score:.0f}</div>
            <div class="label">Score</div>
        </div>
        <div class="summary-card">
            <div class="value" style="color: #22c55e;">{report.passed}</div>
            <div class="label">Passed</div>
        </div>
        <div class="summary-card">
            <div class="value" style="color: #ef4444;">{report.failed}</div>
            <div class="label">Failed</div>
        </div>
        <div class="summary-card">
            <div class="value" style="color: #f59e0b;">{report.warnings}</div>
            <div class="label">Warnings</div>
        </div>
        <div class="summary-card">
            <div class="value">{report.total_duration_ms:.0f}</div>
            <div class="label">Duration (ms)</div>
        </div>
    </div>

    <h2>Test Results</h2>
    <div class="results">
        {results_html}
    </div>

    <div class="footer">
        Generated by A2Apex • {report.timestamp}
    </div>
</body>
</html>"""

    if path:
        Path(path).write_text(html)

    return html


def export_html_validation_report(
    report: ValidationReport,
    path: str | Path | None = None,
) -> str:
    """
    Export a ValidationReport to HTML.

    Args:
        report: ValidationReport to export
        path: Optional file path to write to

    Returns:
        HTML string
    """
    # Build issues HTML
    issues_html = ""

    for section, issues, title in [
        ("errors", report.errors, "Errors"),
        ("warnings", report.warnings, "Warnings"),
        ("info", report.info, "Info"),
    ]:
        if issues:
            color = _severity_color(section.rstrip("s"))  # "errors" -> "error"
            issues_html += f'<h3 style="color: {color};">{title} ({len(issues)})</h3>'
            for issue in issues:
                issues_html += f"""
                <div class="issue" style="border-left: 3px solid {color};">
                    <div class="issue-field">{issue.field}</div>
                    <div class="issue-message">{issue.message}</div>
                    {'<div class="issue-suggestion">💡 ' + issue.suggestion + '</div>' if issue.suggestion else ''}
                </div>
                """

    status_text = "✓ Valid" if report.is_valid else "✗ Invalid"
    status_color = _status_color("passed" if report.is_valid else "failed")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>A2Apex Validation Report</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #1f2937;
            max-width: 800px;
            margin: 0 auto;
            padding: 2rem;
            background: #f9fafb;
        }}
        h1 {{ color: #111827; margin-bottom: 0.5rem; }}
        h3 {{ margin-top: 1.5rem; margin-bottom: 0.5rem; }}
        .status {{
            font-size: 1.25rem;
            font-weight: bold;
            color: {status_color};
            margin-bottom: 2rem;
        }}
        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        .summary-card {{
            background: white;
            padding: 1rem;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            text-align: center;
        }}
        .summary-card .value {{
            font-size: 2rem;
            font-weight: bold;
            color: #111827;
        }}
        .summary-card .label {{
            font-size: 0.875rem;
            color: #6b7280;
        }}
        .score {{ color: {_status_color('passed' if report.score >= 80 else ('warning' if report.score >= 50 else 'failed'))} !important; }}
        .issue {{
            background: white;
            padding: 1rem;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            margin-bottom: 0.5rem;
        }}
        .issue-field {{
            font-family: monospace;
            font-weight: 600;
            color: #374151;
        }}
        .issue-message {{ color: #4b5563; }}
        .issue-suggestion {{
            color: #059669;
            font-size: 0.875rem;
            margin-top: 0.5rem;
        }}
        .footer {{
            margin-top: 2rem;
            padding-top: 1rem;
            border-top: 1px solid #e5e7eb;
            color: #9ca3af;
            font-size: 0.875rem;
            text-align: center;
        }}
    </style>
</head>
<body>
    <h1>📋 A2Apex Validation Report</h1>
    <p class="status">{status_text}</p>

    <div class="summary">
        <div class="summary-card">
            <div class="value score">{report.score:.0f}</div>
            <div class="label">Score</div>
        </div>
        <div class="summary-card">
            <div class="value" style="color: #ef4444;">{report.error_count}</div>
            <div class="label">Errors</div>
        </div>
        <div class="summary-card">
            <div class="value" style="color: #f59e0b;">{report.warning_count}</div>
            <div class="label">Warnings</div>
        </div>
        <div class="summary-card">
            <div class="value" style="color: #3b82f6;">{report.info_count}</div>
            <div class="label">Info</div>
        </div>
    </div>

    {issues_html if issues_html else '<p style="color: #22c55e;">✓ No issues found!</p>'}

    <div class="footer">
        Generated by A2Apex • {datetime.utcnow().isoformat()}Z
    </div>
</body>
</html>"""

    if path:
        Path(path).write_text(html)

    return html


# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


def export_report(
    report: TestReport | ValidationReport,
    path: str | Path,
    format: str = "auto",
) -> str:
    """
    Export a report to file.

    Args:
        report: TestReport or ValidationReport
        path: File path (format auto-detected from extension if format='auto')
        format: 'json', 'html', or 'auto'

    Returns:
        The exported content
    """
    path = Path(path)

    if format == "auto":
        format = path.suffix.lstrip(".").lower()
        if format not in ("json", "html"):
            format = "json"

    if format == "json":
        return export_json(report, path)
    elif format == "html":
        # Detect report type
        from .tester import TestReport as TR
        from .validator import ValidationReport as VR

        if isinstance(report, TR):
            return export_html_test_report(report, path)
        elif isinstance(report, VR):
            return export_html_validation_report(report, path)
        else:
            # Fallback to JSON
            return export_json(report, path)
    else:
        raise ValueError(f"Unknown format: {format}")
