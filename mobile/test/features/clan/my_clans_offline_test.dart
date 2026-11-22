// Issue #370: the clan list reads through the offline cache. Every reading is
// text on the screen `MyClansRoute` renders, never a provider field.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:family_roots_mobile/app/router/routes.dart';
import 'package:family_roots_mobile/core/l10n/generated/app_localizations.dart';
import 'package:family_roots_mobile/core/network/api_exception.dart';
import 'package:family_roots_mobile/core/network/dio_provider.dart';
import 'package:family_roots_mobile/core/theme/app_theme.dart';
import 'package:family_roots_mobile/domain/clan/clan_membership.dart';
import 'package:family_roots_mobile/domain/shared/ids.dart';
import 'package:family_roots_mobile/features/clan/clan.dart';

import '../../support/load_app_fonts.dart';
import '../../support/main_container.dart';

const _fresh = ClanMembership(
  clanId: ClanId('c2'),
  clanName: 'Họ Trần',
  clanSlug: 'ho-tran',
  role: ClanRole.viewer,
  joinedAt: null,
);

class _FlakyRepo implements ClanRepository {
  bool offline = false;

  @override
  Future<List<ClanMembership>> myClans() async {
    if (offline) throw const NetworkException('down');
    return <ClanMembership>[_fresh];
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  setUpAll(loadAppFonts);

  testWidgets('offline shows the cached clans with the dated banner; online '
      'refreshes and drops it', (tester) async {
    final repo = _FlakyRepo();
    final cache = FakeCacheStore();
    // Prime the cache the way a previous online session would have.
    await cache.put('GET /me/clans', <Object?>[
      <String, Object?>{
        'clan_id': 'c1',
        'clan_name': 'Họ Nguyễn Phúc',
        'clan_slug': 'ho-nguyen-phuc',
        'role': 'admin',
        'joined_at': null,
      },
    ]);
    repo.offline = true;

    final container = ProviderContainer(
      overrides: [
        clanRepositoryProvider.overrideWithValue(repo),
        cacheStoreProvider.overrideWithValue(cache),
      ],
    );
    addTearDown(container.dispose);

    await tester.runAsync(() => container.read(myClansProvider.future));
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp(
          locale: const Locale('vi'),
          theme: buildAppTheme(),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: const MyClansRoute(),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Họ Nguyễn Phúc'), findsOneWidget);
    expect(find.text('Dữ liệu ngày 03/08/2026'), findsOneWidget);

    repo.offline = false;
    container.invalidate(myClansProvider);
    await tester.runAsync(() => container.read(myClansProvider.future));
    await tester.pumpAndSettle();

    expect(find.text('Họ Trần'), findsOneWidget);
    expect(find.text('Họ Nguyễn Phúc'), findsNothing);
    expect(find.textContaining('Dữ liệu ngày'), findsNothing);
  });
}
