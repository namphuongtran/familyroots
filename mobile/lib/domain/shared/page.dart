/// One page of a cursor-paginated list.
class Page<T> {
  const Page({
    required this.items,
    required this.cursor,
    required this.hasMore,
    required this.limit,
  });

  final List<T> items;

  /// Opaque (ADR-010). Never parsed, constructed or repaired by the client —
  /// pass it back verbatim or drop it.
  final String? cursor;
  final bool hasMore;
  final int limit;

  static Page<T> empty<T>() =>
      Page<T>(items: <T>[], cursor: null, hasMore: false, limit: 0);
}
