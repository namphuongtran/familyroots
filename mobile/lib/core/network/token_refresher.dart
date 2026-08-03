/// Single-flight: concurrent callers await the same in-flight future, so a
/// burst of 401s produces exactly one refresh.
class TokenRefresher {
  TokenRefresher(this._refresh);

  final Future<String?> Function() _refresh;
  Future<String?>? _inFlight;

  /// Underlying refreshes actually performed. Test-facing.
  int refreshCallCount = 0;

  Future<String?> refresh() {
    final existing = _inFlight;
    if (existing != null) return existing;
    refreshCallCount++;
    // whenComplete also clears the slot on error, so a failed refresh does
    // not wedge every later attempt.
    final future = _refresh().whenComplete(() => _inFlight = null);
    _inFlight = future;
    return future;
  }
}
