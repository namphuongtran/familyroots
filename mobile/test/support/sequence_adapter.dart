import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';

class Canned {
  const Canned(this.statusCode, this.body);
  final int statusCode;
  final Object? body;
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
    return ResponseBody.fromString(
      jsonEncode(canned.body),
      canned.statusCode,
      headers: <String, List<String>>{
        Headers.contentTypeHeader: <String>[Headers.jsonContentType],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}
