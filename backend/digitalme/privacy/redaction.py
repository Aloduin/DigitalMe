"""Deterministic secret detection, redaction and provider policy enforcement."""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import PurePath


class Sensitivity(StrEnum):
    """Content handling classification used at provider boundaries."""

    PUBLIC = "public"
    PERSONAL = "personal"
    SENSITIVE = "sensitive"
    SECRET = "secret"
    UNCLASSIFIED = "unclassified"


@dataclass(frozen=True, slots=True)
class RedactionSpan:
    """Location of a detected secret in the original normalized text."""

    start: int
    end: int
    kind: str
    replacement: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RedactionResult:
    """A safe derived view plus auditable offsets into its source text."""

    text: str
    spans: tuple[RedactionSpan, ...]
    sensitivity: Sensitivity


class ProviderPolicyError(ValueError):
    """Raised when content classification forbids a provider request."""


@dataclass(frozen=True, slots=True)
class _Detector:
    kind: str
    pattern: re.Pattern[str]
    secret_group: str | None = None


_DETECTORS = (
    _Detector(
        "private_key",
        re.compile(
            r"-----BEGIN(?: [A-Z0-9]+)* PRIVATE KEY-----.*?"
            r"-----END(?: [A-Z0-9]+)* PRIVATE KEY-----",
            re.DOTALL,
        ),
    ),
    _Detector(
        "authorization",
        re.compile(r"(?i)\bAuthorization\s*:\s*(?:Bearer|Basic)\s+(?P<secret>[^\s,;]+)"),
        "secret",
    ),
    _Detector(
        "url_credentials",
        re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s/:@]+:(?P<secret>[^\s/@]+)@"),
        "secret",
    ),
    _Detector(
        "credential_assignment",
        re.compile(
            r"(?ix)\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|pwd|"
            r"client[_-]?secret|database[_-]?url)\b\s*[:=]\s*[\"']?(?P<secret>[^\s\"';,]+)"
        ),
        "secret",
    ),
    _Detector(
        "known_token",
        re.compile(
            r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|"
            r"AKIA[0-9A-Z]{16})\b"
        ),
    ),
)

_HIGH_ENTROPY_CANDIDATE = re.compile(r"(?<![A-Za-z0-9_/-])[A-Za-z0-9_/-]{32,}(?![A-Za-z0-9_/-])")
_DENIED_NAMES = frozenset(
    {
        ".env",
        ".env.local",
        ".env.production",
        "id_rsa",
        "id_ed25519",
        "credentials.json",
        "secrets.json",
    }
)
_DENIED_SUFFIXES = (".pem", ".key", ".p12", ".pfx")


def is_denied_path(path: str | PurePath) -> bool:
    """Return whether a source path must never be selected for model input."""

    name = PurePath(path).name.lower()
    return name in _DENIED_NAMES or name.startswith(".env.") or name.endswith(_DENIED_SUFFIXES)


def redact_text(text: str) -> RedactionResult:
    """Create a stable redacted view without modifying the source text."""

    matches: list[tuple[int, int, str]] = []
    for detector in _DETECTORS:
        for match in detector.pattern.finditer(text):
            start, end = (
                match.span(detector.secret_group) if detector.secret_group else match.span()
            )
            matches.append((start, end, detector.kind))

    for match in _HIGH_ENTROPY_CANDIDATE.finditer(text):
        candidate = match.group()
        if _looks_like_high_entropy_secret(candidate):
            matches.append((match.start(), match.end(), "high_entropy"))

    selected = _select_non_overlapping(matches)
    if not selected:
        return RedactionResult(text=text, spans=(), sensitivity=Sensitivity.PERSONAL)

    parts: list[str] = []
    spans: list[RedactionSpan] = []
    cursor = 0
    for start, end, kind in selected:
        replacement = f"[REDACTED:{kind}]"
        parts.extend((text[cursor:start], replacement))
        spans.append(RedactionSpan(start=start, end=end, kind=kind, replacement=replacement))
        cursor = end
    parts.append(text[cursor:])
    return RedactionResult(
        text="".join(parts),
        spans=tuple(spans),
        sensitivity=Sensitivity.SECRET,
    )


def require_provider_access(sensitivity: Sensitivity | str, *, local: bool) -> None:
    """Enforce the final sensitivity gate before any model provider call."""

    try:
        classification = Sensitivity(sensitivity)
    except ValueError as exc:
        raise ProviderPolicyError("unknown sensitivity classification") from exc
    if classification in {Sensitivity.SECRET, Sensitivity.UNCLASSIFIED}:
        raise ProviderPolicyError(f"{classification.value} content cannot be sent to a provider")
    if classification is Sensitivity.SENSITIVE and not local:
        raise ProviderPolicyError("sensitive content requires a local provider")


def _select_non_overlapping(matches: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
    selected: list[tuple[int, int, str]] = []
    for candidate in sorted(matches, key=lambda item: (item[0], -(item[1] - item[0]), item[2])):
        start, end, _ = candidate
        if start == end or any(
            start < kept_end and end > kept_start for kept_start, kept_end, _ in selected
        ):
            continue
        selected.append(candidate)
    return sorted(selected)


def _looks_like_high_entropy_secret(candidate: str) -> bool:
    character_classes = sum(
        (
            any(character.islower() for character in candidate),
            any(character.isupper() for character in candidate),
            any(character.isdigit() for character in candidate),
            "_" in candidate or "-" in candidate or "/" in candidate,
        )
    )
    if character_classes < 3 or len(set(candidate)) < 12:
        return False
    counts = {character: candidate.count(character) for character in set(candidate)}
    entropy = -sum(
        (count / len(candidate)) * math.log2(count / len(candidate)) for count in counts.values()
    )
    return entropy >= 3.7
