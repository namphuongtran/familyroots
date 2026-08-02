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
    """Assert against the OpenAPI schema, not ``app.routes``.

    FastAPI 0.141 stopped flattening ``include_router`` children into
    ``app.routes``; it stores lazy ``_IncludedRouter`` wrappers there instead and
    resolves them per request. Walking ``app.routes`` therefore reports only the
    four routes declared directly on the app, and the old assertion passed for
    years only because the flattening happened to be eager. The schema is also
    the better subject: it is what clients bind to.
    """
    app = create_app()
    paths = set(app.openapi()["paths"])
    missing = EXPECTED_ROUTES - paths
    assert not missing, f"routes missing from assembled app: {sorted(missing)}"
