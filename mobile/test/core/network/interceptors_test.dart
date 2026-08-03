import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:family_roots_mobile/core/network/interceptors/auth_interceptor.dart';
import 'package:family_roots_mobile/core/network/interceptors/clan_interceptor.dart';
import 'package:family_roots_mobile/core/network/interceptors/locale_interceptor.dart';
import 'package:family_roots_mobile/core/network/interceptors/trace_interceptor.dart';
import 'package:family_roots_mobile/core/observability/traceparent.dart';

import '../../support/sequence_adapter.dart';

Dio _dio(SequenceAdapter a) =>
    Dio(BaseOptions(baseUrl: 'https://api.test/api/v1'))..httpClientAdapter = a;

SequenceAdapter _ok() => SequenceAdapter(<Canned>[
  const Canned(200, <String, Object?>{'data': null}),
]);

void main() {
  group('isClanScoped', () {
    test('clan-scoped routes', () {
      expect(isClanScoped('/persons'), isTrue);
      expect(isClanScoped('/tree'), isTrue);
      expect(isClanScoped('/events'), isTrue);
      expect(isClanScoped('/documents'), isTrue);
      expect(isClanScoped('/relationships/marriages'), isTrue);
      expect(isClanScoped('/branches'), isTrue);
      expect(isClanScoped('/claims'), isTrue);
      expect(isClanScoped('/clans/me/founder'), isTrue);
    });

    test('exempt routes', () {
      expect(isClanScoped('/auth/login'), isFalse);
      expect(isClanScoped('/auth/me'), isFalse);
      expect(isClanScoped('/auth/refresh'), isFalse);
      expect(isClanScoped('/me/clans'), isFalse);
      expect(isClanScoped('/me/clans/abc-123/select'), isFalse);
      expect(isClanScoped('/platform/audit'), isFalse);
      expect(isClanScoped('/invitations/tok/accept'), isFalse);
    });

    test('an invitations route that is not /accept stays clan-scoped', () {
      expect(isClanScoped('/invitations'), isTrue);
    });
  });

  test('AuthInterceptor attaches the bearer token', () async {
    final a = _ok();
    await (_dio(
      a,
    )..interceptors.add(AuthInterceptor(() => 'tok'))).get<Object?>('/persons');
    expect(a.received.single.headers['Authorization'], 'Bearer tok');
  });

  test('AuthInterceptor omits the header when signed out', () async {
    final a = _ok();
    await (_dio(a)..interceptors.add(AuthInterceptor(() => null))).get<Object?>(
      '/auth/login',
    );
    expect(a.received.single.headers.containsKey('Authorization'), isFalse);
  });

  test('ClanInterceptor attaches only on clan-scoped routes', () async {
    final a = SequenceAdapter(<Canned>[
      const Canned(200, <String, Object?>{'data': null}),
      const Canned(200, <String, Object?>{'data': null}),
    ]);
    final dio = _dio(a)..interceptors.add(ClanInterceptor(() => 'clan-1'));

    await dio.get<Object?>('/persons');
    expect(a.received[0].headers['X-Current-Clan-Id'], 'clan-1');

    await dio.get<Object?>('/me/clans');
    expect(a.received[1].headers.containsKey('X-Current-Clan-Id'), isFalse);
  });

  test('ClanInterceptor omits the header when no clan is selected', () async {
    final a = _ok();
    await (_dio(
      a,
    )..interceptors.add(ClanInterceptor(() => null))).get<Object?>('/persons');
    expect(a.received.single.headers.containsKey('X-Current-Clan-Id'), isFalse);
  });

  test('LocaleInterceptor sends the app locale', () async {
    final a = _ok();
    await (_dio(a)..interceptors.add(LocaleInterceptor(() => 'vi')))
        .get<Object?>('/persons');
    expect(a.received.single.headers['Accept-Language'], 'vi');
  });

  test('TraceInterceptor sends a W3C traceparent', () async {
    final a = _ok();
    await (_dio(
      a,
    )..interceptors.add(TraceInterceptor())).get<Object?>('/persons');
    final tp = a.received.single.headers['traceparent']! as String;
    expect(
      RegExp(r'^00-[0-9a-f]{32}-[0-9a-f]{16}-0[01]$').hasMatch(tp),
      isTrue,
      reason: tp,
    );
  });

  test('each request gets a distinct traceparent', () async {
    final a = SequenceAdapter(<Canned>[
      const Canned(200, <String, Object?>{'data': null}),
      const Canned(200, <String, Object?>{'data': null}),
    ]);
    final dio = _dio(a)..interceptors.add(TraceInterceptor());
    await dio.get<Object?>('/persons');
    await dio.get<Object?>('/persons');
    expect(
      a.received[0].headers['traceparent'],
      isNot(a.received[1].headers['traceparent']),
    );
  });

  test('newTraceparent honours the sampled flag', () {
    expect(newTraceparent().endsWith('-01'), isTrue);
    expect(newTraceparent(sampled: false).endsWith('-00'), isTrue);
  });
}
