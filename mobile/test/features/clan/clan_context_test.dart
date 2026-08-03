import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:family_roots_mobile/core/network/api_client.dart';
import 'package:family_roots_mobile/core/storage/prefs_store.dart';
import 'package:family_roots_mobile/domain/shared/ids.dart';
import 'package:family_roots_mobile/features/clan/application/clan_context.dart';
import 'package:family_roots_mobile/features/clan/data/clan_repository.dart';

import '../../support/sequence_adapter.dart';

ClanRepository _repo(List<Canned> canned) => ClanRepository(
  ApiClient(
    Dio(BaseOptions(baseUrl: 'https://api.test/api/v1'))
      ..httpClientAdapter = SequenceAdapter(canned),
  ),
);

Canned _clans(List<Map<String, Object?>> rows) =>
    Canned(200, <String, Object?>{'data': rows});

Map<String, Object?> _row(String id, String name) => <String, Object?>{
  'clan_id': id,
  'clan_name': name,
  'clan_slug': name.toLowerCase(),
  'role': 'admin',
  'joined_at': null,
};

Future<ProviderContainer> _container(List<Canned> canned) async {
  SharedPreferences.setMockInitialValues(<String, Object>{});
  final prefs = await PrefsStore.open();
  return ProviderContainer(
    overrides: [
      clanRepositoryProvider.overrideWithValue(_repo(canned)),
      prefsStoreProvider.overrideWithValue(prefs),
    ],
  );
}

void main() {
  test('no approved clans resolves to none', () async {
    final c = await _container(<Canned>[_clans(<Map<String, Object?>>[])]);
    addTearDown(c.dispose);
    expect(await c.read(clanResolutionProvider.future), ClanResolution.none);
  });

  test('exactly one clan auto-selects and persists', () async {
    final c = await _container(<Canned>[
      _clans(<Map<String, Object?>>[_row('c1', 'Ho A')]),
    ]);
    addTearDown(c.dispose);

    expect(
      await c.read(selectedClanProvider.notifier).resolve(),
      ClanResolution.resolved,
    );
    expect(c.read(selectedClanProvider), const ClanId('c1'));
  });

  test('several clans need the picker until one is chosen', () async {
    final c = await _container(<Canned>[
      _clans(<Map<String, Object?>>[_row('c1', 'Ho A'), _row('c2', 'Ho B')]),
    ]);
    addTearDown(c.dispose);

    expect(
      await c.read(clanResolutionProvider.future),
      ClanResolution.needsPicker,
    );

    await c.read(selectedClanProvider.notifier).select(const ClanId('c2'));
    c.invalidate(clanResolutionProvider);
    expect(
      await c.read(clanResolutionProvider.future),
      ClanResolution.resolved,
    );
    expect(c.read(selectedClanProvider), const ClanId('c2'));
  });

  test(
    'a stored clan the user no longer belongs to forces the picker',
    () async {
      SharedPreferences.setMockInitialValues(<String, Object>{
        'familyroots.selected_clan_id': 'gone',
      });
      final prefs = await PrefsStore.open();
      final c = ProviderContainer(
        overrides: [
          clanRepositoryProvider.overrideWithValue(
            _repo(<Canned>[
              _clans(<Map<String, Object?>>[
                _row('c1', 'Ho A'),
                _row('c2', 'Ho B'),
              ]),
            ]),
          ),
          prefsStoreProvider.overrideWithValue(prefs),
        ],
      );
      addTearDown(c.dispose);

      expect(c.read(selectedClanProvider), const ClanId('gone'));
      expect(
        await c.read(clanResolutionProvider.future),
        ClanResolution.needsPicker,
      );
    },
  );

  test('clear drops the stored selection', () async {
    final c = await _container(<Canned>[
      _clans(<Map<String, Object?>>[_row('c1', 'Ho A')]),
    ]);
    addTearDown(c.dispose);

    await c.read(selectedClanProvider.notifier).resolve();
    expect(c.read(selectedClanProvider), isNotNull);

    await c.read(selectedClanProvider.notifier).clear();
    expect(c.read(selectedClanProvider), isNull);
  });
}
