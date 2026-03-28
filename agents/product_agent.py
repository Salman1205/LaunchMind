import json
from message_bus import MessageBus
from llm_client import call_llm

SYSTEM_PROMPT = """You are a senior product manager. Given a startup idea, produce a detailed product specification as a JSON object.

The JSON must have exactly these fields:
- value_proposition: string (one sentence)
- personas: array of objects with keys: name, role, pain_point (at least 2 personas)
- features: array of objects with keys: name, description, priority (1=highest, at least 5 features)
- user_stories: array of objects with keys: as_a, i_want, so_that (exactly 3 stories)

Respond with ONLY valid JSON. No markdown, no explanation, no code fences."""


class ProductAgent:
    def __init__(self, bus: MessageBus):
        self.bus = bus

    def run(self):
        messages = self.bus.receive("product")
        for msg in messages:
            if msg["message_type"] not in ("task", "revision_request"):
                continue
            print(f"\n[PRODUCT] Processing message type={msg['message_type']}")
            payload = msg["payload"]
            idea = payload.get("idea", "")
            focus = payload.get("focus", "")
            feedback = payload.get("feedback", "")

            user_prompt = f"Startup idea: {idea}\nFocus: {focus}"
            if feedback:
                user_prompt += f"\nPrevious feedback to address: {feedback}"

            raw = call_llm(SYSTEM_PROMPT, user_prompt)
            print(f"[PRODUCT] Raw LLM output:\n{raw[:300]}...")

            try:
                spec = json.loads(raw)
            except json.JSONDecodeError:
                cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                spec = json.loads(cleaned)

            print(f"[PRODUCT] Spec generated: {spec['value_proposition']}")
            self.bus.send(
                from_agent="product",
                to_agent="ceo",
                message_type="result",
                payload={"product_spec": spec},
                parent_message_id=msg["message_id"],
            )
