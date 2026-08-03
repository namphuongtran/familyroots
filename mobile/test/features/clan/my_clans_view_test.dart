import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:family_roots_mobile/core/l10n/generated/app_localizations.dart';
import 'package:family_roots_mobile/core/theme/app_theme.dart';
import 'package:family_roots_mobile/domain/clan/clan_membership.dart';
import 'package:family_roots_mobile/domain/shared/ids.dart';
import 'package:family_roots_mobile/features/clan/presentation/my_clans_page.dart';

import '../../support/load_app_fonts.dart';

final _clans = <ClanMembership>[
  const ClanMembership(
    clanId: ClanId('c1'),
    clanName: 'Họ Nguyễn Phúc',
    clanSlug: 'ho-nguyen-phuc',
    role: ClanRole.admin,
    joinedAt: null,
  ),
  const ClanMembership(
    clanId: ClanId('c2'),
    clanName: 'Họ Trần',
    clanSlug: 'ho-tran',
    role: ClanRole.viewer,
    joinedAt: null,
  ),
];

Widget host(
  Widget child, {
  Locale locale = const Locale('vi'),
  double scale = 1.0,
}) => MaterialApp(
  locale: locale,
  theme: buildAppTheme(),
  localizationsDelegates: AppLocalizations.localizationsDelegates,
  supportedLocales: AppLocalizations.supportedLocales,
  builder: (context, w) => MediaQuery(
    data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(scale)),
    child: w!,
  ),
  home: child,
);

void main() {
  setUpAll(loadAppFonts);

  testWidgets('renders Vietnamese by default', (tester) async {
    await tester.pumpWidget(host(MyClansView(clans: _clans, onSelect: (_) {})));
    await tester.pumpAndSettle();

    expect(find.text('Dòng họ của tôi'), findsOneWidget);
    expect(find.text('Họ Nguyễn Phúc'), findsOneWidget);
    expect(find.text('2 dòng họ'), findsOneWidget);
  });

  testWidgets('renders English when the locale is en', (tester) async {
    await tester.pumpWidget(
      host(
        MyClansView(clans: _clans, onSelect: (_) {}),
        locale: const Locale('en'),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('My clans'), findsOneWidget);
    expect(find.text('2 clans'), findsOneWidget);
  });

  testWidgets('the plural zero case has its own wording', (tester) async {
    await tester.pumpWidget(
      host(MyClansView(clans: const <ClanMembership>[], onSelect: (_) {})),
    );
    await tester.pumpAndSettle();
    expect(find.text('Chưa có dòng họ'), findsOneWidget);
  });

  testWidgets('the stale banner uses the ARB placeholder', (tester) async {
    await tester.pumpWidget(
      host(
        MyClansView(clans: _clans, onSelect: (_) {}, staleAsOf: '01/08/2026'),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Dữ liệu ngày 01/08/2026'), findsOneWidget);
  });

  testWidgets('survives 200% text scale without overflow', (tester) async {
    await tester.pumpWidget(
      host(MyClansView(clans: _clans, onSelect: (_) {}), scale: 2.0),
    );
    await tester.pumpAndSettle();

    expect(find.text('Họ Nguyễn Phúc'), findsOneWidget);
    // Non-null if a RenderFlex overflowed.
    expect(tester.takeException(), isNull);
  });

  testWidgets('tapping a clan reports the selection', (tester) async {
    ClanMembership? picked;
    await tester.pumpWidget(
      host(MyClansView(clans: _clans, onSelect: (c) => picked = c)),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Họ Trần'));
    await tester.pumpAndSettle();
    expect(picked?.clanId.value, 'c2');
  });
}
