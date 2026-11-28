import 'package:flutter_test/flutter_test.dart';

import 'package:family_roots_mobile/core/network/dio_provider.dart';
import 'package:family_roots_mobile/domain/shared/ids.dart';
import 'package:family_roots_mobile/features/auth/auth.dart';
import 'package:family_roots_mobile/features/clan/clan.dart';

import '../../support/main_container.dart';
import '../../support/sequence_adapter.dart';

Canned _me(String email) => Canned(200, <String, Object?>{
  'data': <String, Object?>{
    'id': 'u-$email',
    'email': email,
    'full_name': email,
    'clan_id': null,
    'clan_name': null,
    'role': 'member',
    'is_approved': true,
    'has_pending_membership': false,
    'person_id': null,
    'preferred_locale': 'vi',
  },
});

Canned _clans(List<String> ids) => Canned(200, <String, Object?>{
  'data': <Map<String, Object?>>[
    for (final id in ids)
      <String, Object?>{
        'clan_id': id,
        'clan_name': 'Ho $id',
        'clan_slug': id,
        'role': 'admin',
        'joined_at': null,
      },
  ],
});

const _ok = Canned(200, <String, Object?>{'data': <String, Object?>{}});

void main() {
  test('signing out wipes the previous user: B sees only B\'s clans and '
      'starts with no clan header', () async {
    final adapter = SequenceAdapter(<Canned>[
      _me('a@b.c'),
      _clans(<String>['X', 'Y']),
      _ok, // clan-scoped probe while A is signed in
      _me('b@b.c'),
      _clans(<String>['Z']),
      _ok, // clan-scoped probe as B
    ]);
    final c = await mainContainer(adapter: adapter);
    addTearDown(c.dispose);
    final session = c.read(sessionControllerProvider.notifier);

    await c.read(sessionControllerProvider.future);
    await session.signIn(email: 'a@b.c', password: 'x');
    expect((await c.read(myClansProvider.future)).value.length, 2);
    await c.read(selectedClanProvider.notifier).select(const ClanId('X'));
    await c.read(dioProvider).get<Object?>('/persons');
    expect(adapter.received.last.headers['X-Current-Clan-Id'], 'X');

    await session.signOut();
    expect(c.read(selectedClanProvider), isNull);

    await session.signIn(email: 'b@b.c', password: 'x');
    final clans = (await c.read(myClansProvider.future)).value;
    expect(clans.map((m) => m.clanId.value), <String>['Z']);
    await c.read(dioProvider).get<Object?>('/persons');
    expect(adapter.received.last.headers['X-Current-Clan-Id'], isNull);
  });

  test('signing out empties the response cache', () async {
    final c = await mainContainer();
    addTearDown(c.dispose);
    await c.read(cacheStoreProvider).put('GET /me/clans', <Object?>[1]);

    await c.read(sessionControllerProvider.notifier).signOut();

    expect(await c.read(cacheStoreProvider).get('GET /me/clans'), isNull);
  });
}
