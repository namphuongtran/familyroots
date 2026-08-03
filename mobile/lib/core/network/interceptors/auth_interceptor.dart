import 'package:dio/dio.dart';

/// Attaches `Authorization: Bearer <token>` from the current Supabase session.
class AuthInterceptor extends Interceptor {
  AuthInterceptor(this._accessToken);
  final String? Function() _accessToken;

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    final token = _accessToken();
    if (token != null) {
      options.headers['Authorization'] = 'Bearer $token';
    }
    handler.next(options);
  }
}
