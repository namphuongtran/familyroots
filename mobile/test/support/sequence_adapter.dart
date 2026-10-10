import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';

class Canned {
  const Canned(this.statusCode, this.body, {this.bearer});

  final int statusCode;
  final Object? body;

  /// When set, only a request carrying `Authorization: Bearer <bearer>` gets
  /// this response. Any other request gets the 401 `get_current_user` answers
  /// (`backend/app/core/security.py`): `missing_token` with no header,
  /// `invalid_token` with another one. Without it a canned authenticated
  /// endpoint answers 200 whatever the headers are, so a client that sends no
  /// token passes.
  final String? bearer;
}

/// Returns each canned response in order, repeating the last one thereafter,
/// and records every RequestOptions it saw.
class SequenceAdapter implements HttpClientAdapter {
  SequenceAdapter(this._responses);

  final List<Canned> _responses;
  final List<RequestOptions> received = <RequestOptions>[];

  int get callCount => received.length;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    received.add(options);
    final index = received.length <= _responses.length
        ? received.length - 1
        : _responses.length - 1;
    final canned = _responses[index];
    final (status, body) = _answer(canned, options.headers['Authorization']);
    return ResponseBody.fromString(
      jsonEncode(body),
      status,
      headers: <String, List<String>>{
        Headers.contentTypeHeader: <String>[Headers.jsonContentType],
      },
    );
  }

  (int, Object?) _answer(Canned canned, Object? authorization) {
    final bearer = canned.bearer;
    if (bearer == null || authorization == 'Bearer $bearer') {
      return (canned.statusCode, canned.body);
    }
    final code = authorization == null ? 'missing_token' : 'invalid_token';
    return (
      401,
      <String, Object?>{
        'error': <String, Object?>{
          'code': code,
          'message': code,
          'detail': <String, Object?>{},
        },
      },
    );
  }

  @override
  void close({bool force = false}) {}
}
