import 'dart:math';

final _rng = Random.secure();

String _hex(int bytes) {
  final buffer = StringBuffer();
  for (var i = 0; i < bytes; i++) {
    buffer.write(_rng.nextInt(256).toRadixString(16).padLeft(2, '0'));
  }
  return buffer.toString();
}

/// A W3C trace-context `traceparent` (ADR-033), so a mobile span joins the
/// backend trace: `00-<32 hex trace-id>-<16 hex span-id>-<2 hex flags>`.
String newTraceparent({bool sampled = true}) =>
    '00-${_hex(16)}-${_hex(8)}-${sampled ? '01' : '00'}';
