import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:family_roots_mobile/core/network/interceptors/refresh_interceptor.dart';
import 'package:family_roots_mobile/core/network/token_refresher.dart';

import '../../support/sequence_adapter.dart';

const _unauthorized = <String, Object?>{
  'error': <String, Object?>{
    'code': 'invalid_token',
    'message': 'Token không hợp lệ',
    'detail': <String, Object?>{},
  },
};

Dio _dio(SequenceAdapter a) =>
    Dio(BaseOptions(baseUrl: 'https://api.test'))..httpClientAdapter = a;

void main() {
  group('TokenRefresher', () {
    test('concurrent callers share one in-flight refresh', () async {
      var calls = 0;
      final refresher = TokenRefresher(() async {
        calls++;
        await Future<void>.delayed(const Duration(milliseconds: 20));
        return 'new-token';
      });

      final results = await Future.wait<String?>(<Future<String?>>[
        refresher.refresh(),
        refresher.refresh(),
        refresher.refresh(),
      ]);

      expect(results, <String?>['new-token', 'new-token', 'new-token']);
      expect(calls, 1);
    });

    test('a later refresh starts a new flight', () async {
      var calls = 0;
      final refresher = TokenRefresher(() async {
        calls++;
        return 't$calls';
      });
      expect(await refresher.refresh(), 't1');
      expect(await refresher.refresh(), 't2');
      expect(calls, 2);
    });

    test('a throwing refresh does not wedge the refresher', () async {
      var calls = 0;
      final refresher = TokenRefresher(() async {
        calls++;
        if (calls == 1) throw StateError('boom');
        return 'ok';
      });
      await expectLater(refresher.refresh(), throwsStateError);
      expect(await refresher.refresh(), 'ok');
    });
  });

  group('RefreshInterceptor', () {
    test('401 refreshes once and retries exactly once', () async {
      final a = SequenceAdapter(<Canned>[
        const Canned(401, _unauthorized),
        const Canned(200, <String, Object?>{'data': <Object?>[]}),
      ]);
      final dio = _dio(a);

      var signedOut = false;
      final refresher = TokenRefresher(() async => 'fresh');
      dio.interceptors.add(
        RefreshInterceptor(
          refresher: refresher,
          retryDio: dio,
          onSignOut: () => signedOut = true,
        ),
      );

      final res = await dio.get<Object?>('/persons');
      expect(res.statusCode, 200);
      expect(a.callCount, 2);
      expect(a.received.last.headers['Authorization'], 'Bearer fresh');
      expect(refresher.refreshCallCount, 1);
      expect(signedOut, isFalse);
    });

    test('a failed refresh signs out and does not loop', () async {
      final a = SequenceAdapter(<Canned>[const Canned(401, _unauthorized)]);
      final dio = _dio(a);

      var signedOut = false;
      dio.interceptors.add(
        RefreshInterceptor(
          refresher: TokenRefresher(() async => null),
          retryDio: dio,
          onSignOut: () => signedOut = true,
        ),
      );

      await expectLater(
        dio.get<Object?>('/persons'),
        throwsA(isA<DioException>()),
      );
      expect(signedOut, isTrue);
      expect(a.callCount, 1);
    });

    test('a second 401 on the retry is not retried again', () async {
      final a = SequenceAdapter(<Canned>[
        const Canned(401, _unauthorized),
        const Canned(401, _unauthorized),
      ]);
      final dio = _dio(a);
      final refresher = TokenRefresher(() async => 'fresh');
      dio.interceptors.add(
        RefreshInterceptor(
          refresher: refresher,
          retryDio: dio,
          onSignOut: () {},
        ),
      );

      await expectLater(
        dio.get<Object?>('/persons'),
        throwsA(isA<DioException>()),
      );
      expect(a.callCount, 2);
      expect(refresher.refreshCallCount, 1);
    });

    test('a non-401 error passes straight through', () async {
      final a = SequenceAdapter(<Canned>[
        const Canned(403, <String, Object?>{
          'error': <String, Object?>{
            'code': 'insufficient_permissions',
            'message': 'Không đủ quyền',
            'detail': <String, Object?>{},
          },
        }),
      ]);
      final dio = _dio(a);
      final refresher = TokenRefresher(() async => 'fresh');
      dio.interceptors.add(
        RefreshInterceptor(
          refresher: refresher,
          retryDio: dio,
          onSignOut: () {},
        ),
      );

      await expectLater(
        dio.get<Object?>('/persons'),
        throwsA(isA<DioException>()),
      );
      expect(refresher.refreshCallCount, 0);
      expect(a.callCount, 1);
    });

    test('a cancellation is rethrown unchanged and never refreshes', () async {
      final dio = _dio(
        SequenceAdapter(<Canned>[
          const Canned(200, <String, Object?>{'data': null}),
        ]),
      );
      final refresher = TokenRefresher(() async => 'fresh');
      dio.interceptors.add(
        RefreshInterceptor(
          refresher: refresher,
          retryDio: dio,
          onSignOut: () {},
        ),
      );

      final token = CancelToken()..cancel('user left the screen');
      await expectLater(
        dio.get<Object?>('/persons', cancelToken: token),
        throwsA(
          isA<DioException>().having(
            (e) => e.type,
            'type',
            DioExceptionType.cancel,
          ),
        ),
      );
      expect(refresher.refreshCallCount, 0);
    });
  });
}
