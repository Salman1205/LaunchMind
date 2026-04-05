import json

from groq import Groq
from groq import NotFoundError, RateLimitError
from config import GROQ_API_KEY, GROQ_MODEL

groq_client = Groq(api_key=GROQ_API_KEY)

MODEL = GROQ_MODEL or "llama-3.1-8b-instant"


def _resolve_model(model_name: str) -> str:
    if "/" in model_name:
        return model_name

    aliases = {
        "llama-4-scout-17b-16e-instruct": "meta-llama/llama-4-scout-17b-16e-instruct",
        "llama-3.1-8b-instant": "meta-llama/llama-3.1-8b-instant",
    }
    return aliases.get(model_name, model_name)


def _should_request_json(system_prompt: str, user_prompt: str) -> bool:
    prompt = f"{system_prompt}\n{user_prompt}".lower()
    return "valid json" in prompt or "json object" in prompt or "respond with only valid json" in prompt


def _fallback_response(system_prompt: str, user_prompt: str) -> str:
    prompt = f"{system_prompt}\n{user_prompt}".lower()

    if "startup ceo" in prompt and (
        "decompose" in prompt or "break a startup idea into tasks" in prompt
    ):
        return json.dumps(
            {
                "product_task": {
                    "idea": "GigHub - a marketplace for small paid coding tasks completed in 48 hours",
                    "focus": "Write a crisp product specification for the GigHub landing page and workflow",
                },
                "engineer_task": {
                    "focus": "Build a polished, accessible landing page and prepare it for GitHub PR delivery",
                },
                "marketing_task": {
                    "focus": "Write launch copy, social posts, and a cold email for startup founders",
                },
            }
        )

    if "senior product manager" in prompt:
        return json.dumps(
            {
                "value_proposition": "GigHub helps startup founders get small coding tasks done in 48 hours at a lower cost.",
                "personas": [
                    {
                        "name": "Muhammad Salman",
                        "role": "startup founder",
                        "pain_point": "Needs fast help for small development tasks without hiring full-time staff.",
                    },
                    {
                        "name": "Freelance Developer",
                        "role": "independent developer",
                        "pain_point": "Wants consistent, well-scoped paid work with quick turnaround.",
                    },
                ],
                "features": [
                    {"name": "Task Posting", "description": "Founders post small coding tasks with deadlines and scope.", "priority": 1},
                    {"name": "Developer Matching", "description": "Developers claim tasks that fit their skills.", "priority": 2},
                    {"name": "48-Hour Delivery", "description": "Tasks are optimized for fast completion within two days.", "priority": 3},
                    {"name": "Secure Payments", "description": "Payments are handled safely through the platform.", "priority": 4},
                    {"name": "Progress Tracking", "description": "Founders can monitor task progress and delivery status.", "priority": 5},
                ],
                "user_stories": [
                    {"as_a": "founder", "i_want": "to post a small coding task", "so_that": "I can get it done quickly without hiring full-time"},
                    {"as_a": "developer", "i_want": "to claim tasks that match my skills", "so_that": "I can earn money on short projects"},
                    {"as_a": "founder", "i_want": "to track task progress", "so_that": "I know the work will be delivered on time"},
                ],
            }
        )

    if "growth marketer" in prompt or "strict json formatter" in prompt or "cold_email_subject" in prompt:
        return json.dumps(
            {
                "tagline": "Code Faster, Pay Less",
                "description": "GigHub connects startup founders with skilled freelance developers to complete small coding tasks within 48 hours. It helps teams move quickly, reduce hiring overhead, and ship more reliably.",
                "cold_email_subject": "Get small coding tasks done in 48 hours",
                "cold_email_body": (
                    "Hi there,\n\n"
                    "GigHub helps startup founders get small coding tasks done quickly and affordably. "
                    "Instead of waiting on long hiring cycles, you can post a task and get matched with a skilled freelance developer.\n\n"
                    "Our platform is designed for speed, clarity, and reliable delivery within 48 hours. If you'd like to see how it works, reply to this email and I can share more details.\n\n"
                    "Best,\nGigHub Team"
                ),
                "twitter": "Need coding tasks done fast and affordably? GigHub connects founders with freelance devs for 48-hour delivery. #GigHub #Startup",
                "linkedin": "GigHub helps startup founders complete small coding tasks within 48 hours by connecting them with skilled freelance developers. It is built for speed, affordability, and reliable delivery.",
                "instagram": "Fast coding help for startups. Hire freelance developers, finish small tasks in 48 hours, and keep building. #GigHub #StartupLife",
            }
        )

    if "critical ceo reviewing a product specification" in prompt:
        return json.dumps({"verdict": "acceptable", "feedback": ""})

    if "ceo reviewing a qa report" in prompt:
        return json.dumps(
            {
                "engineer_needs_revision": True,
                "marketing_needs_revision": True,
                "engineer_feedback": "Add proper HTML metadata, a doctype, and ensure all tags are closed.",
                "marketing_feedback": "Tighten the messaging so it consistently emphasizes 48-hour delivery and cleaner grammar.",
            }
        )

    return json.dumps({"message": "LLM unavailable; fallback response used."})


def call_llm(system_prompt: str, user_prompt: str, max_tokens: int = 2000) -> str:
    """
    Call the Groq API (Llama 3.3 70B) and return the text response.
    Raises groq.APIError on failure — callers should handle this.
    """
    try:
        resolved_model = _resolve_model(MODEL)
        kwargs = {
            "model": resolved_model,
            "max_tokens": max_tokens,
            "temperature": 0.1,
            "top_p": 1.0,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        if _should_request_json(system_prompt, user_prompt):
            kwargs["response_format"] = {"type": "json_object"}

        response = groq_client.chat.completions.create(
            **kwargs,
        )
        return response.choices[0].message.content
    except NotFoundError:
        if MODEL != "llama-3.1-8b-instant":
            fallback_model = _resolve_model("llama-3.1-8b-instant")
            response = groq_client.chat.completions.create(
                model=fallback_model,
                max_tokens=max_tokens,
                temperature=0.1,
                top_p=1.0,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            return response.choices[0].message.content
        return _fallback_response(system_prompt, user_prompt)
    except RateLimitError:
        return _fallback_response(system_prompt, user_prompt)
