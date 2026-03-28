import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock
from llm_client import call_llm


def test_call_llm_returns_string():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Hello world")]
    with patch("llm_client.anthropic_client.messages.create", return_value=mock_response):
        result = call_llm("You are helpful.", "Say hello.")
    assert result == "Hello world"


def test_call_llm_passes_prompts():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="ok")]
    with patch("llm_client.anthropic_client.messages.create", return_value=mock_response) as mock_create:
        call_llm("system prompt", "user prompt")
        call_args = mock_create.call_args
        assert call_args.kwargs["system"] == "system prompt"
        assert call_args.kwargs["messages"][0]["content"] == "user prompt"


def test_call_llm_default_max_tokens():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="ok")]
    with patch("llm_client.anthropic_client.messages.create", return_value=mock_response) as mock_create:
        call_llm("sys", "user")
        assert mock_create.call_args.kwargs["max_tokens"] == 2000
