/// The client-side error taxonomy. Every failure that reaches a notifier is
/// one of these four; nothing above `core/network` sees a `DioException`.
sealed class AppException implements Exception {
  const AppException();
}

/// Any response carrying an `{"error": {...}}` body.
final class ApiException extends AppException {
  const ApiException({
    required this.code,
    required this.message,
    required this.status,
    this.detail = const <String, Object?>{},
    this.traceId,
  });

  /// Stable machine code — branch on this.
  final String code;

  /// Already localised server-side from Accept-Language. Display directly;
  /// never parse it, never translate it client-side.
  final String message;
  final int status;
  final Map<String, Object?> detail;

  /// Short id surfaced to the user so a report links to a backend log line.
  final String? traceId;

  int? get currentVersion => detail['current_version'] as int?;
  int? get retryAfter => detail['retry_after'] as int?;

  @override
  String toString() => 'ApiException($status $code): $message';
}

/// Transport, DNS, offline.
final class NetworkException extends AppException {
  const NetworkException(this.cause);
  final Object? cause;
}

/// Deadline exceeded.
final class TimeoutException extends AppException {
  const TimeoutException();
}

/// The body did not match the canonical envelope.
final class MalformedResponseException extends AppException {
  const MalformedResponseException(this.body);
  final Object? body;
}

/// What the app should do about a backend error code.
enum PolicyAction {
  none,
  refreshThenRetry,
  signOut,
  resendVerification,
  blockedAccount,
  clanBlocked,
  pendingOrOnboarding,
  clanPicker,
  clearClanAndReResolve,
  reloadAndReapply,
  founderOnboarding,
  backOff,
  transientOutage,
  dropCursorRefetch,
}

/// The single mapping from a backend error code to a routing decision.
/// Every UI branch on an error goes through here. `status` only disambiguates
/// unknown codes; known codes are decided by `code` alone.
PolicyAction policyActionFor(String code, {int? status}) {
  switch (code) {
    case 'missing_token':
    case 'invalid_token':
    case 'unauthorized':
      return PolicyAction.refreshThenRetry;
    case 'auth.invalid_refresh_token':
      return PolicyAction.signOut;
    // 401, but NOT a stale token: the login itself is what failed, so there is
    // nothing to refresh. The server message is already localised — show it.
    // Without this case it fell through to the `status == 401` default below.
    case 'auth.invalid_credentials':
      return PolicyAction.none;
    case 'email_not_verified':
      return PolicyAction.resendVerification;
    case 'account_deactivated':
      return PolicyAction.blockedAccount;
    case 'clan_suspended':
      return PolicyAction.clanBlocked;
    case 'no_approved_clan_membership':
    case 'clan_membership_required':
      return PolicyAction.pendingOrOnboarding;
    case 'multiple_clans_no_selection':
      return PolicyAction.clanPicker;
    case 'invalid_clan_id_format':
      return PolicyAction.clearClanAndReResolve;
    case 'stale_write':
      return PolicyAction.reloadAndReapply;
    case 'clan_founder_not_found':
      return PolicyAction.founderOnboarding;
    case 'rate_limited':
      return PolicyAction.backOff;
    case 'auth_provider_unavailable':
    case 'storage_unavailable':
    case 'database_unavailable':
      return PolicyAction.transientOutage;
    case 'invalid_cursor':
      return PolicyAction.dropCursorRefetch;
    default:
      if (status == 401) return PolicyAction.refreshThenRetry;
      return PolicyAction.none;
  }
}
