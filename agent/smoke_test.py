"""Make one small live API call to verify Germinate's agent configuration."""
import json
from pathlib import Path

from agent.client import OpenAIAgent

ROOT = Path(__file__).resolve().parents[1]


def main():
    config = json.loads((ROOT / "config" / "agent.json").read_text(encoding="utf-8-sig"))
    answer = OpenAIAgent(config).analyze(
        source="Germinate smoke test",
        url="https://example.org/test-grant",
        page_text=(
            "Non-repayable grants are available to local nonprofit organizations for "
            "wetland and ecosystem restoration. Applications close 30 November 2026."
        ),
        preliminary={"decision": "candidate", "score": 5},
    )
    print(json.dumps(answer, indent=2, ensure_ascii=False))
    if answer["grant_status"] != "confirmed" or answer["decision"] != "accept":
        raise SystemExit("Agent responded, but did not accept the clear grant example.")
    print("Agent smoke test passed.")


if __name__ == "__main__":
    main()
