"""Production config must fail fast on insecure values."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _build(**overrides):
    # _env_file=None so the developer's local .env does not interfere.
    return Settings(_env_file=None, **overrides)


def test_dev_defaults_ok():
    s = _build(APP_ENV="development")
    assert s.APP_DEBUG is False  # new default


def test_production_rejects_default_secret():
    with pytest.raises(ValidationError):
        _build(APP_ENV="production", APP_SECRET_KEY="change-me-in-production")


def test_production_rejects_debug_true():
    with pytest.raises(ValidationError):
        _build(APP_ENV="production", APP_SECRET_KEY="a-real-secret", APP_DEBUG=True)


def test_production_rejects_wildcard_allowed_hosts():
    with pytest.raises(ValidationError):
        _build(APP_ENV="production", APP_SECRET_KEY="a-real-secret", APP_DEBUG=False)


_PROD_SAFE = {
    "APP_ENV": "production",
    "APP_SECRET_KEY": "a-real-secret",
    "APP_DEBUG": False,
    "ALLOWED_HOSTS": ["example.com"],
    "DATABASE_URL": "postgresql+psycopg://u:p@db.prod.internal:5432/familyroots",
    "CORS_ORIGINS": ["https://app.example.com"],
    "INVITE_LINK_ORIGIN": "https://app.example.com",
    # Auth config is required in production (fail fast instead of per-request 503s).
    "SUPABASE_URL": "https://proj.supabase.co",
    "SUPABASE_ANON_KEY": "sb_publishable_x",
    "SUPABASE_SERVICE_ROLE_KEY": "sb_secret_x",
    # Production must decide XFF trust explicitly; Render (proxied) → true.
    "RATE_LIMIT_TRUST_FORWARDED_FOR": True,
}


def test_production_with_safe_values_ok():
    s = _build(**_PROD_SAFE)
    assert s.APP_ENV == "production"


def test_production_rejects_localhost_database_url():
    with pytest.raises(ValidationError):
        _build(**{**_PROD_SAFE, "DATABASE_URL": "postgresql+psycopg://u:p@localhost:5432/x"})


def test_production_rejects_localhost_cors_origin():
    with pytest.raises(ValidationError):
        _build(**{**_PROD_SAFE, "CORS_ORIGINS": ["http://localhost:3000"]})


@pytest.mark.parametrize(
    "origin", ["", "http://localhost:3000", "http://127.0.0.1:3102", "https://localhost"]
)
def test_production_rejects_an_invite_link_origin_no_relative_can_open(origin: str) -> None:
    """ADR-062. The admin shares `<INVITE_LINK_ORIGIN>/<locale>/invitations/<token>` with a
    relative, so an empty or loopback origin hands out a link that opens nothing. `match`
    names the setting: the baseline constructs, so the refusal is this setting's."""
    with pytest.raises(ValidationError, match="INVITE_LINK_ORIGIN"):
        _build(**{**_PROD_SAFE, "INVITE_LINK_ORIGIN": origin})


def test_production_boots_with_a_real_invite_link_origin() -> None:
    _build(**{**_PROD_SAFE, "INVITE_LINK_ORIGIN": "https://app.example.test"})


def test_production_requires_explicit_forwarded_for_decision():
    # Deployed behind a proxy (Render) with trust left unset, every client shares
    # the proxy's rate bucket and audit IPs record the proxy — production must
    # make the XFF-trust decision explicitly, either way.
    prod = {k: v for k, v in _PROD_SAFE.items() if k != "RATE_LIMIT_TRUST_FORWARDED_FOR"}
    with pytest.raises(ValidationError):
        _build(**prod)


def test_production_accepts_explicit_forwarded_for_true():
    s = _build(**{**_PROD_SAFE, "RATE_LIMIT_TRUST_FORWARDED_FOR": True})
    assert s.trust_forwarded_for is True


def test_production_accepts_explicit_forwarded_for_false():
    # Direct exposure (no proxy) is a legitimate deployment — trusting XFF there
    # would let clients spoof it — so an explicit False must also pass.
    s = _build(**{**_PROD_SAFE, "RATE_LIMIT_TRUST_FORWARDED_FOR": False})
    assert s.trust_forwarded_for is False


def test_dev_unset_forwarded_for_resolves_false():
    s = _build(APP_ENV="development")
    assert s.trust_forwarded_for is False


def test_metrics_enabled_without_a_token_is_rejected():
    """Enabled-but-unprotected would publish request volumes and route names to
    anyone — reject it in every environment, not just production."""
    with pytest.raises(ValidationError):
        _build(APP_ENV="development", METRICS_ENABLED=True, METRICS_TOKEN="")


def test_metrics_enabled_with_a_token_is_accepted():
    s = _build(APP_ENV="development", METRICS_ENABLED=True, METRICS_TOKEN=_STRONG_METRICS_TOKEN)
    assert s.METRICS_ENABLED is True


# ─── METRICS_TOKEN length floor (ADR-040) ─────────────────────────────────────

