// Fixtures copied verbatim from docs/contracts/rest-auth-api.md.
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:family_roots_mobile/core/network/api_client.dart';
import 'package:family_roots_mobile/core/network/api_exception.dart';
import 'package:family_roots_mobile/features/auth/data/auth_repository.dart';

import '../../support/sequence_adapter.dart';

ApiClient _client(SequenceAdapter a) => ApiClient(
  Dio(BaseOptions(baseUrl: 'https://api.test/api/v1'))..httpClientAdapter = a,
);

void main() {
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
      // `/auth/*` shares one rate-limit bucket (ADR-021). This rode on login
      // until #204 moved sign-in to Supabase.
      await AuthRepository(_client(a)).resendVerification('a@b.c');
      fail('expected ApiException');
    } on ApiException catch (e) {
      expect(e.retryAfter, 42);
      expect(policyActionFor(e.code), PolicyAction.backOff);
    }
  });
}
