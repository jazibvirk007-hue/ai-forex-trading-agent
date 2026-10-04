from app.integrations.ai import _ids_from_payload, public_provider_catalog


def test_provider_catalog_contains_dynamic_and_custom_options():
    ids = {item["id"] for item in public_provider_catalog()}
    assert {"openai", "xai", "anthropic", "gemini", "openai-compatible"} <= ids


def test_openai_style_model_payload_is_normalized():
    assert _ids_from_payload({"data": [{"id": "b"}, {"id": "a"}]}) == ["a", "b"]


def test_gemini_style_model_payload_is_normalized():
    assert _ids_from_payload({"models": [{"name": "models/gemini-test"}]}) == ["gemini-test"]
