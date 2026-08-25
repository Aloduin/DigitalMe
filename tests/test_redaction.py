import pytest
from digitalme.privacy import (
    ProviderPolicyError,
    Sensitivity,
    is_denied_path,
    redact_text,
    require_provider_access,
)


def test_redacts_common_secret_forms_with_original_offsets() -> None:
    known_secret = "sk-" + "abcdefghijklmnopqrstuvwxyz" + "123456"
    text = f"API_KEY={known_secret} and Authorization: Bearer bearer-token-1234567890"

    result = redact_text(text)

    assert result.sensitivity is Sensitivity.SECRET
    assert known_secret not in result.text
    assert "bearer-token-1234567890" not in result.text
    assert result.text == (
        "API_KEY=[REDACTED:credential_assignment] and "
        "Authorization: Bearer [REDACTED:authorization]"
    )
    assert [text[span.start : span.end] for span in result.spans] == [
        known_secret,
        "bearer-token-1234567890",
    ]


def test_high_entropy_detection_avoids_plain_language_and_uuid() -> None:
    safe = (
        "ThisIsALongButReadableIdentifierForDocumentation and 550e8400-e29b-41d4-a716-446655440000"
    )
    secret = "A9v_K2m-Q8xR5pT1wY7nC4sL6dF0hJ3z"

    assert redact_text(safe).spans == ()
    assert redact_text(secret).text == "[REDACTED:high_entropy]"


@pytest.mark.parametrize(
    "path",
    [".env", "config/.env.production", "keys/id_ed25519", "certs/client.pem"],
)
def test_denied_source_paths(path: str) -> None:
    assert is_denied_path(path)


def test_provider_policy_blocks_secret_unclassified_and_remote_sensitive() -> None:
    with pytest.raises(ProviderPolicyError):
        require_provider_access(Sensitivity.SECRET, local=True)
    with pytest.raises(ProviderPolicyError):
        require_provider_access(Sensitivity.UNCLASSIFIED, local=True)
    with pytest.raises(ProviderPolicyError):
        require_provider_access(Sensitivity.SENSITIVE, local=False)
    with pytest.raises(ProviderPolicyError):
        require_provider_access("unexpected", local=True)

    require_provider_access(Sensitivity.SENSITIVE, local=True)
    require_provider_access(Sensitivity.PERSONAL, local=False)
