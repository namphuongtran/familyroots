"""App-assembly smoke test.

Building the app imports every router, which imports every DI provider module — so
this catches import/wiring breakage in the composition root at test time rather
than as a 500 on the first request. Does not start the lifespan (no DB / network).
"""

from app.main import create_app

# A representative slice of routes that must always be mounted.
EXPECTED_ROUTES = {
    "/health",
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/me/clans",
    "/api/v1/persons",
    "/api/v1/relationships/marriages",
}


def test_app_builds_and_mounts_core_routes() -> None:
    app = create_app()
    paths = {getattr(r, "path", None) for r in app.routes}
    missing = EXPECTED_ROUTES - paths
    assert not missing, f"routes missing from assembled app: {sorted(missing)}"
