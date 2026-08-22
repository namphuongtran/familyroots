import 'package:dio/dio.dart';

import '../token_refresher.dart';

const _retriedFlag = 'familyroots.retried';

/// Endpoints that carry no bearer token, taken from the backend's own OpenAPI
/// (`security` absent on all five). A 401 from one of these cannot mean "the
/// access token expired" — there is no token in the request to expire. It is an
/// *answer*: wrong password, invalid refresh token, unknown email.
///
/// Refreshing anyway costs a wasted round-trip, and signing out when that
/// refresh fails means **a mistyped password can log you out**.
const _unauthenticatedPaths = <String>{
  '/auth/login',
  '/auth/refresh',
  '/auth/register',
  '/auth/forgot-password',
  '/auth/resend-verification',
};

/// True when the request never carried a token, so a 401 is the server's answer
/// rather than an expiry signal. Matches on suffix because `baseUrl` may or may
/// not already include the `/api/v1` prefix.
bool isUnauthenticatedEndpoint(String path) {
  for (final p in _unauthenticatedPaths) {
    if (path == p || path.endsWith(p)) return true;
  }
  return false;
}

/// On 401: one shared refresh, concurrent 401s queued behind it, retry the
/// original request exactly once; on refresh failure, sign out.
class RefreshInterceptor extends Interceptor {
  RefreshInterceptor({
    required this.refresher,
    required this.retryDio,
    required this.onSignOut,
  });

  final TokenRefresher refresher;
  final Dio retryDio;
  final void Function() onSignOut;

  @override
  Future<void> onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    // A caller-initiated cancellation is rethrown unchanged and is never
    // reported as a network or auth failure.
    if (err.type == DioExceptionType.cancel) {
      handler.next(err);
      return;
    }

    final options = err.requestOptions;
    if (err.response?.statusCode != 401 ||
        options.extra[_retriedFlag] == true ||
        // A 401 here is an answer, not an expiry — see _unauthenticatedPaths.
        isUnauthenticatedEndpoint(options.path)) {
      handler.next(err);
      return;
    }

    final String? token;
    try {
      token = await refresher.refresh();
    } on Object {
      onSignOut();
      handler.next(err);
      return;
    }

    if (token == null) {
      onSignOut();
      handler.next(err);
      return;
    }

    options.extra[_retriedFlag] = true;
    options.headers['Authorization'] = 'Bearer $token';
    try {
      handler.resolve(await retryDio.fetch<Object?>(options));
    } on DioException catch (e) {
      handler.next(e);
    }
  }
}
