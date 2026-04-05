import json
from slack_sdk import WebClient
from message_bus import MessageBus
from llm_client import call_llm
from config import SLACK_BOT_TOKEN, SLACK_CHANNEL
from slack_utils import post_blocks_with_auto_join

DECOMPOSE_SYSTEM = """You are a startup CEO. Break a startup idea into tasks for your team.
Return a JSON object with these keys:
- product_task: object with "idea" and "focus" strings
- engineer_task: object with "focus" string
- marketing_task: object with "focus" string
Respond with ONLY valid JSON."""

REVIEW_SPEC_SYSTEM = """You are a critical CEO reviewing a product specification.
Evaluate whether the spec is specific, actionable, and complete.
Return a JSON object with:
- verdict: "acceptable" or "needs_revision"
- feedback: string (empty if acceptable, specific feedback if needs_revision)
Respond with ONLY valid JSON."""

REVIEW_QA_SYSTEM = """You are a CEO reviewing a QA report. Determine which agent needs to revise its work.
Return a JSON object with:
- engineer_needs_revision: boolean
- marketing_needs_revision: boolean
- engineer_feedback: string (empty if no revision needed)
- marketing_feedback: string (empty if no revision needed)
Respond with ONLY valid JSON."""


class CEOAgent:
    def __init__(self, bus: MessageBus, startup_idea: str):
        self.bus = bus
        self.startup_idea = startup_idea
        self._decisions: list[str] = []

    def log(self, decision: str) -> None:
        print(f"[CEO] {decision}")
        self._decisions.append(decision)

    def _try_parse_json(self, raw: str) -> dict | None:
        candidates = []

        text = raw.strip()
        if text:
            candidates.append(text)

        cleaned = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        if cleaned and cleaned not in candidates:
            candidates.append(cleaned)

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            extracted = cleaned[start:end + 1]
            if extracted not in candidates:
                candidates.append(extracted)

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue
        return None

    def _fallback_product_review(self, spec: dict) -> dict:
        value = spec.get("value_proposition", "")
        if value:
            return {"verdict": "acceptable", "feedback": ""}
        return {
            "verdict": "needs_revision",
            "feedback": "The product spec is missing a clear value proposition."
        }

    def _fallback_qa_review(self) -> dict:
        return {
            "engineer_needs_revision": True,
            "marketing_needs_revision": True,
            "engineer_feedback": "Add a doctype, proper metadata, and verify every HTML tag is closed.",
            "marketing_feedback": "Tighten the copy so it consistently highlights 48-hour delivery and cleaner grammar.",
        }

    def decompose_and_send(self) -> None:
        self.log(f"Decomposing idea: {self.startup_idea}")
        raw = call_llm(DECOMPOSE_SYSTEM, f"Startup idea: {self.startup_idea}")
        tasks = self._try_parse_json(raw)
        if tasks is None:
            raise ValueError("CEO could not parse task decomposition JSON")

        self.log("Sending task to Product agent")
        self.bus.send("ceo", "product", "task", {
            "idea": self.startup_idea,
            **tasks["product_task"],
        })

    def review_product_spec(self, spec: dict) -> dict:
        self.log("Reviewing product spec with LLM...")
        raw = call_llm(REVIEW_SPEC_SYSTEM, f"Product spec:\n{json.dumps(spec, indent=2)}")
        review = self._try_parse_json(raw)
        if review is None:
            print("[CEO] WARNING: Using fallback product review after JSON parse failure.")
            review = self._fallback_product_review(spec)

        self.log(f"Product spec verdict: {review['verdict']}")
        if review["verdict"] == "needs_revision":
            self.log(f"Requesting revision: {review['feedback']}")
            self.bus.send("ceo", "product", "revision_request", {
                "idea": self.startup_idea,
                "focus": "Revise based on feedback",
                "feedback": review["feedback"],
            })
        return review

    def dispatch_to_engineer_and_marketing(self, spec: dict, pr_url: str = "") -> None:
        self.log("Dispatching product spec to Engineer and Marketing agents")
        self.bus.send("ceo", "engineer", "task", {"product_spec": spec})
        self.bus.send("ceo", "marketing", "task", {"product_spec": spec, "pr_url": pr_url})

    def review_qa_report(
        self,
        report: dict,
        spec: dict,
        engineer_html: str,
        marketing_copy: dict,
        engineer_pr_url: str,
    ) -> dict:
        self.log(f"Reviewing QA verdict: {report['overall_verdict']}")
        if report["overall_verdict"] == "pass":
            return {
                "engineer_needs_revision": False,
                "marketing_needs_revision": False,
                "engineer_feedback": "",
                "marketing_feedback": "",
            }

        user_prompt = (
            f"QA report:\n{json.dumps(report, indent=2)}\n\n"
            f"What should the Engineer and Marketing agents fix?"
        )
        raw = call_llm(REVIEW_QA_SYSTEM, user_prompt)
        decision = self._try_parse_json(raw)
        if decision is None:
            print("[CEO] WARNING: Using fallback QA review after JSON parse failure.")
            decision = self._fallback_qa_review()

        if decision.get("engineer_needs_revision"):
            self.log(f"Requesting Engineer revision: {decision['engineer_feedback']}")
            self.bus.send("ceo", "engineer", "revision_request", {
                "product_spec": spec,
                "feedback": decision["engineer_feedback"],
                "pr_url": engineer_pr_url,
            })

        if decision.get("marketing_needs_revision"):
            self.log(f"Requesting Marketing revision: {decision['marketing_feedback']}")
            self.bus.send("ceo", "marketing", "revision_request", {
                "product_spec": spec,
                "feedback": decision["marketing_feedback"],
                "pr_url": engineer_pr_url,
            })
        return decision

    def post_final_summary(self, spec: dict, pr_url: str, email_sent: bool) -> None:
        self.log("Posting final summary to Slack")
        summary = (
            f"*LaunchMind Pipeline Complete* :rocket:\n\n"
            f"*Startup:* {spec.get('value_proposition', 'N/A')}\n"
            f"*GitHub PR:* <{pr_url}|View Pull Request>\n"
            f"*Email sent:* {'Yes' if email_sent else 'No'}\n\n"
            f"*CEO Decision Log (last 5):*\n"
            + "\n".join(f"  • {d}" for d in self._decisions[-5:])
        )
        client = WebClient(token=SLACK_BOT_TOKEN)
        post_blocks_with_auto_join(
            client,
            SLACK_CHANNEL,
            [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "LaunchMind: Pipeline Complete"},
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": summary},
                },
            ],
        )
        self.log("Final summary posted to Slack.")

    def get_decision_log(self) -> list[str]:
        return list(self._decisions)
