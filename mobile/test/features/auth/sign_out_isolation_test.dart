// Issue #369: sign-out left the previous user's clans, selected clan and
// cached responses on the device. Every reading below is a clan list a
// provider returned, a header on a request the real Dio sent, or a row read
// back from the cache — never a setter.
import 'package:flutter_test/flutter_test.dart';

import 'package:family_roots_mobile/core/network/dio_provider.dart';
import 'package:family_roots_mobile/domain/shared/ids.dart';
import 'package:family_roots_mobile/features/auth/auth.dart';
import 'package:family_roots_mobile/features/clan/clan.dart';

import '../../support/main_container.dart';
import '../../support/sequence_adapter.dart';

Canned _me(String id, String email) => Canned(200, <String, Object?>{
  'data': <String, Object?>{
    'id': id,
    'email': email,
    'full_name': id,
    'clan_id': null,
    'clan_name': null,
    'role': null,
    'is_approved': true,
    'has_pending_membership': false,
    'person_id': null,
    'preferred_locale': 'vi',
  },
});

Canned _clans(List<String> ids) => Canned(200, <String, Object?>{
  'data': [
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

void main() {
  test(
    'B signs in after A on one device and sees none of A\'s clan data',
    () async {
      final adapter = SequenceAdapter(<Canned>[
        _me('a', 'a@x.test'),
        _clans(<String>['x', 'y']),
        _me('b', 'b@x.test'),
        _clans(<String>['z']),
        const Canned(200, <String, Object?>{'data': <Object?>[]}),
      ]);
      final c = await mainContainer(adapter: adapter);
      addTearDown(c.dispose);
      final session = c.read(sessionControllerProvider.notifier);

      await c.read(sessionControllerProvider.future);
      await session.signIn(email: 'a@x.test', password: 'x');
      expect(
        (await c.read(myClansProvider.future)).map((m) => m.clanId.value),
        <String>['x', 'y'],
      );
      await c.read(selectedClanProvider.notifier).select(const ClanId('x'));
      await c.read(cacheStoreProvider).put('GET /me/clans', <Object?>['a']);

      await session.signOut();
      expect(c.read(selectedClanProvider), isNull);
      expect(await c.read(cacheStoreProvider).get('GET /me/clans'), isNull);

      await session.signIn(email: 'b@x.test', password: 'x');
      expect(
        (await c.read(myClansProvider.future)).map((m) => m.clanId.value),
        <String>['z'],
      );
      expect(c.read(selectedClanProvider), isNull);

      await c.read(dioProvider).get<Object?>('/persons');
      expect(adapter.received.last.path, '/persons');
      expect(adapter.received.last.headers['X-Current-Clan-Id'], isNull);
    },
  );
}
