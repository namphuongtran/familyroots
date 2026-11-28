import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:family_roots_mobile/core/l10n/generated/app_localizations.dart';
import 'package:family_roots_mobile/core/theme/app_theme.dart';
import 'package:family_roots_mobile/domain/clan/clan_membership.dart';
import 'package:family_roots_mobile/domain/shared/ids.dart';
import 'package:family_roots_mobile/features/clan/presentation/clan_picker_page.dart';
import 'package:family_roots_mobile/features/clan/presentation/my_clans_page.dart';

import '../../support/load_app_fonts.dart';

final _clans = <ClanMembership>[
  for (final r in ClanRole.values)
    ClanMembership(
      clanId: ClanId('c-${r.name}'),
      clanName: 'Họ ${r.index}',
      clanSlug: 'ho-${r.index}',
      role: r,
      joinedAt: null,
    ),
];

Widget _host(Widget child, Locale locale) => MaterialApp(
  locale: locale,
  theme: buildAppTheme(),
  localizationsDelegates: AppLocalizations.localizationsDelegates,
  supportedLocales: AppLocalizations.supportedLocales,
  home: child,
);

void main() {
  setUpAll(loadAppFonts);

  final screens = <String, Widget Function()>{
    'MyClansView': () => MyClansView(clans: _clans, onSelect: (_) {}),
    'ClanPickerView': () => ClanPickerView(clans: _clans, onSelect: (_) {}),
  };
  final labels = <String, List<String>>{
    'vi': ['Quản trị', 'Chỉnh sửa', 'Xem', 'Không rõ'],
    'en': ['Admin', 'Editor', 'Viewer', 'Unknown'],
  };

  for (final screen in screens.entries) {
    for (final loc in labels.entries) {
      testWidgets('${screen.key} shows role labels under ${loc.key}', (
        tester,
      ) async {
        await tester.pumpWidget(_host(screen.value(), Locale(loc.key)));
        await tester.pumpAndSettle();

        for (final l in loc.value) {
          expect(find.text(l), findsOneWidget);
        }
        for (final raw in ['admin', 'editor', 'viewer', 'unknown']) {
          expect(find.text(raw), findsNothing);
        }
      });
    }
  }
}
