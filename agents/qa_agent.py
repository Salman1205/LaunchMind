import json
import requests
from message_bus import MessageBus
from llm_client import call_llm
from config import GITHUB_TOKEN, GITHUB_REPO

GITHUB_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}

QA_SYSTEM_PROMPT = """You are a QA reviewer for a software startup. Review the HTML landing page and marketing copy.

Return a JSON object with exactly these fields:
- html_verdict: "pass" or "fail"
- html_issues: array of specific issues found in the HTML (always include at least 2 items)
- copy_verdict: "pass" or "fail"
- copy_issues: array of specific issues in the marketing copy (at least 1 item)
- overall_verdict: "pass" or "fail" (fail if either html or copy fails)

Be specific. Reference the value proposition when checking consistency.
Respond with ONLY valid JSON."""


class QAAgent:
    def __init__(self, bus: MessageBus):
        self.bus = bus

    def run(self) -> None:
        messages = self.bus.receive("qa")
        for msg in messages:
            if msg["message_type"] != "task":
                continue
            print(f"\n[QA] Running review...")
            payload = msg["payload"]
            html = payload["html_content"]
            copy = payload["copy"]
            spec = payload["product_spec"]
            pr_url = payload["pr_url"]

            report = self._review(html, copy, spec)
            self._post_pr_comments(pr_url, report)

            print(f"[QA] Overall verdict: {report['overall_verdict']}")
            self.bus.send(
                from_agent="qa",
                to_agent="ceo",
                message_type="result",
                payload={"review_report": report},
                parent_message_id=msg["message_id"],
            )

    def _review(self, html: str, copy: dict, spec: dict) -> dict:
        user_prompt = (
            f"Value proposition: {spec['value_proposition']}\n\n"
            f"HTML landing page:\n{html[:2000]}\n\n"
            f"Marketing copy:\n{json.dumps(copy, indent=2)}"
        )
        raw = call_llm(QA_SYSTEM_PROMPT, user_prompt)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            cleaned = (
                raw.strip()
                .removeprefix("```json")
                .removeprefix("```")
                .removesuffix("```")
                .strip()
            )
            return json.loads(cleaned)

    def _get_pr_details(self, pr_url: str) -> tuple[int, str]:
        pr_number = int(pr_url.rstrip("/").split("/")[-1])
        r = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/pulls/{pr_number}",
            headers=GITHUB_HEADERS,
        )
        r.raise_for_status()
        commit_id = r.json()["head"]["sha"]
        return pr_number, commit_id

    def _post_pr_comments(self, pr_url: str, report: dict) -> None:
        try:
            pr_number, commit_id = self._get_pr_details(pr_url)
        except Exception as e:
            print(f"[QA] Could not fetch PR details: {e}")
            return

        issues = report.get("html_issues", []) + report.get("copy_issues", [])
        lines_to_comment = [5, 10]
        for i, issue in enumerate(issues[:2]):
            body = f"**QA Review:** {issue}"
            payload = {
                "body": body,
                "commit_id": commit_id,
                "path": "index.html",
                "line": lines_to_comment[i],
                "side": "RIGHT",
            }
            r = requests.post(
                f"https://api.github.com/repos/{GITHUB_REPO}/pulls/{pr_number}/comments",
                headers=GITHUB_HEADERS,
                json=payload,
            )
            if r.status_code in (200, 201):
                print(f"[QA] Posted PR comment: {issue[:60]}...")
            else:
                print(f"[QA] Failed to post comment (status {r.status_code})")
