"""OpenAPI must expose typed response schemas — client codegen depends on it.

Zero response_model usage meant every 2xx in the generated OpenAPI was a
bare untyped object: openapi-typescript / Dio codegen produced
Record<string, unknown> for all endpoints and clients hand-wrote types that
silently drift. Runtime response_model is deliberately NOT used (it would
re-validate and break the sparse `fields=` responses); instead every route
declares its envelope via `responses=` — documentation-only, zero runtime
change — plus the standard error envelope.

These tests pin representative routes across every v1 router, including
tree and platform-admin.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.main import create_app


@pytest.fixture(scope="module")
def openapi() -> dict[str, Any]:
    return create_app().openapi()


def _response_schema(openapi: dict[str, Any], path: str, method: str, status: str) -> str:
    op = openapi["paths"][path][method]
    content = op["responses"][status]["content"]["application/json"]
    ref: str = content["schema"]["$ref"]
    return ref


def test_events_list_is_page_envelope_of_event_response(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/events", "get", "200")
    assert "PageEnvelope" in ref and "EventResponse" in ref, ref


def test_event_get_is_envelope_of_event_response(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/events/{event_id}", "get", "200")
    assert "Envelope" in ref and "EventResponse" in ref, ref


def test_event_create_declares_201_envelope(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/events", "post", "201")
    assert "Envelope" in ref and "EventResponse" in ref, ref


def test_persons_list_is_page_envelope(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/persons", "get", "200")
    assert "PageEnvelope" in ref and "PersonResponse" in ref, ref


def test_login_is_envelope_of_login_response(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/auth/login", "post", "200")
    assert "Envelope" in ref and "LoginResponse" in ref, ref


def test_error_envelope_is_documented(openapi: dict[str, Any]) -> None:
    op = openapi["paths"]["/api/v1/events/{event_id}"]["get"]
    assert "404" in op["responses"], sorted(op["responses"])
    ref = op["responses"]["404"]["content"]["application/json"]["schema"]["$ref"]
    assert "ErrorEnvelope" in ref, ref


def test_envelope_component_shapes(openapi: dict[str, Any]) -> None:
    schemas = openapi["components"]["schemas"]
    error = next(v for k, v in schemas.items() if k == "ErrorEnvelope")
    assert set(error["properties"]) == {"error"}
    meta = next(v for k, v in schemas.items() if k == "ListMeta")
    assert set(meta["properties"]) == {"cursor", "has_more", "limit"}


def test_platform_clans_is_page_envelope(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/platform/clans", "get", "200")
    assert "PageEnvelope" in ref and "ClanSummaryResponse" in ref, ref


def test_platform_clan_detail_is_envelope(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/platform/clans/{clan_id}", "get", "200")
    assert "Envelope" in ref and "ClanDetailResponse" in ref, ref


def test_platform_metrics_is_envelope(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/platform/metrics", "get", "200")
    assert "Envelope" in ref and "PlatformMetricsResponse" in ref, ref


def test_tree_full_is_envelope_of_tree_response(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/tree", "get", "200")
    assert "Envelope" in ref and "TreeResponse" in ref, ref


def test_tree_ancestors_is_envelope_list_of_detail_node(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/tree/ancestors/{person_id}", "get", "200")
    assert "Envelope" in ref and "TreeNodeDetail" in ref, ref


def test_tree_path_is_envelope_of_relationship_path(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/tree/path", "get", "200")
    assert "Envelope" in ref and "RelationshipPathResponse" in ref, ref


def test_auth_onboard_is_created_envelope_of_register_response(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/auth/onboard", "post", "201")
    assert "Envelope" in ref and "RegisterResponse" in ref, ref


def test_auth_logout_is_envelope_of_message(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/auth/logout", "post", "200")
    assert "Envelope" in ref and "MessageData" in ref, ref


def test_persons_marriages_is_envelope_list_of_marriage(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/persons/{person_id}/marriages", "get", "200")
    assert "Envelope" in ref and "MarriageResponse" in ref, ref


def test_persons_timeline_is_envelope_list_of_timeline_event(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/persons/{person_id}/timeline", "get", "200")
    assert "Envelope" in ref and "TimelineEvent" in ref, ref
