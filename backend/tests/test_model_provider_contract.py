import json

import httpx2
import pytest
from pydantic import ValidationError

import llm_eval_lab.config as config_module
from llm_eval_lab.config import Settings
from llm_eval_lab.demo_provider import (
    DEMO_BASELINE_MODEL,
    DeterministicDemoAdapter,
)
from llm_eval_lab.model_provider import (
    ModelProviderFailure,
    ModelRequest,
    ModelResponse,
    get_model_provider_registry,
)
from llm_eval_lab.ollama_provider import OllamaModelAdapter
from llm_eval_lab.openai_compatible_provider import OpenAICompatibleAdapter
from llm_eval_lab.sample_suite import SAMPLE_TEST_CASES


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


def test_openai_compatible_adapter_maps_chat_completion_usage_and_known_cost():
    def respond(request: httpx2.Request) -> httpx2.Response:
        assert str(request.url) == "https://compatible.test/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer process-only-secret"
        assert json.loads(request.content) == {
            "temperature": 0,
            "max_tokens": 80,
            "model": "compatible-model",
            "messages": [
                {"role": "system", "content": "Use supplied evidence only."},
                {"role": "user", "content": "Question"},
            ],
            "stream": False,
        }
        return httpx2.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": "Supported answer."}}
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "total_tokens": 120,
                },
            },
        )

    client = httpx2.Client(
        base_url="https://compatible.test/v1/",
        headers={"Authorization": "Bearer process-only-secret"},
        transport=httpx2.MockTransport(respond),
    )
    adapter = OpenAICompatibleAdapter(
        client,
        input_cost_per_million_tokens=2.5,
        output_cost_per_million_tokens=10,
    )

    response = adapter.generate(
        ModelRequest(
            model="compatible-model",
            system_prompt="Use supplied evidence only.",
            user_prompt="Question",
            generation_parameters={"temperature": 0, "max_tokens": 80},
        )
    )

    assert response == ModelResponse(
        content="Supported answer.",
        usage=response.usage,
    )
    assert response.usage.prompt_tokens == 100
    assert response.usage.completion_tokens == 20
    assert response.usage.total_tokens == 120
    assert response.usage.cost_usd == pytest.approx(0.00045)


def test_openai_compatible_adapter_keeps_cost_unknown_without_complete_pricing():
    client = httpx2.Client(
        base_url="https://compatible.test/v1/",
        transport=httpx2.MockTransport(
            lambda _: httpx2.Response(
                200,
                json={
                    "choices": [{"message": {"content": "Answer"}}],
                    "usage": {
                        "prompt_tokens": 7,
                        "completion_tokens": 3,
                        "total_tokens": 10,
                    },
                },
            )
        ),
    )
    adapter = OpenAICompatibleAdapter(
        client,
        input_cost_per_million_tokens=1,
        output_cost_per_million_tokens=None,
    )

    response = adapter.generate(
        ModelRequest(
            model="compatible-model",
            system_prompt="System",
            user_prompt="Question",
            generation_parameters={},
        )
    )

    assert response.usage.total_tokens == 10
    assert response.usage.cost_usd is None


def test_openai_compatible_adapter_reports_rate_limits_without_response_secrets():
    secret = "must-not-appear-in-errors"
    client = httpx2.Client(
        base_url="https://compatible.test/v1/",
        headers={"Authorization": f"Bearer {secret}"},
        transport=httpx2.MockTransport(
            lambda _: httpx2.Response(429, json={"error": {"message": secret}})
        ),
    )
    adapter = OpenAICompatibleAdapter(client)

    with pytest.raises(ModelProviderFailure) as raised:
        adapter.generate(
            ModelRequest(
                model="compatible-model",
                system_prompt="System",
                user_prompt="Question",
                generation_parameters={},
            )
        )

    assert raised.value.code == "provider_rate_limited"
    assert "OPENAI_COMPATIBLE_BASE_URL" in raised.value.message
    assert secret not in raised.value.message


