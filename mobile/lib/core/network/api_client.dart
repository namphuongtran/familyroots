import 'package:dio/dio.dart' as dio;

import '../../domain/shared/page.dart';
import 'api_exception.dart';
import 'envelope.dart';

/// The only class that talks to Dio. Everything above it sees domain types and
/// AppException — never DioException, never `{"data": ...}`.
class ApiClient {
  ApiClient(this._dio);

  final dio.Dio _dio;

  Future<T> getOne<T>(
    String path, {
    Map<String, Object?>? query,
    dio.CancelToken? cancelToken,
    required Parse<T> parse,
  }) => _guard(() async {
    final res = await _dio.get<Object?>(
      path,
      queryParameters: query,
      cancelToken: cancelToken,
    );
    return unwrapData<T>(res.data, parse);
  });

  Future<Page<T>> getPage<T>(
    String path, {
    String? cursor,
    int? limit,
    Map<String, Object?>? query,
    dio.CancelToken? cancelToken,
    required Parse<T> parse,
  }) => _guard(() async {
    final res = await _dio.get<Object?>(
      path,
      queryParameters: <String, Object?>{
        ...?query,
        // Opaque: replayed verbatim, never constructed or parsed.
        // `?x` is Dart 3.12's null-aware element — the entry is omitted when
        // the value is null. `if (x != null)` trips use_null_aware_elements.
        'cursor': ?cursor,
        'limit': ?limit,
      },
      cancelToken: cancelToken,
    );
    return unwrapPage<T>(res.data, parse);
  });

  Future<T> post<T>(
    String path, {
    Object? body,
    dio.CancelToken? cancelToken,
    required Parse<T> parse,
  }) => _guard(() async {
    final res = await _dio.post<Object?>(
      path,
      data: body,
      cancelToken: cancelToken,
    );
    return unwrapData<T>(res.data, parse);
  });

  Future<T> _guard<T>(Future<T> Function() run) async {
    try {
      return await run();
    } on dio.DioException catch (e) {
      // A caller-initiated cancellation is rethrown unchanged.
      if (e.type == dio.DioExceptionType.cancel) rethrow;
      throw toAppException(e);
    }
  }
}

/// Maps a DioException onto the sealed client taxonomy.
AppException toAppException(dio.DioException e) {
  switch (e.type) {
    case dio.DioExceptionType.connectionTimeout:
    case dio.DioExceptionType.sendTimeout:
    case dio.DioExceptionType.receiveTimeout:
    // dio 5.11 added transformTimeout; the switch must be exhaustive.
    case dio.DioExceptionType.transformTimeout:
      return const TimeoutException();
    case dio.DioExceptionType.connectionError:
    case dio.DioExceptionType.unknown:
    case dio.DioExceptionType.badCertificate:
      return NetworkException(e.error ?? e);
    case dio.DioExceptionType.cancel:
      return NetworkException(e);
    case dio.DioExceptionType.badResponse:
      final res = e.response;
      final body = res?.data;
      if (body is Map<String, Object?> &&
          body['error'] is Map<String, Object?>) {
        final err = body['error']! as Map<String, Object?>;
        final code = err['code'];
        final message = err['message'];
        if (code is String && message is String) {
          return ApiException(
            code: code,
            message: message,
            status: res?.statusCode ?? 0,
            detail:
                (err['detail'] as Map<String, Object?>?) ??
                const <String, Object?>{},
            traceId: _traceIdOf(res),
          );
        }
      }
      return MalformedResponseException(body);
  }
}

/// The 32-hex trace-id half of the request's traceparent, surfaced to the user
/// so a report links to the exact backend log line.
String? _traceIdOf(dio.Response<Object?>? res) {
  final tp = res?.requestOptions.headers['traceparent'];
  if (tp is! String) return null;
  final parts = tp.split('-');
  return parts.length >= 2 ? parts[1] : null;
}
