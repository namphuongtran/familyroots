import 'package:gotrue/gotrue.dart';

import '../../../core/network/api_exception.dart';

/// The Supabase half of the auth slice's transport (ADR-064).
///
/// Sign-in goes to Supabase directly, as the web's does (ADR-061 § 7), so the
/// session is created by the client that stores it (spec D6) and refreshes it
/// (D8). The access token every backend request carries and the refresh the
/// 401 interceptor runs are read from the same object, so they cannot disagree
/// with the sign-in about which session exists. `main.dart` builds one on
/// `Supabase.instance.client.auth`; a test builds one on a `GoTrueClient` with
/// a fake transport.
///
/// Like `ApiClient` for Dio, this is the one place gotrue's [AuthException]
/// is caught. Everything above it sees an [AppException].
class SupabaseAuth {
  SupabaseAuth(this._client);

  final GoTrueClient _client;

  /// Read by `accessTokenProvider` at request time. Null when signed out.
  String? get accessToken => _client.currentSession?.accessToken;

  /// One refresh, for `TokenRefresher`. Throws an [AppException] when there
  /// is no session to refresh or Supabase refuses it, which the refresh
  /// interceptor reads as "sign out".
  Future<String?> refresh() async {
    try {
      return (await _client.refreshSession()).session?.accessToken;
    } on AuthException catch (e) {
      throw _toAppException(e);
    }
  }

  /// `POST /token?grant_type=password`. On success the client holds the
  /// session, and `supabase_flutter` persists it to secure storage.
  ///
  /// Throws [SupabaseAuthException] when Supabase refuses, carrying GoTrue's
  /// code and [email], and [NetworkException] when nothing answered.
  Future<void> signInWithPassword({
    required String email,
    required String password,
  }) async {
    try {
      await _client.signInWithPassword(email: email, password: password);
    } on AuthException catch (e) {
      throw _toAppException(e, email: email);
    }
  }

  /// Ends the session here, then asks Supabase to revoke it server-side.
  ///
  /// [everywhere] revokes every session of this user, as the backend's
  /// `POST /auth/logout` did (`"global"`) and as the web's `signOut()` does by
  /// default. That is what a person pressing "sign out" gets. A cleanup the
  /// person did not ask for passes false and revokes only this device's
  /// session, so a sign-in that failed on a passing 5xx does not sign them out
  /// of the web as well.
  ///
  /// Never throws. gotrue drops the local session before it sends the revoke,
  /// so a failed revoke leaves nothing a later request could carry.
  Future<void> signOut({bool everywhere = true}) async {
    try {
      await _client.signOut(
        scope: everywhere ? SignOutScope.global : SignOutScope.local,
      );
    } on Object {
      // The revoke is best-effort, and the session is already gone locally.
      // `on Object`, not `on AuthException`: gotrue also clears the PKCE
      // verifier from secure storage on the way, and a platform error there
      // must not leave the app showing a session it no longer has.
    }
  }
}

AppException _toAppException(AuthException e, {String? email}) {
  // No status means no answer: offline, DNS, TLS. gotrue wraps all of them
  // in this one type, and a 5xx in it too, but with a status.
  if (e is AuthRetryableFetchException && e.statusCode == null) {
    return NetworkException(e);
  }
  return SupabaseAuthException(
    code: e.code,
    status: int.tryParse(e.statusCode ?? ''),
    email: email,
  );
}
