import 'package:dio/dio.dart';

import '../token_refresher.dart';

const _retriedFlag = 'familyroots.retried';

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
        options.extra[_retriedFlag] == true) {
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
