// Fixtures copied verbatim from docs/contracts/rest-auth-api.md.
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:family_roots_mobile/core/network/api_client.dart';
import 'package:family_roots_mobile/core/network/api_exception.dart';
import 'package:family_roots_mobile/domain/clan/clan_membership.dart';
import 'package:family_roots_mobile/features/auth/data/auth_repository.dart';

import '../../support/sequence_adapter.dart';

ApiClient _client(SequenceAdapter a) => ApiClient(
  Dio(BaseOptions(baseUrl: 'https://api.test/api/v1'))..httpClientAdapter = a,
);

const _login = <String, Object?>{
  'data': <String, Object?>{
    'access_token': 'eyJhbGciOi...',
    'refresh_token': 'v1.Mr7...',
    'expires_in': 3600,
    'user': <String, Object?>{
      'id': '99999999-9999-9999-9999-999999999999',
      'email': 'minh@example.com',
      'full_name': 'Nguyễn Văn Minh',
      'clan_id': '11111111-1111-1111-1111-111111111111',
      'clan_name': 'Họ Nguyễn Phúc',
      'role': 'admin',
      'is_approved': true,
      'has_pending_membership': false,
      'person_id': '33333333-3333-3333-3333-333333333333',
      'preferred_locale': 'vi',
    },
  },
};

void main() {
  test('POST /login maps tokens and the nested user', () async {
    final a = SequenceAdapter(<Canned>[const Canned(200, _login)]);
    final res = await AuthRepository(
      _client(a),
    ).login(email: 'minh@example.com', password: 'secret');

    expect(res.accessToken, 'eyJhbGciOi...');
    expect(res.refreshToken, 'v1.Mr7...');
    expect(res.expiresIn, 3600);
    expect(res.user.email, 'minh@example.com');
    expect(res.user.role, ClanRole.admin);
    expect(res.user.personId!.value, '33333333-3333-3333-3333-333333333333');
  });

  test('GET /auth/me carries the real has_pending_membership', () async {
    final a = SequenceAdapter(<Canned>[
      const Canned(200, <String, Object?>{
        'data': <String, Object?>{
          'id': 'u1',
          'email': 'pending@example.com',
          'full_name': 'Chờ Duyệt',
          'clan_id': 'c1',
          'clan_name': 'Họ Lê',
          'role': null,
          'is_approved': false,
          'has_pending_membership': true,
          'person_id': null,
          'preferred_locale': 'vi',
        },
      }),
    ]);
    final me = await AuthRepository(_client(a)).me();

    expect(me.isApproved, isFalse);
    expect(me.hasPendingMembership, isTrue);
    expect(me.role, isNull, reason: 'role is null until approved');
    expect(me.needsPendingScreen, isTrue);
    expect(me.needsOnboarding, isFalse);
  });

  test('a user attached to no clan needs onboarding', () async {
    final a = SequenceAdapter(<Canned>[
      const Canned(200, <String, Object?>{
        'data': <String, Object?>{
          'id': 'u2',
          'email': 'new@example.com',
          // NOT null: the backend declares `full_name: str` (non-nullable) on
          // UserProfile, so it cannot emit null here. Verified against the
          // generated OpenAPI schema, not the prose docs.
          'full_name': 'Người Mới',
          'clan_id': null,
          'clan_name': null,
          'role': null,
          'is_approved': false,
          'has_pending_membership': false,
          'person_id': null,
          'preferred_locale': 'vi',
        },
      }),
    ]);
    final me = await AuthRepository(_client(a)).me();
    expect(me.needsOnboarding, isTrue);
    expect(me.needsPendingScreen, isFalse);
  });

  test('login with an unverified email surfaces email_not_verified', () async {
    final a = SequenceAdapter(<Canned>[
      const Canned(403, <String, Object?>{
        'error': <String, Object?>{
          'code': 'email_not_verified',
          'message': 'Email chưa được xác thực',
          'detail': <String, Object?>{},
        },
      }),
    ]);
    try {
      await AuthRepository(_client(a)).login(email: 'a@b.c', password: 'x');
      fail('expected ApiException');
    } on ApiException catch (e) {
      expect(e.code, 'email_not_verified');
      expect(e.status, 403);
      expect(
        policyActionFor(e.code, status: e.status),
        PolicyAction.resendVerification,
      );
    }
  });

  test('rate limiting surfaces retry_after', () async {
    final a = SequenceAdapter(<Canned>[
      const Canned(429, <String, Object?>{
        'error': <String, Object?>{
          'code': 'rate_limited',
          'message': 'Quá nhiều yêu cầu',
          'detail': <String, Object?>{'retry_after': 42},
        },
      }),
    ]);
    try {
      await AuthRepository(_client(a)).login(email: 'a@b.c', password: 'x');
      fail('expected ApiException');
    } on ApiException catch (e) {
      expect(e.retryAfter, 42);
      expect(policyActionFor(e.code), PolicyAction.backOff);
    }
  });
}
