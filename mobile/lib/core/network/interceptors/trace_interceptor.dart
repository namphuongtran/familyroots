import 'package:dio/dio.dart';

import '../../observability/traceparent.dart';

/// W3C trace context (ADR-033): a crash on a phone links to the exact backend
/// log line.
class TraceInterceptor extends Interceptor {
  TraceInterceptor({String Function()? generator})
    : _generator = generator ?? newTraceparent;

  final String Function() _generator;

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    options.headers['traceparent'] = _generator();
    handler.next(options);
  }
}
