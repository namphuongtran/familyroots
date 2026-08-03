import 'package:dio/dio.dart';

/// Routes that must NOT carry `X-Current-Clan-Id`: `/auth/*`, `/me/clans`,
/// `/me/clans/{id}/select`, `/invitations/{token}/accept`, `/platform/*`.
bool isClanScoped(String path) {
  const exempt = <String>['/auth/', '/me/clans', '/platform/'];
  for (final prefix in exempt) {
    if (path.startsWith(prefix)) return false;
  }
  if (path.startsWith('/invitations/') && path.endsWith('/accept')) {
    return false;
  }
  return true;
}

/// Sent on every clan-scoped request, including for single-clan users, so
/// behaviour stays deterministic if the user later joins a second clan.
class ClanInterceptor extends Interceptor {
  ClanInterceptor(this._currentClanId);
  final String? Function() _currentClanId;

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    final clanId = _currentClanId();
    if (clanId != null && isClanScoped(options.path)) {
      options.headers['X-Current-Clan-Id'] = clanId;
    }
    handler.next(options);
  }
}
