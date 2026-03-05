"""
Evaluation Runner — tests tools and optionally the full agent against golden cases.

Usage:
    python tests/run_evals.py              # Tool-level tests only (no LLM needed)
    python tests/run_evals.py --agent      # Include agent-level tests (needs Ollama)
"""

import argparse
import json
import os
import sys
import tempfile

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.golden_evals import GOLDEN_CASES
from framework.tools.email_parser import parse_aws_alert_email
from framework.tools.service_registry import fetch_service_info, _load_registry, lookup_by_alarm
from framework.memory import Memory


# ── Test Helpers ──────────────────────────────────────────────────────────

class EvalResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = 0
        self.failed = 0
        self.errors: list[str] = []

    def check(self, condition: bool, message: str):
        if condition:
            self.passed += 1
        else:
            self.failed += 1
            self.errors.append(message)

    @property
    def ok(self) -> bool:
        return self.failed == 0

    def __str__(self):
        status = "✅ PASS" if self.ok else "❌ FAIL"
        s = f"{status} {self.name} ({self.passed} passed, {self.failed} failed)"
        for err in self.errors:
            s += f"\n    ⚠ {err}"
        return s


# ── Tool-Level Tests ──────────────────────────────────────────────────────

def test_email_parser(case: dict) -> EvalResult:
    """Test the email parser tool against a golden case."""
    result = EvalResult(f"email_parser: {case['name']}")

    raw_body = case["input_email"]["body"]
    output = parse_aws_alert_email.invoke({"raw_email_body": raw_body})
    parsed = json.loads(output)

    if "expected_alarm_name" in case:
        result.check(
            parsed.get("alarm_name", "").lower() == case["expected_alarm_name"].lower(),
            f"alarm_name: expected '{case['expected_alarm_name']}', got '{parsed.get('alarm_name', '')}'",
        )

    if "expected_state" in case:
        result.check(
            parsed.get("new_state", "").upper() == case["expected_state"].upper(),
            f"new_state: expected '{case['expected_state']}', got '{parsed.get('new_state', '')}'",
        )

    return result


def test_service_registry(case: dict) -> EvalResult:
    """Test the service registry lookup against a golden case."""
    result = EvalResult(f"service_registry: {case['name']}")

    alarm_name = case.get("expected_alarm_name", "")
    if not alarm_name:
        result.check(True, "No alarm name to test")
        return result

    output = fetch_service_info.invoke({"alarm_name_or_service": alarm_name})
    parsed = json.loads(output)

    if "expected_log_group" in case:
        log_groups = parsed.get("log_groups", [])
        result.check(
            case["expected_log_group"] in log_groups,
            f"log_group: expected '{case['expected_log_group']}' in {log_groups}",
        )

    if "expected_owner_team" in case:
        result.check(
            parsed.get("owner_team", "") == case["expected_owner_team"],
            f"owner_team: expected '{case['expected_owner_team']}', got '{parsed.get('owner_team', '')}'",
        )

    return result


def test_memory_corrections() -> EvalResult:
    """Test the memory correction system."""
    result = EvalResult("memory_corrections")

    # Use a temp file
    tmp_path = os.path.join(tempfile.gettempdir(), "test_corrections_memory.json")
    mem = Memory(filepath=tmp_path)
    mem.clear()

    # Store a correction
    mem.add_correction("test-alarm", "This alarm is caused by batch jobs at 4 AM")
    result.check(
        len(mem.get_corrections("test-alarm")) == 1,
        "Should have 1 correction after add_correction",
    )

    # Verify correction content
    corrections = mem.get_corrections("test-alarm")
    result.check(
        "batch jobs" in corrections[0]["correction"],
        "Correction should contain 'batch jobs'",
    )

    # Verify it appears in context summary
    summary = mem.get_context_summary()
    result.check(
        "batch jobs" in summary.lower(),
        "Context summary should include corrections",
    )

    # Verify all corrections
    all_corr = mem.get_all_corrections()
    result.check(
        "test-alarm" in all_corr,
        "get_all_corrections should include 'test-alarm'",
    )

    # Verify case-insensitive lookup
    mem.add_correction("TEST-ALARM", "Second correction")
    result.check(
        len(mem.get_corrections("test-alarm")) == 2,
        "Corrections should be case-insensitive",
    )

    # Cleanup
    mem.clear()
    try:
        os.remove(tmp_path)
    except OSError:
        pass

    return result


