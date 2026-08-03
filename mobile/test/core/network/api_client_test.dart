import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:family_roots_mobile/core/network/api_client.dart';
import 'package:family_roots_mobile/core/network/api_exception.dart';
import 'package:family_roots_mobile/core/network/interceptors/trace_interceptor.dart';

import '../../support/sequence_adapter.dart';

ApiClient _client(SequenceAdapter a, {bool trace = false}) {
  final dio = Dio(BaseOptions(baseUrl: 'https://api.test/api/v1'))
    ..httpClientAdapter = a;
  if (trace) dio.interceptors.add(TraceInterceptor());
  return ApiClient(dio);
}

void main() {
  test('getOne unwraps the envelope', () async {
    final a = SequenceAdapter(<Canned>[
      const Canned(200, <String, Object?>{
        'data': <String, Object?>{'id': 'u1', 'email': 'a@b.c'},
      }),
    ]);
    final got = await _client(a).getOne<String>(
      '/auth/me',
      parse: (j) => (j! as Map<String, Object?>)['email']! as String,
    );
    expect(got, 'a@b.c');
  });

  test('getPage handles the meta-less array of GET /me/clans', () async {
    final a = SequenceAdapter(<Canned>[
      const Canned(200, <String, Object?>{
        'data': <Object?>[
          <String, Object?>{'clan_id': 'c1'},
          <String, Object?>{'clan_id': 'c2'},
        ],
      }),
    ]);
    final page = await _client(a).getPage<String>(
      '/me/clans',
      parse: (j) => (j! as Map<String, Object?>)['clan_id']! as String,
    );
    expect(page.items, <String>['c1', 'c2']);
    expect(page.cursor, isNull);
    expect(page.hasMore, isFalse);
  });

  test('getPage forwards an opaque cursor verbatim', () async {
    final a = SequenceAdapter(<Canned>[
      const Canned(200, <String, Object?>{'data': <Object?>[]}),
    ]);
    await _client(a).getPage<int>(
      '/persons',
      cursor: 'weird!!:{}',
      limit: 25,
      parse: (j) => j! as int,
    );
    expect(a.received.single.uri.queryParameters['cursor'], 'weird!!:{}');
    expect(a.received.single.uri.queryParameters['limit'], '25');
  });

  test('an error envelope becomes ApiException with code and detail', () async {
    final a = SequenceAdapter(<Canned>[
      const Canned(409, <String, Object?>{
        'error': <String, Object?>{
          'code': 'stale_write',
          'message': 'Người khác vừa sửa',
          'detail': <String, Object?>{'current_version': 4},
        },
      }),
    ]);
    await expectLater(
      _client(a).getOne<Object?>('/persons/1', parse: (j) => j),
      throwsA(
        isA<ApiException>()
            .having((e) => e.code, 'code', 'stale_write')
            .having((e) => e.status, 'status', 409)
            .having((e) => e.currentVersion, 'currentVersion', 4),
      ),
    );
  });

  test('a 403 error envelope keeps its code for policyActionFor', () async {
    final a = SequenceAdapter(<Canned>[
      const Canned(403, <String, Object?>{
        'error': <String, Object?>{
          'code': 'email_not_verified',
          'message': 'Email chưa xác thực',
          'detail': <String, Object?>{},
        },
      }),
    ]);
    try {
      await _client(a).getOne<Object?>('/persons', parse: (j) => j);
      fail('expected ApiException');
    } on ApiException catch (e) {
      expect(
        policyActionFor(e.code, status: e.status),
        PolicyAction.resendVerification,
      );
    }
  });

  test('a non-envelope error body is MalformedResponseException', () async {
    final a = SequenceAdapter(<Canned>[const Canned(500, 'gateway exploded')]);
    await expectLater(
      _client(a).getOne<Object?>('/persons', parse: (j) => j),
      throwsA(isA<MalformedResponseException>()),
    );
  });

  test('a 2xx body without data is MalformedResponseException', () async {
    final a = SequenceAdapter(<Canned>[
      const Canned(200, <String, Object?>{'unexpected': 1}),
    ]);
    await expectLater(
      _client(a).getOne<Object?>('/persons', parse: (j) => j),
      throwsA(isA<MalformedResponseException>()),
    );
  });

  test('the trace id is lifted from the traceparent header', () async {
    final a = SequenceAdapter(<Canned>[
      const Canned(500, <String, Object?>{
        'error': <String, Object?>{
          'code': 'internal_error',
          'message': 'Lỗi hệ thống',
          'detail': <String, Object?>{},
        },
      }),
    ]);
    try {
      await _client(
        a,
        trace: true,
      ).getOne<Object?>('/persons', parse: (j) => j);
      fail('expected ApiException');
    } on ApiException catch (e) {
      expect(e.traceId, isNotNull);
      expect(RegExp(r'^[0-9a-f]{32}$').hasMatch(e.traceId!), isTrue);
    }
  });

  test('a cancellation is rethrown as DioException, not wrapped', () async {
    final a = SequenceAdapter(<Canned>[
      const Canned(200, <String, Object?>{'data': null}),
    ]);
    final token = CancelToken()..cancel('gone');
    await expectLater(
      _client(
        a,
      ).getOne<Object?>('/persons', cancelToken: token, parse: (j) => j),
      throwsA(
        isA<DioException>().having(
          (e) => e.type,
          'type',
          DioExceptionType.cancel,
        ),
      ),
    );
  });

  test('toAppException maps timeouts and connection errors', () {
    final req = RequestOptions(path: '/x');
    expect(
      toAppException(
        DioException(
          requestOptions: req,
          type: DioExceptionType.receiveTimeout,
        ),
      ),
      isA<TimeoutException>(),
    );
    expect(
      toAppException(
        DioException(
          requestOptions: req,
          type: DioExceptionType.connectionError,
        ),
      ),
      isA<NetworkException>(),
    );
  });

  test('post unwraps the envelope', () async {
    final a = SequenceAdapter(<Canned>[
      const Canned(200, <String, Object?>{
        'data': <String, Object?>{'access_token': 'tok'},
      }),
    ]);
    final got = await _client(a).post<String>(
      '/auth/login',
      body: <String, Object?>{'email': 'a@b.c', 'password': 'x'},
      parse: (j) => (j! as Map<String, Object?>)['access_token']! as String,
    );
    expect(got, 'tok');
    expect(a.received.single.method, 'POST');
  });
}
