"""Language middleware — extract Accept-Language header and set locale in request context."""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.locale import SUPPORTED_LOCALES, current_locale


class LanguageMiddleware(BaseHTTPMiddleware):
    """Extract Accept-Language header and set the current locale context var."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        lang = request.headers.get("Accept-Language", "vi").split(",")[0][:2]
        locale = lang if lang in SUPPORTED_LOCALES else "vi"
        token = current_locale.set(locale)
        try:
            response = await call_next(request)
        finally:
            current_locale.reset(token)
        return response