def test_openai_compatible_adapter_reports_an_actionable_connection_failure():
    def refuse_connection(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("connection refused", request=request)

    client = httpx2.Client(
        base_url="https://compatible.test/v1/",
        transport=httpx2.MockTransport(refuse_connection),
    )
    adapter = OpenAICompatibleAdapter(client)

    with pytest.raises(ModelProviderFailure) as raised:
        adapter.generate(
            ModelRequest(
                model="compatible-model",
                system_prompt="System",
                user_prompt="Question",
                generation_parameters={},
            )
        )

    assert raised.value.code == "provider_unavailable"
    assert raised.value.message == (
        "Cannot reach the configured OpenAI-compatible endpoint. Verify "
        "OPENAI_COMPATIBLE_BASE_URL and local network access."
    )


def test_openai_compatible_adapter_reports_an_actionable_timeout_failure():
    secret = "must-not-appear-in-errors"

    def time_out(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout(secret, request=request)

    client = httpx2.Client(
        base_url="https://compatible.test/v1/",
        headers={"Authorization": f"Bearer {secret}"},
        transport=httpx2.MockTransport(time_out),
    )
    adapter = OpenAICompatibleAdapter(client)

    with pytest.raises(ModelProviderFailure) as raised:
        adapter.generate(
            ModelRequest(
                model="compatible-model",
                system_prompt="System",
                user_prompt="Question",
                generation_parameters={},
            )
        )

    assert raised.value.code == "provider_timeout"
    assert "OPENAI_COMPATIBLE_TIMEOUT_SECONDS" in raised.value.message
    assert secret not in raised.value.message


@pytest.mark.parametrize(
    ("status_code", "expected_code"),
    [
        (401, "provider_authentication_failed"),
        (403, "provider_authentication_failed"),
        (404, "model_unavailable"),
        (500, "provider_request_failed"),
    ],
)
def test_openai_compatible_adapter_maps_http_failures_without_response_secrets(
    status_code: int,
    expected_code: str,
):
    secret = "must-not-appear-in-errors"
    client = httpx2.Client(
        base_url="https://compatible.test/v1/",
        headers={"Authorization": f"Bearer {secret}"},
        transport=httpx2.MockTransport(
            lambda _: httpx2.Response(
                status_code,
                json={"error": {"message": secret}},
            )
        ),
    )
    adapter = OpenAICompatibleAdapter(client)

    with pytest.raises(ModelProviderFailure) as raised:
        adapter.generate(
            ModelRequest(
                model="compatible-model",
                system_prompt="System",
                user_prompt="Question",
                generation_parameters={},
            )
        )

    assert raised.value.code == expected_code
    assert secret not in raised.value.message


@pytest.mark.parametrize(
    "provider_response",
    [
        httpx2.Response(200, content=b"not-json"),
        httpx2.Response(200, json={"choices": []}),
        httpx2.Response(200, json={"choices": [{"message": {}}]}),
    ],
)
def test_openai_compatible_adapter_rejects_malformed_responses_without_secrets(
    provider_response: httpx2.Response,
):
    secret = "must-not-appear-in-errors"
    client = httpx2.Client(
        base_url="https://compatible.test/v1/",
        headers={"Authorization": f"Bearer {secret}"},
        transport=httpx2.MockTransport(lambda _: provider_response),
    )
    adapter = OpenAICompatibleAdapter(client)

    with pytest.raises(ModelProviderFailure) as raised:
        adapter.generate(
            ModelRequest(
                model="compatible-model",
                system_prompt="System",
                user_prompt="Question",
                generation_parameters={},
            )
        )

    assert raised.value.code == "invalid_provider_response"
    assert secret not in raised.value.message


def test_openai_compatible_environment_settings_mask_secrets_and_validate_pricing():
    secret = "process-only-secret"
    settings = Settings(
        database_url="sqlite://",
        openai_compatible_base_url="https://compatible.test/v1",
        openai_compatible_api_key=secret,
        openai_compatible_input_cost_per_million_tokens=2.5,
        openai_compatible_output_cost_per_million_tokens=10,
        _env_file=None,
    )

    assert settings.openai_compatible_api_key is not None
    assert settings.openai_compatible_api_key.get_secret_value() == secret
    assert secret not in repr(settings)

    with pytest.raises(ValidationError):
        Settings(
            database_url="sqlite://",
            openai_compatible_input_cost_per_million_tokens=-1,
            _env_file=None,
        )


def test_registry_adds_remote_provider_only_when_its_base_url_is_configured(monkeypatch):
    real_client = httpx2.Client
    observed: dict[str, object] = {}

    def respond(request: httpx2.Request) -> httpx2.Response:
        observed["request_url"] = str(request.url)
        observed["authorized"] = (
            request.headers.get("Authorization") == "Bearer process-only-secret"
        )
        return httpx2.Response(
            200,
            json={
                "choices": [{"message": {"content": "Configured answer"}}],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "total_tokens": 120,
                },
            },
        )

    def build_client(**kwargs: object) -> httpx2.Client:
        is_remote = kwargs.get("base_url") == "https://compatible.test/v1/"
        if is_remote:
            observed["base_url"] = kwargs.get("base_url")
            observed["timeout"] = kwargs.get("timeout")
            observed["trust_env"] = kwargs.get("trust_env")
            kwargs["transport"] = httpx2.MockTransport(respond)
        return real_client(**kwargs)

    configured = Settings(
        database_url="sqlite://",
        openai_compatible_base_url="https://compatible.test/v1",
        openai_compatible_api_key="process-only-secret",
        openai_compatible_timeout_seconds=37,
        openai_compatible_input_cost_per_million_tokens=2.5,
        openai_compatible_output_cost_per_million_tokens=10,
        _env_file=None,
    )
    monkeypatch.setattr(config_module, "get_settings", lambda: configured)
    monkeypatch.setattr(httpx2, "Client", build_client)
    get_model_provider_registry.cache_clear()
    try:
        registry = get_model_provider_registry()
        response = registry.get("openai-compatible").generate(
            ModelRequest(
                model="configured-model",
                system_prompt="System",
                user_prompt="Question",
                generation_parameters={},
            )
        )
        assert response.content == "Configured answer"
        assert response.usage.cost_usd == pytest.approx(0.00045)
        assert observed == {
            "base_url": "https://compatible.test/v1/",
            "timeout": 37,
            "trust_env": False,
            "request_url": "https://compatible.test/v1/chat/completions",
            "authorized": True,
        }
    finally:
        get_model_provider_registry.cache_clear()

    offline = Settings(database_url="sqlite://", _env_file=None)
    monkeypatch.setattr(config_module, "get_settings", lambda: offline)
    try:
        registry = get_model_provider_registry()
        with pytest.raises(ModelProviderFailure) as raised:
            registry.get("openai-compatible")
        assert raised.value.code == "unsupported_provider"
    finally:
        get_model_provider_registry.cache_clear()


@pytest.mark.parametrize("provider_name", ["ollama", "openai-compatible", "demo-fixture"])
def test_adapters_share_the_provider_neutral_success_contract(provider_name: str):
    test_case = SAMPLE_TEST_CASES[0]
    request = ModelRequest(
        model="contract-model",
        system_prompt="Use supplied evidence only.",
        user_prompt=f"User input:\n{test_case['user_input']}",
        generation_parameters={"temperature": 0},
    )

    if provider_name == "ollama":
        client = httpx2.Client(
            base_url="http://ollama.test",
            transport=httpx2.MockTransport(
                lambda _: httpx2.Response(
                    200,
                    json={"response": "Contract answer", "prompt_eval_count": 3, "eval_count": 2},
                )
            ),
        )
        adapter = OllamaModelAdapter(client)
    elif provider_name == "openai-compatible":
        client = httpx2.Client(
            base_url="https://compatible.test/v1/",
            transport=httpx2.MockTransport(
                lambda _: httpx2.Response(
                    200,
                    json={
                        "choices": [{"message": {"content": "Contract answer"}}],
                        "usage": {
                            "prompt_tokens": 3,
                            "completion_tokens": 2,
                            "total_tokens": 5,
                        },
                    },
                )
            ),
        )
        adapter = OpenAICompatibleAdapter(client)
    else:
        request = ModelRequest(
            model=DEMO_BASELINE_MODEL,
            system_prompt="Use supplied evidence only.",
            user_prompt=f"User input:\n{test_case['user_input']}",
            generation_parameters={"temperature": 0},
        )
        adapter = DeterministicDemoAdapter()

    response = adapter.generate(request)

    assert isinstance(response, ModelResponse)
    assert isinstance(response.content, str) and response.content
    assert response.usage.total_tokens is None or response.usage.total_tokens >= 0