def test_teams_notifier_payload() -> EvalResult:
    """Test that the Teams notifier builds a valid Adaptive Card payload."""
    result = EvalResult("teams_notifier_payload")

    from framework.tools.teams_notifier import _build_adaptive_card

    card = _build_adaptive_card(
        alarm_name="test-alarm",
        summary="Test summary of investigation",
        severity="High",
        owner_team="test-team",
        log_group="/test/log/group",
    )

    result.check(
        card.get("type") == "message",
        "Card should have type 'message'",
    )
    result.check(
        len(card.get("attachments", [])) == 1,
        "Card should have exactly 1 attachment",
    )

    content = card["attachments"][0].get("content", {})
    result.check(
        content.get("type") == "AdaptiveCard",
        "Attachment content should be an AdaptiveCard",
    )
    result.check(
        len(content.get("body", [])) > 0,
        "Card body should have elements",
    )

    return result


# ── Main ──────────────────────────────────────────────────────────────────

def run_tool_evals() -> list[EvalResult]:
    """Run all tool-level evaluations."""
    results = []

    print("=" * 60)
    print("TOOL-LEVEL EVALUATIONS")
    print("=" * 60)

    # Email parser tests
    for case in GOLDEN_CASES:
        r = test_email_parser(case)
        results.append(r)
        print(r)

    # Service registry tests
    _load_registry()  # ensure loaded
    for case in GOLDEN_CASES:
        r = test_service_registry(case)
        results.append(r)
        print(r)

    # Memory corrections test
    r = test_memory_corrections()
    results.append(r)
    print(r)

    # Teams notifier payload test
    r = test_teams_notifier_payload()
    results.append(r)
    print(r)

    return results


def run_agent_evals() -> list[EvalResult]:
    """Run agent-level evaluations (requires Ollama)."""
    results = []

    print("\n" + "=" * 60)
    print("AGENT-LEVEL EVALUATIONS (requires Ollama)")
    print("=" * 60)

    try:
        from framework.config import Config
        from framework.agent import Agent
        from framework.events.base import Event

        from framework.tools.service_registry import fetch_service_info
        from framework.tools.teams_notifier import notify_teams

        config = Config()
        mem = Memory(filepath=os.path.join(tempfile.gettempdir(), "test_agent_memory.json"))
        mem.clear()

        all_tools = [parse_aws_alert_email, fetch_service_info, notify_teams]

        # Import cloudwatch fetcher but don't require AWS
        try:
            from framework.tools.cloudwatch_fetcher import fetch_cloudwatch_logs
            all_tools.append(fetch_cloudwatch_logs)
        except Exception:
            print("  ⚠ CloudWatch fetcher not available, skipping")

        agent = Agent(config=config, tools=all_tools, memory=mem)

        for case in GOLDEN_CASES:
            r = EvalResult(f"agent: {case['name']}")

            event = Event(
                source="email",
                event_type="aws_alarm",
                payload=case["input_email"],
            )

            try:
                response = agent.process_event(event)

                # Check keywords in response
                for keyword in case.get("expected_summary_keywords", []):
                    r.check(
                        keyword.lower() in response.lower(),
                        f"Response should contain '{keyword}'",
                    )

                r.check(
                    len(response) > 50,
                    f"Response should be substantial (got {len(response)} chars)",
                )

            except Exception as e:
                r.check(False, f"Agent raised exception: {e}")

            results.append(r)
            print(r)

        mem.clear()

    except Exception as e:
        r = EvalResult("agent_setup")
        r.check(False, f"Could not initialize agent: {e}")
        results.append(r)
        print(r)

    return results


def main():
    parser = argparse.ArgumentParser(description="Run evaluations for AWS Alert Bot")
    parser.add_argument("--agent", action="store_true", help="Include agent-level evals (needs Ollama)")
    args = parser.parse_args()

    all_results = run_tool_evals()

    if args.agent:
        all_results += run_agent_evals()

    # Summary
    print("\n" + "=" * 60)
    total_passed = sum(r.passed for r in all_results)
    total_failed = sum(r.failed for r in all_results)
    total = total_passed + total_failed

    if total_failed == 0:
        print(f"✅ ALL EVALUATIONS PASSED ({total_passed}/{total} checks)")
    else:
        print(f"❌ {total_failed} FAILURES out of {total} checks")
        for r in all_results:
            if not r.ok:
                print(f"  ⚠ {r.name}: {r.failed} failed")

    print("=" * 60)
    sys.exit(0 if total_failed == 0 else 1)


if __name__ == "__main__":
    main()
