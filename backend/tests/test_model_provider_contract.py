import json

import httpx2
import pytest

from llm_eval_lab.model_provider import ModelProviderFailure, ModelRequest
from llm_eval_lab.ollama_provider import OllamaModelAdapter


def test_ollama_adapter_satisfies_the_provider_neutral_success_contract():
    def respond(request: httpx2.Request) -> httpx2.Response:
        assert str(request.url) == "http://ollama.test/api/generate"
        assert json.loads(request.content) == {
            "model": "qwen-demo",
            "system": "Use supplied evidence only.",
            "prompt": "Grounding material:\n- policy\n\nUser input:\nQuestion",
            "options": {"temperature": 0},
            "stream": False,
        }
        return httpx2.Response(
            200,
            json={
                "response": "Evidence-based answer.",
                "prompt_eval_count": 23,
                "eval_count": 5,
            },
        )

    client = httpx2.Client(
        base_url="http://ollama.test",
        transport=httpx2.MockTransport(respond),
    )
    adapter = OllamaModelAdapter(client)

    response = adapter.generate(
        ModelRequest(
            model="qwen-demo",
            system_prompt="Use supplied evidence only.",
            user_prompt="Grounding material:\n- policy\n\nUser input:\nQuestion",
            generation_parameters={"temperature": 0},
        )
    )

    assert response.content == "Evidence-based answer."
    assert response.usage.prompt_tokens == 23
    assert response.usage.completion_tokens == 5
    assert response.usage.total_tokens == 28


def test_ollama_adapter_reports_an_actionable_unavailable_service_failure():
    def refuse_connection(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("connection refused", request=request)

    client = httpx2.Client(
        base_url="http://127.0.0.1:11434",
        transport=httpx2.MockTransport(refuse_connection),
    )
    adapter = OllamaModelAdapter(client)

    with pytest.raises(ModelProviderFailure) as raised:
        adapter.generate(
            ModelRequest(
                model="qwen-demo",
                system_prompt="Use supplied evidence only.",
                user_prompt="Question",
                generation_parameters={},
            )
        )

    assert raised.value.code == "provider_unavailable"
    assert raised.value.message == (
        "Cannot reach Ollama at http://127.0.0.1:11434. Start Ollama and verify "
        "OLLAMA_BASE_URL."
    )


def test_ollama_adapter_reports_an_actionable_missing_model_failure():
    client = httpx2.Client(
        base_url="http://ollama.test",
        transport=httpx2.MockTransport(
            lambda _: httpx2.Response(404, json={"error": "model 'missing' not found"})
        ),
    )
    adapter = OllamaModelAdapter(client)

    with pytest.raises(ModelProviderFailure) as raised:
        adapter.generate(
            ModelRequest(
                model="missing",
                system_prompt="Use supplied evidence only.",
                user_prompt="Question",
                generation_parameters={},
            )
        )

    assert raised.value.code == "model_unavailable"
    assert raised.value.message == (
        "Ollama model 'missing' is unavailable. Install it locally or select an installed model."
    )


def test_ollama_adapter_reports_an_actionable_timeout_failure():
    def time_out(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("timed out", request=request)

    client = httpx2.Client(
        base_url="http://127.0.0.1:11434",
        transport=httpx2.MockTransport(time_out),
    )
    adapter = OllamaModelAdapter(client)

    with pytest.raises(ModelProviderFailure) as raised:
        adapter.generate(
            ModelRequest(
                model="slow-model",
                system_prompt="Use supplied evidence only.",
                user_prompt="Question",
                generation_parameters={},
            )
        )

    assert raised.value.code == "provider_timeout"
    assert raised.value.message == (
        "Ollama at http://127.0.0.1:11434 did not respond before the configured timeout. "
        "Verify the service and model, or adjust OLLAMA_TIMEOUT_SECONDS."
    )
