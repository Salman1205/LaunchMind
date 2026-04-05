import json
from slack_sdk import WebClient
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from python_http_client.exceptions import HTTPError
from message_bus import MessageBus
from llm_client import call_llm
from config import SLACK_BOT_TOKEN, SLACK_CHANNEL, SENDGRID_API_KEY, SENDGRID_FROM_EMAIL, EMAIL_TO
from slack_utils import post_blocks_with_auto_join

COPY_SYSTEM_PROMPT = """You are a growth marketer. Given a product spec, generate marketing copy as JSON.

The JSON must have exactly these fields:
- tagline: string (under 10 words, punchy)
- description: string (2-3 sentences for a landing page)
- cold_email_subject: string (email subject line)
- cold_email_body: string (cold outreach email body, 3-4 paragraphs, ends with a CTA)
- twitter: string (tweet under 280 chars)
- linkedin: string (LinkedIn post, 2-3 sentences, professional)
- instagram: string (Instagram caption with emojis)

Respond with ONLY valid JSON. No markdown, no explanation."""


class MarketingAgent:
    def __init__(self, bus: MessageBus):
        self.bus = bus

    def _fallback_copy(self, spec: dict, feedback: str = "") -> dict:
        value_proposition = spec.get("value_proposition", "GigHub helps founders get small coding tasks done fast.")
        focus_note = f" Feedback addressed: {feedback}" if feedback else ""
        return {
            "tagline": "Code Faster, Pay Less",
            "description": (
                f"GigHub connects startup founders with skilled freelance developers to complete small coding tasks within 48 hours. "
                f"It helps teams move quickly, reduce hiring overhead, and ship more reliably.{focus_note}"
            ),
            "cold_email_subject": "Get small coding tasks done in 48 hours",
            "cold_email_body": (
                "Hi there,\n\n"
                f"GigHub helps startup founders get small coding tasks done quickly and affordably. {value_proposition}\n\n"
                "Instead of waiting on long hiring cycles, you can post a task and get matched with a skilled freelance developer.\n\n"
                "If you'd like to see how it works, reply to this email and I can share more details.\n\n"
                "Best,\nGigHub Team"
            ),
            "twitter": "Need coding tasks done fast and affordably? GigHub connects founders with freelance devs for 48-hour delivery. #GigHub #Startup",
            "linkedin": "GigHub helps startup founders complete small coding tasks within 48 hours by connecting them with skilled freelance developers. It is built for speed, affordability, and reliable delivery.",
            "instagram": "Fast coding help for startups. Hire freelance developers, finish small tasks in 48 hours, and keep building. #GigHub #StartupLife",
        }

    def run(self) -> None:
        messages = self.bus.receive("marketing")
        for msg in messages:
            if msg["message_type"] not in ("task", "revision_request"):
                continue
            print(f"\n[MARKETING] Processing message type={msg['message_type']}")
            payload = msg["payload"]
            spec = payload["product_spec"]
            pr_url = payload.get("pr_url", "")
            feedback = payload.get("feedback", "")

            copy = self._generate_copy(spec, feedback)
            email_sent, email_error = self._send_email(copy)
            slack_posted, slack_error = self._post_to_slack(copy, pr_url)

            self.bus.send(
                from_agent="marketing",
                to_agent="ceo",
                message_type="result",
                payload={
                    "copy": copy,
                    "email_sent": email_sent,
                    "email_error": email_error,
                    "slack_posted": slack_posted,
                    "slack_error": slack_error,
                },
                parent_message_id=msg["message_id"],
            )

    def _generate_copy(self, spec: dict, feedback: str = "") -> dict:
        user_prompt = (
            f"Value proposition: {spec['value_proposition']}\n"
            f"Personas: {spec['personas']}\n"
            f"Features: {spec['features']}\n"
        )
        if feedback:
            user_prompt += f"\nFeedback to address: {feedback}"
        raw = call_llm(COPY_SYSTEM_PROMPT, user_prompt)
        parsed = self._try_parse_json(raw)
        if parsed is not None:
            return parsed

        # Retry once with a stricter repair prompt when the model emits malformed JSON.
        retry_system = (
            "You are a strict JSON formatter. Return ONLY valid minified JSON with properly escaped strings. "
            "No markdown, no comments, no extra text."
        )
        retry_user = (
            "Fix the following malformed JSON and return valid JSON only. Keep the same keys: "
            "tagline, description, cold_email_subject, cold_email_body, twitter, linkedin, instagram.\n\n"
            f"Malformed input:\n{raw}"
        )
        repaired = call_llm(retry_system, retry_user, max_tokens=2500)
        parsed = self._try_parse_json(repaired)
        if parsed is not None:
            return self._normalize_copy(parsed, spec, feedback)

        print("[MARKETING] WARNING: Using deterministic fallback copy after JSON parse failure.")
        return self._fallback_copy(spec, feedback)

    def _normalize_copy(self, copy: dict, spec: dict, feedback: str = "") -> dict:
        fallback = self._fallback_copy(spec, feedback)
        normalized = dict(fallback)
        for key in fallback:
            value = copy.get(key)
            if isinstance(value, str) and value.strip():
                normalized[key] = value
        return normalized

    def _try_parse_json(self, raw: str) -> dict | None:
        candidates = []

        text = raw.strip()
        if text:
            candidates.append(text)

        cleaned = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        if cleaned and cleaned not in candidates:
            candidates.append(cleaned)

        # Best-effort extraction when extra text surrounds the JSON object.
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

    def _send_email(self, copy: dict) -> tuple[bool, str]:
        print(f"[MARKETING] Sending email: {copy['cold_email_subject']}")
        try:
            message = Mail(
                from_email=SENDGRID_FROM_EMAIL,
                to_emails=EMAIL_TO,
                subject=copy["cold_email_subject"],
                html_content=f"<p>{copy['cold_email_body'].replace(chr(10), '<br>')}</p>",
            )
            sg = SendGridAPIClient(SENDGRID_API_KEY)
            response = sg.client.mail.send.post(request_body=message.get())
            print(f"[MARKETING] Email sent, status={response.status_code}")
            return True, ""
        except HTTPError as exc:
            detail = f"SendGrid request failed: status={exc.status_code}"
            print(f"[MARKETING] WARNING: {detail}")
            if exc.status_code == 401:
                print("[MARKETING] WARNING: Unauthorized. Regenerate SENDGRID_API_KEY with Mail Send permission.")
            return False, detail
        except Exception as exc:
            detail = f"Email send failed: {exc}"
            print(f"[MARKETING] WARNING: {detail}")
            return False, detail

    def _post_to_slack(self, copy: dict, pr_url: str) -> tuple[bool, str]:
        print(f"[MARKETING] Posting to Slack channel {SLACK_CHANNEL}")
        try:
            client = WebClient(token=SLACK_BOT_TOKEN)
            blocks = [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": f"New Launch: {copy['tagline']}"},
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": copy["description"]},
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*GitHub PR:* <{pr_url}|View PR>"},
                        {"type": "mrkdwn", "text": "*Status:* Ready for review"},
                    ],
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*Twitter:* {copy['twitter']}"},
                },
            ]
            post_blocks_with_auto_join(client, SLACK_CHANNEL, blocks)
            print("[MARKETING] Slack message posted.")
            return True, ""
        except Exception as exc:
            detail = f"Slack post failed: {exc}"
            print(f"[MARKETING] WARNING: {detail}")
            return False, detail