# 49 characters, 23 distinct — well past the floor. Assembled rather than
# written out: a single 32-char hex literal is indistinguishable from a leaked
# credential, and gitleaks flagged the first version of this line as `generic-api-key`.
# An allowlist entry would train everyone to wave through exactly the shape the scanner
# exists to catch, so the fixture is built from obviously-synthetic pieces instead.
_STRONG_METRICS_TOKEN = "not-a-real-token-" + "0123456789abcdef" * 2


def test_metrics_enabled_rejects_a_short_token():
    """Refusing to boot is the primary guarantee. Settings are read once per process
    (@lru_cache, no reload path), so the blast radius is a failed deploy — on Render
    the previous release keeps serving — never a running instance dropped mid-flight.
    The alternative, booting and quietly serving route names and request volumes
    behind a guessable token, is strictly worse."""
    with pytest.raises(ValidationError):
        _build(APP_ENV="development", METRICS_ENABLED=True, METRICS_TOKEN="s3cret")


def test_metrics_enabled_rejects_a_single_character_token():
    """The value §3.1 named: a one-character METRICS_TOKEN used to be accepted."""
    with pytest.raises(ValidationError):
        _build(APP_ENV="development", METRICS_ENABLED=True, METRICS_TOKEN="x")


def test_metrics_enabled_rejects_a_long_but_degenerate_token():
    """A length floor alone accepts 64 identical characters. Not entropy — see
    ADR-040 — but the likeliest way a compliant-looking token is worthless."""
    with pytest.raises(ValidationError):
        _build(APP_ENV="development", METRICS_ENABLED=True, METRICS_TOKEN="a" * 64)


def test_metrics_disabled_does_not_police_the_token():
    """A leftover value in a .env with the endpoint switched off protects nothing and
    exposes nothing; failing boot over it would be noise, and would punish exactly
    the safe configuration."""
    s = _build(APP_ENV="development", METRICS_ENABLED=False, METRICS_TOKEN="x")
    assert s.METRICS_ENABLED is False


def test_production_with_metrics_enabled_and_a_real_token_ok():
    s = _build(**_PROD_SAFE, METRICS_ENABLED=True, METRICS_TOKEN=_STRONG_METRICS_TOKEN)
    assert s.METRICS_TOKEN == _STRONG_METRICS_TOKEN


def test_the_error_names_the_setting_and_the_remedy():
    """A boot failure an operator cannot act on is an outage, not a guardrail."""
    with pytest.raises(ValidationError) as exc:
        _build(APP_ENV="development", METRICS_ENABLED=True, METRICS_TOKEN="s3cret")
    message = str(exc.value)
    assert "METRICS_TOKEN" in message
    assert "openssl rand -hex 32" in message


# ─── CRON_SECRET with the in-process scheduler off (ADR-065) ──────────────────

# Assembled for the same reason as _STRONG_METRICS_TOKEN above.
_STRONG_CRON_SECRET = "not-a-real-secret-" + "0123456789abcdef" * 2


@pytest.mark.parametrize(
    "secret",
    ["", "short-secret", _STRONG_CRON_SECRET[:31], "a" * 64],
    ids=["empty", "short", "one-below-the-floor", "degenerate"],
)
def test_production_without_the_scheduler_refuses_a_weak_cron_secret(secret: str) -> None:
    """With SCHEDULER_ENABLED=false the /internal/cron/* routes are the only trigger of the
    giỗ reminders and the purge. An empty secret leaves both jobs never running and nothing
    raising; a weak one guards them with a guessable value. `match` names the setting, so
    the refusal is this rule's and not another production check's: the baseline boots."""
    with pytest.raises(ValidationError, match="CRON_SECRET"):
        _build(**{**_PROD_SAFE, "SCHEDULER_ENABLED": False, "CRON_SECRET": secret})


def test_production_without_the_scheduler_boots_with_a_strong_cron_secret() -> None:
    s = _build(**{**_PROD_SAFE, "SCHEDULER_ENABLED": False, "CRON_SECRET": _STRONG_CRON_SECRET})
    assert s.SCHEDULER_ENABLED is False


def test_production_with_the_scheduler_does_not_require_a_cron_secret() -> None:
    """The control: a long-running deployment keeps APScheduler and needs no cron route."""
    s = _build(**_PROD_SAFE)
    assert s.SCHEDULER_ENABLED is True
    assert s.CRON_SECRET == ""


def test_development_without_the_scheduler_does_not_police_the_cron_secret() -> None:
    """Outside production nothing depends on the routes. The handler still refuses a weak
    secret at request time (tests/unit/test_cron_endpoints.py)."""
    s = _build(APP_ENV="development", SCHEDULER_ENABLED=False, CRON_SECRET="")
    assert s.SCHEDULER_ENABLED is False


def test_the_cron_secret_error_names_the_remedy() -> None:
    with pytest.raises(ValidationError) as exc:
        _build(**{**_PROD_SAFE, "SCHEDULER_ENABLED": False})
    assert "openssl rand -hex 32" in str(exc.value)
