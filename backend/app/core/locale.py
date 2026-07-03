"""Request-scoped locale context.

Lives in ``app.core`` (not the middleware) so that readers like the translator
service never depend on the middleware layer: ``LanguageMiddleware`` *sets* the
contextvar per request; anything that renders localized text *reads* it.
"""

from contextvars import ContextVar

current_locale: ContextVar[str] = ContextVar("current_locale", default="vi")

SUPPORTED_LOCALES = {"vi", "en", "zh", "fr"}
