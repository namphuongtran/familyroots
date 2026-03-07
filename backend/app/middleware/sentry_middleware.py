"""Sentry middleware — capture exceptions and performance data."""

# TODO: implement in Prompt 2
#
# This middleware will:
# - Attach request context (user, clan_id, path) to Sentry scope
# - Capture unhandled exceptions with full context
# - Start Sentry transaction for performance monitoring
