"""``scripts/read_back_auth_email_templates.py`` compares a Management API response with the files.

#202, ADR-063 § 6. The owner runs the script after every push to the hosted project, with a
personal access token, so no CI job can reach the hosted copy. What a test can pin is the
comparison, fed a saved response the way ``--response`` feeds it, and the request the fetch sends.

The saved responses here are built from the repository's own two files, so "equal" means equal to
what ``supabase/templates/`` holds today, byte for byte.
"""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO / "scripts" / "read_back_auth_email_templates.py"
_TEMPLATES = _REPO / "supabase" / "templates"


def _load_script() -> ModuleType:
    """Import the script by path. It lives in ``scripts/``, which is not a package."""
    spec = importlib.util.spec_from_file_location("read_back_under_test", _SCRIPT)
    assert spec is not None and spec.loader is not None, f"cannot load {_SCRIPT}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


read_back = _load_script()


def _file_body(name: str) -> str:
    """What a hosted copy equal to the repository's file holds."""
    return (_TEMPLATES / f"{name}.html").read_bytes().decode("utf-8")


def _saved_response(tmp_path: Path, **overrides: Any) -> Path:
    """A response shaped like ``AuthConfigResponse_Output``, holding the files' bodies."""
    body: dict[str, Any] = {
        "site_url": "http://localhost:3000",
        "mailer_subjects_confirmation": "Confirm Your Signup",
        "mailer_templates_confirmation_content": _file_body("confirmation"),
        "mailer_templates_recovery_content": _file_body("recovery"),
        "mailer_templates_invite_content": "<h2>You have been invited</h2>",
    }
    body.update(overrides)
    path = tmp_path / "auth-config.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def _change_one_character(text: str) -> str:
    """The same body with one character, inside the visible copy, replaced."""
    at = text.index("FamilyRoots")
    return text[:at] + "f" + text[at + 1 :]


def _named_as_differing(output: str) -> set[str]:
    return {
        line.split(":", 1)[0].removeprefix("DIFFERS ").strip()
        for line in output.splitlines()
        if line.startswith("DIFFERS ")
    }


def test_a_response_equal_to_the_files_exits_0(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = read_back.main(["--response", str(_saved_response(tmp_path))])

    out = capsys.readouterr().out
    assert code == 0, out
    assert _named_as_differing(out) == set()
    assert "match confirmation" in out
    assert "match recovery" in out


def test_one_changed_character_in_recovery_names_recovery_and_only_recovery(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    saved = _saved_response(
        tmp_path,
        mailer_templates_recovery_content=_change_one_character(_file_body("recovery")),
    )

    code = read_back.main(["--response", str(saved)])

    out = capsys.readouterr().out
    assert code != 0, out
    assert _named_as_differing(out) == {"recovery"}
    assert "match confirmation" in out


def test_a_trailing_newline_alone_is_a_difference(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Byte for byte: a hosted copy that lost the file's final newline is not the file.
    saved = _saved_response(
        tmp_path, mailer_templates_confirmation_content=_file_body("confirmation").rstrip("\n")
    )

    code = read_back.main(["--response", str(saved)])

    out = capsys.readouterr().out
    assert code != 0, out
    assert _named_as_differing(out) == {"confirmation"}


def test_both_changed_names_both(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    saved = _saved_response(
        tmp_path,
        mailer_templates_confirmation_content="<h2>Confirm your signup</h2>",
        mailer_templates_recovery_content=_change_one_character(_file_body("recovery")),
    )

    code = read_back.main(["--response", str(saved)])

    out = capsys.readouterr().out
    assert code != 0, out
    assert _named_as_differing(out) == {"confirmation", "recovery"}


@pytest.mark.parametrize("carried_as", ["null", "no key"])
def test_a_template_the_response_does_not_carry_is_named(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], carried_as: str
) -> None:
    # `null` is what the API answers for a template nobody has set.
    saved = _saved_response(tmp_path, mailer_templates_confirmation_content=None)
    if carried_as == "no key":
        body = json.loads(saved.read_text(encoding="utf-8"))
        del body["mailer_templates_confirmation_content"]
        saved.write_text(json.dumps(body), encoding="utf-8")

    code = read_back.main(["--response", str(saved)])

    out = capsys.readouterr().out
    assert code != 0, out
    assert _named_as_differing(out) == {"confirmation"}


def test_the_fetch_asks_the_management_api_for_the_auth_config_with_the_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sent: list[Any] = []
    body = _saved_response(tmp_path).read_bytes()

    class _Response:
        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self) -> bytes:
            return body

    def _urlopen(request: Any, timeout: float) -> _Response:
        sent.append(request)
        return _Response()

    monkeypatch.setattr(read_back.urllib.request, "urlopen", _urlopen)
    monkeypatch.setenv("SUPABASE_ACCESS_TOKEN", "sbp_test_token")

    code = read_back.main(["--project-ref", "bftqrkgbulwtbptnpfca"])

    assert code == 0, capsys.readouterr().out
    [request] = sent
    assert request.get_method() == "GET"
    assert (
        request.full_url == "https://api.supabase.com/v1/projects/bftqrkgbulwtbptnpfca/config/auth"
    )
    assert request.get_header("Authorization") == "Bearer sbp_test_token"


def test_the_fetch_without_a_token_exits_2_and_sends_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _urlopen(*_: object, **__: object) -> None:
        raise AssertionError("sent a request with no token")

    monkeypatch.setattr(read_back.urllib.request, "urlopen", _urlopen)
    monkeypatch.delenv("SUPABASE_ACCESS_TOKEN", raising=False)

    code = read_back.main(["--project-ref", "bftqrkgbulwtbptnpfca"])

    assert code == 2
    assert "SUPABASE_ACCESS_TOKEN" in capsys.readouterr().err


def test_a_project_ref_that_is_not_one_is_refused_before_any_request(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _urlopen(*_: object, **__: object) -> None:
        raise AssertionError("sent a request for a malformed ref")

    monkeypatch.setattr(read_back.urllib.request, "urlopen", _urlopen)
    monkeypatch.setenv("SUPABASE_ACCESS_TOKEN", "sbp_test_token")

    code = read_back.main(["--project-ref", "../../v1/organizations"])

    assert code == 2
    assert "project ref" in capsys.readouterr().err
