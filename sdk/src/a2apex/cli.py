"""
A2Apex CLI

Basic command-line interface for validating and testing A2A agents.

Usage:
    a2apex validate https://agent.example.com
    a2apex test https://agent.example.com
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from .client import A2ApexClient
from .report import export_report


def _print_validation_report(report):
    """Print validation report to console."""
    status = "✓ Valid" if report.is_valid else "✗ Invalid"
    color_code = "\033[32m" if report.is_valid else "\033[31m"
    reset = "\033[0m"

    print(f"\n{color_code}{status}{reset} (Score: {report.score:.0f}/100)")
    print(f"  Errors: {report.error_count}, Warnings: {report.warning_count}\n")

    if report.errors:
        print("\033[31mErrors:\033[0m")
        for e in report.errors:
            print(f"  ✗ {e.field}: {e.message}")
            if e.suggestion:
                print(f"    💡 {e.suggestion}")
        print()

    if report.warnings:
        print("\033[33mWarnings:\033[0m")
        for w in report.warnings[:5]:  # Show first 5
            print(f"  ⚠ {w.field}: {w.message}")
        if len(report.warnings) > 5:
            print(f"  ... and {len(report.warnings) - 5} more")
        print()


def _print_test_report(report):
    """Print test report to console."""
    print(f"\n🔬 A2Apex Test Results")
    print(f"   URL: {report.agent_url}")
    print(f"   Score: {report.score:.0f}/100")
    print(f"   Passed: {report.passed}/{report.total_tests}")
    print(f"   Duration: {report.total_duration_ms:.0f}ms\n")

    for test in report.results:
        if test.status.value == "passed":
            icon = "\033[32m✓\033[0m"
        elif test.status.value == "failed":
            icon = "\033[31m✗\033[0m"
        elif test.status.value == "warning":
            icon = "\033[33m⚠\033[0m"
        else:
            icon = "○"

        print(f"  {icon} {test.name}: {test.message}")
        if test.error:
            print(f"      Error: {test.error}")

    print()


def cmd_validate(args):
    """Run validation command."""
    client = A2ApexClient(timeout=args.timeout)

    try:
        report = client.validate_card(args.url)
    except Exception as e:
        print(f"\033[31mError: {e}\033[0m", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    elif args.output:
        export_report(report, args.output)
        print(f"Report saved to {args.output}")
    else:
        _print_validation_report(report)

    sys.exit(0 if report.is_valid else 1)


def cmd_test(args):
    """Run test command."""
    client = A2ApexClient(
        timeout=args.timeout,
        auth_header=args.auth,
    )

    try:
        report = asyncio.get_event_loop().run_until_complete(
            client.atest_agent(args.url)
        )
    except Exception as e:
        print(f"\033[31mError: {e}\033[0m", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    elif args.output:
        export_report(report, args.output)
        print(f"Report saved to {args.output}")
    else:
        _print_test_report(report)

    # Exit with failure if score below threshold
    if report.score < args.min_score:
        sys.exit(1)
    sys.exit(0)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="a2apex",
        description="Test, validate, and certify A2A protocol implementations",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Validate command
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate an Agent Card",
    )
    validate_parser.add_argument("url", help="URL of the agent")
    validate_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    validate_parser.add_argument(
        "--output", "-o",
        help="Save report to file (JSON or HTML)",
    )
    validate_parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Request timeout in seconds",
    )
    validate_parser.set_defaults(func=cmd_validate)

    # Test command
    test_parser = subparsers.add_parser(
        "test",
        help="Run the full test suite against an agent",
    )
    test_parser.add_argument("url", help="URL of the agent")
    test_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    test_parser.add_argument(
        "--output", "-o",
        help="Save report to file (JSON or HTML)",
    )
    test_parser.add_argument(
        "--auth",
        help="Authorization header value",
    )
    test_parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Request timeout in seconds",
    )
    test_parser.add_argument(
        "--min-score",
        type=float,
        default=0,
        help="Minimum score to pass (0-100)",
    )
    test_parser.set_defaults(func=cmd_test)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
