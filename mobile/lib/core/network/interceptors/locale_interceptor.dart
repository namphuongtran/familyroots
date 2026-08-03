import 'package:dio/dio.dart';

/// Drives all server-localised text. The app owns its locale and never reads
/// the backend's `preferred_locale`, which always returns "vi" (spec R3).
class LocaleInterceptor extends Interceptor {
  LocaleInterceptor(this._locale);
  final String Function() _locale;

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    options.headers['Accept-Language'] = _locale();
    handler.next(options);
  }
}
