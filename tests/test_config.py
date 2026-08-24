from digitalme.config import Settings
from pydantic import SecretStr


def test_deepseek_is_optional() -> None:
    settings = Settings(_env_file=None)

    assert settings.deepseek_configured is False


def test_deepseek_secret_is_masked() -> None:
    settings = Settings(
        _env_file=None,
        API_KEY="not-a-real-secret",
        API_BASE_URL="https://example.invalid",
    )

    assert isinstance(settings.api_key, SecretStr)
    assert str(settings.api_key) == "**********"
    assert settings.deepseek_configured is True
