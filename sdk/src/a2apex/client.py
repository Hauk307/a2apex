"""
A2Apex Client - Main Entry Point

The A2ApexClient provides a unified interface for validating and testing
A2A protocol implementations.

Example:
    from a2apex import A2ApexClient

    client = A2ApexClient()

    # Validate an Agent Card
    report = client.validate_card("https://agent.example.com")
    print(f"Score: {report.score}/100")

    # Run full test suite
    results = client.test_agent("https://agent.example.com")
    for test in results:
        print(f"{'✅' if test.passed else '❌'} {test.name}: {test.message}")
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import httpx

from .tester import LiveTester, TestReport, TestResult
from .validator import AgentCardValidator, ValidationReport

if TYPE_CHECKING:
    pass


class A2ApexClient:
    """
    Main A2Apex client for validating and testing A2A agents.

    Provides both sync and async interfaces.
    """

    def __init__(
        self,
        timeout: float = 30.0,
        auth_header: str | None = None,
    ) -> None:
        """
        Initialize the client.

        Args:
            timeout: Default request timeout in seconds
            auth_header: Default Authorization header value
        """
        self.timeout = timeout
        self.auth_header = auth_header
        self._validator = AgentCardValidator()

    # ═══════════════════════════════════════════════════════════════════════════
    # SYNC API
    # ═══════════════════════════════════════════════════════════════════════════

    def validate_card(self, url_or_dict: str | dict) -> ValidationReport:
        """
        Validate an Agent Card.

        Can accept either a URL (will fetch the Agent Card) or a dict.

        Args:
            url_or_dict: URL to agent or Agent Card dict

        Returns:
            ValidationReport with score, errors, warnings

        Example:
            report = client.validate_card("https://agent.example.com")
            print(f"Score: {report.score}/100")
            print(f"Errors: {report.error_count}")
        """
        if isinstance(url_or_dict, str):
            # Fetch Agent Card from URL
            card = self._fetch_agent_card_sync(url_or_dict)
        else:
            card = url_or_dict

        return self._validator.validate(card)

    def validate_card_dict(self, card: dict) -> ValidationReport:
        """
        Validate an Agent Card dict directly (no HTTP request).

        Args:
            card: Agent Card as dictionary

        Returns:
            ValidationReport
        """
        return self._validator.validate(card)

    def test_agent(
        self,
        url: str,
        auth_header: str | None = None,
        timeout: float | None = None,
    ) -> TestReport:
        """
        Run the full test suite against an A2A agent.

        Args:
            url: Base URL of the agent
            auth_header: Optional Authorization header (overrides default)
            timeout: Request timeout (overrides default)

        Returns:
            TestReport with all test results

        Example:
            results = client.test_agent("https://agent.example.com")
            print(f"Score: {results.score}/100")
            for test in results:
                status = "✅" if test.passed else "❌"
                print(f"{status} {test.name}: {test.message}")
        """
        return asyncio.get_event_loop().run_until_complete(
            self.atest_agent(url, auth_header, timeout)
        )

    def _fetch_agent_card_sync(self, url: str) -> dict:
        """Fetch Agent Card synchronously."""
        card_url = url.rstrip("/")
        if not card_url.endswith("/.well-known/agent-card.json"):
            card_url = f"{card_url}/.well-known/agent-card.json"

        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            response = client.get(card_url)
            response.raise_for_status()
            return response.json()

    # ═══════════════════════════════════════════════════════════════════════════
    # ASYNC API
    # ═══════════════════════════════════════════════════════════════════════════

    async def avalidate_card(self, url_or_dict: str | dict) -> ValidationReport:
        """
        Validate an Agent Card (async version).

        Args:
            url_or_dict: URL to agent or Agent Card dict

        Returns:
            ValidationReport
        """
        if isinstance(url_or_dict, str):
            card = await self._fetch_agent_card_async(url_or_dict)
        else:
            card = url_or_dict

        return self._validator.validate(card)

    async def atest_agent(
        self,
        url: str,
        auth_header: str | None = None,
        timeout: float | None = None,
    ) -> TestReport:
        """
        Run the full test suite against an A2A agent (async version).

        Args:
            url: Base URL of the agent
            auth_header: Optional Authorization header
            timeout: Request timeout

        Returns:
            TestReport with all test results
        """
        tester = LiveTester(
            base_url=url,
            auth_header=auth_header or self.auth_header,
            timeout=timeout or self.timeout,
        )
        return await tester.run_all_tests()

    async def atest_agent_card_fetch(self, url: str) -> TestResult:
        """
        Quick test: just fetch and validate the Agent Card (async).

        Args:
            url: Base URL of the agent

        Returns:
            TestResult
        """
        tester = LiveTester(url, timeout=self.timeout)
        return await tester.test_agent_card_fetch()

    async def atest_message_send(
        self,
        url: str,
        message: str = "Hello! This is a test from A2Apex.",
        auth_header: str | None = None,
    ) -> TestResult:
        """
        Quick test: send a message (async).

        Args:
            url: Base URL of the agent
            message: Message text to send
            auth_header: Optional Authorization header

        Returns:
            TestResult
        """
        tester = LiveTester(url, auth_header or self.auth_header, self.timeout)
        await tester.test_agent_card_fetch()
        return await tester.test_message_send(message)

    async def _fetch_agent_card_async(self, url: str) -> dict:
        """Fetch Agent Card asynchronously."""
        card_url = url.rstrip("/")
        if not card_url.endswith("/.well-known/agent-card.json"):
            card_url = f"{card_url}/.well-known/agent-card.json"

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.get(card_url)
            response.raise_for_status()
            return response.json()

    # ═══════════════════════════════════════════════════════════════════════════
    # UTILITY METHODS
    # ═══════════════════════════════════════════════════════════════════════════

    def validate_json_string(self, json_string: str) -> ValidationReport:
        """
        Validate an Agent Card from a JSON string.

        Args:
            json_string: Agent Card as JSON string

        Returns:
            ValidationReport
        """
        card = json.loads(json_string)
        return self._validator.validate(card)


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE-LEVEL CONVENIENCE
# ═══════════════════════════════════════════════════════════════════════════════

_default_client: A2ApexClient | None = None


def get_client() -> A2ApexClient:
    """Get or create the default client."""
    global _default_client
    if _default_client is None:
        _default_client = A2ApexClient()
    return _default_client


def validate_card(url_or_dict: str | dict) -> ValidationReport:
    """
    Validate an Agent Card using the default client.

    Args:
        url_or_dict: URL to agent or Agent Card dict

    Returns:
        ValidationReport

    Example:
        from a2apex import validate_card
        report = validate_card("https://agent.example.com")
    """
    return get_client().validate_card(url_or_dict)


def test_agent(url: str) -> TestReport:
    """
    Test an agent using the default client.

    Args:
        url: Base URL of the agent

    Returns:
        TestReport

    Example:
        from a2apex import test_agent
        results = test_agent("https://agent.example.com")
    """
    return get_client().test_agent(url)
