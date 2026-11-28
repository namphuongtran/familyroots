// Issue #369: sign-out left the previous user's clans, selected clan and
// cache on the device. Every reading below is a provider value, a request
// header on the wire (real Dio, all five interceptors) or a stored row.
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:family_roots_mobile/core/network/dio_provider.dart';
import 'package:family_roots_mobile/domain/shared/ids.dart';
import 'package:family_roots_mobile/features/auth/auth.dart';
import 'package:family_roots_mobile/features/clan/clan.dart';

import '../support/main_container.dart';
import '../support/sequence_adapter.dart';

const _me = Canned(200, <String, Object?>{
  'data': <String, Object?>{
    'id': 'u1',
    'email': 'a@b.c',
    'full_name': 'A',
    'clan_id': null,
    'clan_name': null,
    'role': null,
    'is_approved': true,
    'has_pending_membership': false,
    'person_id': null,
    'preferred_locale': 'vi',
  },
});

Map<String, Object?> _row(String id) => <String, Object?>{
  'clan_id': id,
  'clan_name': 'Ho $id',
  'clan_slug': id,
  'role': 'admin',
  'joined_at': null,
};

Canned _clans(List<String> ids) =>
    Canned(200, <String, Object?>{'data': ids.map(_row).toList()});

const _ok = Canned(200, <String, Object?>{'data': <String, Object?>{}});

void main() {
  test('sign-out leaves nothing of user A for user B', () async {
    final adapter = SequenceAdapter(<Canned>[
      _me, // A signs in
      _clans(<String>['x', 'y']),
      _ok, // A's clan-scoped probe
      _me, // B signs in
      _clans(<String>['z']),
      _ok, // B's clan-scoped probe
    ]);
    final c = await mainContainer(adapter: adapter);
    addTearDown(c.dispose);
    final session = c.read(sessionControllerProvider.notifier);

    await c.read(sessionControllerProvider.future);
    await session.signIn(email: 'a@b.c', password: 'x');
    expect((await c.read(myClansProvider.future)).length, 2);
    await c.read(selectedClanProvider.notifier).select(const ClanId('x'));
    await c.read(cacheStoreProvider).put('GET /me/clans', <Object?>[]);
    await c.read(dioProvider).get<Object?>('/probe');
    expect(adapter.received.last.headers['X-Current-Clan-Id'], 'x');

    await session.signOut();
    expect(c.read(selectedClanProvider), isNull);
    expect(c.read(prefsStoreProvider).readClanId(), isNull);
    expect(await c.read(cacheStoreProvider).get('GET /me/clans'), isNull);

    await session.signIn(email: 'b@b.c', password: 'x');
    final clans = await c.read(myClansProvider.future);
    expect(clans.map((m) => m.clanId.value), <String>['z']);

    await c.read(dioProvider).get<Object?>('/probe');
    expect(
      adapter.received.last.headers['X-Current-Clan-Id'],
      isNot('x'),
      reason: "B's first request must not carry A's clan",
    );
  });
}
