import json

import pytest

from src.api.main import _load_release_identity


def test_load_release_identity_accepts_exact_release_contract(tmp_path):
    identity_path = tmp_path / "mutx-release.json"
    expected = {
        "tag": "v1.4.0",
        "version": "1.4.0",
        "sha": "a" * 40,
    }
    identity_path.write_text(json.dumps(expected), encoding="utf-8")

    assert _load_release_identity(identity_path) == expected


@pytest.mark.parametrize(
    "payload",
    (
        {"tag": "v1.4.0", "version": "1.4.0"},
        {"tag": "v1.4.0", "version": "1.4.0", "sha": "not-a-commit"},
        {"tag": "v1.4.0", "version": "1.4.0", "sha": "a" * 40, "extra": "stale"},
    ),
)
def test_load_release_identity_rejects_partial_or_ambiguous_contract(tmp_path, payload):
    identity_path = tmp_path / "mutx-release.json"
    identity_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError):
        _load_release_identity(identity_path)
