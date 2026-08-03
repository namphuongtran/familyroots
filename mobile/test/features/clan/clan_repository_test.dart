// Fixtures copied verbatim from docs/contracts/rest-me-api.md.
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:family_roots_mobile/core/network/api_client.dart';
import 'package:family_roots_mobile/domain/clan/clan_membership.dart';
import 'package:family_roots_mobile/features/clan/data/clan_repository.dart';

import '../../support/sequence_adapter.dart';

ApiClient _client(SequenceAdapter a) => ApiClient(
  Dio(BaseOptions(baseUrl: 'https://api.test/api/v1'))..httpClientAdapter = a,
);

const _meClans = <String, Object?>{
  'data': <Object?>[
    <String, Object?>{
      'clan_id': '11111111-1111-1111-1111-111111111111',
      'clan_name': 'Họ Nguyễn Phúc',
      'clan_slug': 'ho-nguyen-phuc',
      'role': 'admin',
      'joined_at': '2026-01-15T08:30:00Z',
    },
    <String, Object?>{
      'clan_id': '22222222-2222-2222-2222-222222222222',
      'clan_name': 'Họ Trần',
      'clan_slug': 'ho-tran',
      'role': 'viewer',
      'joined_at': '2026-03-02T11:00:00Z',
    },
  ],
};

void main() {
  test('GET /me/clans maps to domain memberships', () async {
    final a = SequenceAdapter(<Canned>[const Canned(200, _meClans)]);
    final clans = await ClanRepository(_client(a)).myClans();

    expect(clans, hasLength(2));
    expect(clans.first.clanName, 'Họ Nguyễn Phúc');
    expect(clans.first.clanId.value, '11111111-1111-1111-1111-111111111111');
    expect(clans.first.role, ClanRole.admin);
    expect(clans.first.role.canAdminister, isTrue);
    expect(clans.first.joinedAt, DateTime.utc(2026, 1, 15, 8, 30));
    expect(clans.last.role, ClanRole.viewer);
    expect(clans.last.role.canEdit, isFalse);
  });

  test('no X-Current-Clan-Id header is needed for /me/clans', () async {
    final a = SequenceAdapter(<Canned>[const Canned(200, _meClans)]);
    await ClanRepository(_client(a)).myClans();
    expect(a.received.single.headers.containsKey('X-Current-Clan-Id'), isFalse);
  });

  test('an unknown role degrades rather than throwing', () async {
    final a = SequenceAdapter(<Canned>[
      const Canned(200, <String, Object?>{
        'data': <Object?>[
          <String, Object?>{
            'clan_id': 'c1',
            'clan_name': 'X',
            'clan_slug': 'x',
            'role': 'archivist',
            'joined_at': null,
          },
        ],
      }),
    ]);
    final clans = await ClanRepository(_client(a)).myClans();
    expect(clans.single.role, ClanRole.unknown);
    expect(clans.single.role.canEdit, isFalse);
    expect(clans.single.joinedAt, isNull);
  });

  test('an empty clan list is valid — a purely pending user', () async {
    final a = SequenceAdapter(<Canned>[
      const Canned(200, <String, Object?>{'data': <Object?>[]}),
    ]);
    expect(await ClanRepository(_client(a)).myClans(), isEmpty);
  });
}
