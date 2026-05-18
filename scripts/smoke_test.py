"""Smoke test — verifies DeepSeek LLM integration end-to-end.

Usage:
    python scripts/smoke_test.py
"""

import sys
from pathlib import Path

# Ensure project root is on path when run directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from email_agent.graph.builder import build_graph
from email_agent.graph.state import GraphState


CASES = [
    {
        "email_id": "smoke-001",
        "subject": "明天下午2点开会",
        "body": "请帮我在日历里创建一个明天下午2点的项目评审会议。",
        "sender": "boss@company.com",
        "expected": "create_calendar_event",
    },
    {
        "email_id": "smoke-002",
        "subject": "垃圾邮件",
        "body": "恭喜您中奖了！点击领取百万大奖。",
        "sender": "spam@unknown.com",
        "expected": "move_to_trash",
    },
    {
        "email_id": "smoke-003",
        "subject": "Re: 项目进展",
        "body": "请回复告知最新进展，谢谢。",
        "sender": "colleague@company.com",
        "expected": "reply",
    },
]


def main() -> None:
    print("=== EmailAgent Smoke Test ===\n")

    app = build_graph()
    passed = 0

    for case in CASES:
        state = GraphState(
            email_id=case["email_id"],
            message_id=case["email_id"],
            subject=case["subject"],
            body=case["body"],
            sender=case["sender"],
        )
        result = app.invoke(state)
        intents = result.get("intents", [])
        intent_names = [i.name if hasattr(i, "name") else i for i in intents]

        ok = case["expected"] in intent_names
        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1

        print(f"[{status}] {case['email_id']} — subject: {case['subject']}")
        print(f"       expected: {case['expected']}")
        print(f"       got:      {intent_names}")
        if result.get("error"):
            print(f"       error:    {result['error']}")
        print()

    total = len(CASES)
    print(f"Result: {passed}/{total} passed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
