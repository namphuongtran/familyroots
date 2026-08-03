import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:family_roots_mobile/core/network/api_client.dart';
import 'package:family_roots_mobile/core/network/api_exception.dart';
import 'package:family_roots_mobile/domain/auth/user_profile.dart';
import 'package:family_roots_mobile/features/auth/application/session_controller.dart';
import 'package:family_roots_mobile/features/auth/data/auth_repository.dart';

import '../../support/sequence_adapter.dart';

AuthRepository _repo(List<Canned> canned) => AuthRepository(
  ApiClient(
    Dio(BaseOptions(baseUrl: 'https://api.test/api/v1'))
      ..httpClientAdapter = SequenceAdapter(canned),
  ),
);

const _loginOk = Canned(200, <String, Object?>{
  'data': <String, Object?>{
    'access_token': 'a',
    'refresh_token': 'r',
    'expires_in': 3600,
    'user': <String, Object?>{
      'id': 'u1',
      'email': 'a@b.c',
      'full_name': 'A',
      'clan_id': 'c1',
      'clan_name': 'Họ A',
      'role': 'admin',
      'is_approved': true,
      'has_pending_membership': false,
      'person_id': null,
      'preferred_locale': 'vi',
    },
  },
});

const _meApproved = Canned(200, <String, Object?>{
  'data': <String, Object?>{
    'id': 'u1',
    'email': 'a@b.c',
    'full_name': 'A',
    'clan_id': 'c1',
    'clan_name': 'Họ A',
    'role': 'admin',
    'is_approved': true,
    'has_pending_membership': false,
    'person_id': null,
    'preferred_locale': 'vi',
  },
});

void main() {
  test('starts signed out', () async {
    final c = ProviderContainer(
      overrides: [authRepositoryProvider.overrideWithValue(_repo(<Canned>[]))],
    );
    addTearDown(c.dispose);
    expect(await c.read(sessionControllerProvider.future), isNull);
  });

  test('signIn logs in then reads GET /auth/me', () async {
    final c = ProviderContainer(
      overrides: [
        authRepositoryProvider.overrideWithValue(
          _repo(<Canned>[_loginOk, _meApproved]),
        ),
      ],
    );
    addTearDown(c.dispose);

    await c.read(sessionControllerProvider.future);
    await c
        .read(sessionControllerProvider.notifier)
        .signIn(email: 'a@b.c', password: 'x');

    final profile = c.read(sessionControllerProvider).requireValue;
    expect(profile, isA<UserProfile>());
    expect(profile!.email, 'a@b.c');
    expect(profile.isApproved, isTrue);
  });

  test(
    'a failed login lands in AsyncError carrying the ApiException',
    () async {
      final c = ProviderContainer(
        overrides: [
          authRepositoryProvider.overrideWithValue(
            _repo(<Canned>[
              const Canned(401, <String, Object?>{
                'error': <String, Object?>{
                  'code': 'auth.invalid_credentials',
                  'message': 'Sai email hoặc mật khẩu',
                  'detail': <String, Object?>{},
                },
              }),
            ]),
          ),
        ],
      );
      addTearDown(c.dispose);

      await c.read(sessionControllerProvider.future);
      await c
          .read(sessionControllerProvider.notifier)
          .signIn(email: 'a@b.c', password: 'wrong');

      final state = c.read(sessionControllerProvider);
      expect(state.hasError, isTrue);
      expect(state.error, isA<ApiException>());
      expect((state.error! as ApiException).code, 'auth.invalid_credentials');
    },
  );

  test('signOut clears the profile even if logout fails', () async {
    final c = ProviderContainer(
      overrides: [
        authRepositoryProvider.overrideWithValue(
          _repo(<Canned>[
            _loginOk,
            _meApproved,
            const Canned(503, <String, Object?>{
              'error': <String, Object?>{
                'code': 'auth_provider_unavailable',
                'message': 'Tạm thời gián đoạn',
                'detail': <String, Object?>{},
              },
            }),
          ]),
        ),
      ],
    );
    addTearDown(c.dispose);

    await c.read(sessionControllerProvider.future);
    await c
        .read(sessionControllerProvider.notifier)
        .signIn(email: 'a@b.c', password: 'x');
    expect(c.read(sessionControllerProvider).requireValue, isNotNull);

    await c.read(sessionControllerProvider.notifier).signOut();
    expect(c.read(sessionControllerProvider).requireValue, isNull);
  });
}
