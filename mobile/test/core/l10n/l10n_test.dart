import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:family_roots_mobile/core/l10n/generated/app_localizations.dart';

Widget _host(Locale locale, void Function(AppLocalizations) probe) =>
    MaterialApp(
      locale: locale,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Builder(
        builder: (context) {
          probe(AppLocalizations.of(context));
          return const SizedBox();
        },
      ),
    );

void main() {
  testWidgets('vi and en are both supported, vi first', (tester) async {
    expect(
      AppLocalizations.supportedLocales.map((l) => l.languageCode),
      containsAll(<String>['vi', 'en']),
    );
    expect(AppLocalizations.supportedLocales.first.languageCode, 'vi');
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('Vietnamese strings', (tester) async {
    late AppLocalizations l;
    await tester.pumpWidget(_host(const Locale('vi'), (x) => l = x));
    await tester.pumpAndSettle();

    expect(l.myClansTitle, 'Dòng họ của tôi');
    expect(l.clanCount(0), 'Chưa có dòng họ');
    expect(l.clanCount(1), '1 dòng họ');
    expect(l.clanCount(5), '5 dòng họ');
    expect(l.staleDataBanner('01/08/2026'), 'Dữ liệu ngày 01/08/2026');
  });

  testWidgets('English strings', (tester) async {
    late AppLocalizations l;
    await tester.pumpWidget(_host(const Locale('en'), (x) => l = x));
    await tester.pumpAndSettle();

    expect(l.myClansTitle, 'My clans');
    expect(l.clanCount(0), 'No clans');
    expect(l.clanCount(2), '2 clans');
  });

  testWidgets('an unsupported locale falls back to vi', (tester) async {
    late AppLocalizations l;
    await tester.pumpWidget(_host(const Locale('zh'), (x) => l = x));
    await tester.pumpAndSettle();
    expect(l.myClansTitle, 'Dòng họ của tôi');
  });
}
