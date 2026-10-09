"""The two auth email templates, and the two configs that carry them (#202, ADR-063 § 1, 6 and 7).

What a person receives is read by hand, in the local stack's Mailpit, and by the e2e walks that
take their link from the mail (``web/e2e/auth/mail.ts``). This file pins what those readings
cannot be repeated for on every change:

- **The link.** Every ``href`` in each body is exactly the ADR-063 § 1 URL, read through an HTML
  parser, so an entity or a stray ``{{ .ConfirmationURL }}`` cannot hide in the markup.
- **The order.** The body's visible text reads Vietnamese first, then English (§ 7). It is read
  from the text itself, not from the ``lang`` attributes that label it.
- **Where each config reads its body from.** The CLI resolves ``content_path`` against the
  workdir, the directory that holds ``supabase/`` (measured with CLI 2.115.0 on 2026-10-08:
  ``supabase status --workdir`` fails with ENOENT on a path relative to ``supabase/``). CLI
  2.120.0's ``config push`` also refuses a path that resolves outside the workdir (measured
  2026-10-09). So the local and the hosted-only config name different strings for the same file,
  and the hosted one's must stay inside ``supabase/``.
- **What the hosted-only config declares**, and only that. A push writes every property its file
  declares (``docs/ops/supabase-hosted-project.md`` trap 4), so the file must declare the two
  template tables and nothing else. That is necessary and not sufficient: what a push from it
  *writes* also depends on the CLI. 2.115.0 sends its defaults for every undeclared property, from
  this same file, and only the pinned 2.120.0 does not (§ 4a). No test here can read a push; the
  pin in the documented command is that half.
"""

import tomllib
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_TEMPLATES = _REPO / "supabase" / "templates"
_LOCAL_WORKDIR = _REPO
# `supabase/supabase/config.toml`, pushed with `--workdir supabase`.
_HOSTED_WORKDIR = _REPO / "supabase"

# ADR-063 § 1, verbatim.
_LINKS = {
    "confirmation": "{{ .SiteURL }}/verify-email/confirm?token_hash={{ .TokenHash }}&type=email",
    "recovery": "{{ .SiteURL }}/reset-password?token_hash={{ .TokenHash }}&type=recovery",
}


# Letters Vietnamese writes and English does not. Every Vietnamese sentence in both bodies has one.
_VIETNAMESE_LETTERS = frozenset(
    "ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
)


class _Reader(HTMLParser):
    """Every link target, and every run of visible body text, in document order."""

    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str | None] = []
        self.texts: list[str] = []
        self._in_body = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "body":
            self._in_body = True
        if tag == "a":
            self.hrefs.append(dict(attrs).get("href"))

    def handle_data(self, data: str) -> None:
        if self._in_body and data.strip():
            self.texts.append(data.strip())

    def languages(self) -> list[str]:
        """The language of each run, ``vi`` or ``en`` by its letters, with repeats collapsed."""
        order: list[str] = []
        for text in self.texts:
            language = "vi" if _VIETNAMESE_LETTERS & set(text.lower()) else "en"
            if not order or order[-1] != language:
                order.append(language)
        return order


def _read(name: str) -> _Reader:
    reader = _Reader()
    reader.feed((_TEMPLATES / f"{name}.html").read_text(encoding="utf-8"))
    reader.close()
    return reader


def _config(workdir: Path) -> dict[str, Any]:
    with (workdir / "supabase" / "config.toml").open("rb") as file:
        return tomllib.load(file)


def _templates_of(config: dict[str, Any]) -> dict[str, Any]:
    templates: dict[str, Any] = config["auth"]["email"]["template"]
    return templates


@pytest.mark.parametrize("name", sorted(_LINKS))
def test_every_link_in_the_body_is_the_adr_063_link(name: str) -> None:
    hrefs = _read(name).hrefs

    assert hrefs, f"{name}.html links nothing"
    assert set(hrefs) == {_LINKS[name]}


@pytest.mark.parametrize("name", sorted(_LINKS))
def test_the_body_uses_neither_default_variable(name: str) -> None:
    body = (_TEMPLATES / f"{name}.html").read_text(encoding="utf-8")

    for variable in (".ConfirmationURL", ".RedirectTo"):
        assert variable not in body, f"{name}.html uses {variable}"


@pytest.mark.parametrize("name", sorted(_LINKS))
def test_the_body_reads_vietnamese_then_english(name: str) -> None:
    # Every Vietnamese run comes before every English one: one switch, from vi to en.
    assert _read(name).languages() == ["vi", "en"], _read(name).texts


@pytest.mark.parametrize(
    ("workdir", "label"), [(_LOCAL_WORKDIR, "local"), (_HOSTED_WORKDIR, "hosted")]
)
def test_each_config_reads_each_body_from_its_file(workdir: Path, label: str) -> None:
    templates = _templates_of(_config(workdir))

    for name in _LINKS:
        resolved = (workdir / templates[name]["content_path"]).resolve()
        assert resolved == (_TEMPLATES / f"{name}.html").resolve(), (
            f"the {label} config's {name} content_path resolves to {resolved}"
        )
        # CLI 2.120.0: "resolves outside the project root … move the file inside the project".
        assert resolved.is_relative_to(workdir.resolve()), (
            f"the {label} config's {name} content_path leaves its workdir"
        )


def test_the_hosted_config_declares_only_the_two_template_tables() -> None:
    config = _config(_HOSTED_WORKDIR)

    assert set(config) == {"auth"}, sorted(config)
    assert set(config["auth"]) == {"email"}
    assert set(config["auth"]["email"]) == {"template"}
    templates = _templates_of(config)
    assert set(templates) == set(_LINKS)
    for name, table in templates.items():
        assert set(table) == {"subject", "content_path"}, f"{name}: {sorted(table)}"


def test_the_two_configs_give_each_email_the_same_subject() -> None:
    local = _templates_of(_config(_LOCAL_WORKDIR))
    hosted = _templates_of(_config(_HOSTED_WORKDIR))

    for name in _LINKS:
        assert local[name]["subject"] == hosted[name]["subject"]
        assert local[name]["subject"].strip()
