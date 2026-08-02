import '../../domain/shared/page.dart';
import 'api_exception.dart';

typedef Parse<T> = T Function(Object? json);

/// The ONLY place the canonical `{"data": ...}` envelope is opened (ADR-010).
/// No widget, notifier or repository ever sees the wrapper.
T unwrapData<T>(Object? body, Parse<T> parse) {
  if (body is! Map<String, Object?> || !body.containsKey('data')) {
    throw MalformedResponseException(body);
  }
  return parse(body['data']);
}

/// Cursor lists add `meta: {cursor, has_more, limit}`. Endpoints that return a
/// plain canonical array with no `meta` — `GET /me/clans` — are treated as a
/// single complete page.
Page<T> unwrapPage<T>(Object? body, Parse<T> parse) {
  if (body is! Map<String, Object?> || body['data'] is! List) {
    throw MalformedResponseException(body);
  }
  final items = (body['data']! as List<Object?>).map(parse).toList();
  final meta = body['meta'];
  if (meta is! Map<String, Object?>) {
    return Page<T>(
      items: items,
      cursor: null,
      hasMore: false,
      limit: items.length,
    );
  }
  return Page<T>(
    items: items,
    // Opaque: stored and replayed verbatim, never parsed.
    cursor: meta['cursor'] as String?,
    hasMore: meta['has_more'] as bool? ?? false,
    limit: meta['limit'] as int? ?? items.length,
  );
}
