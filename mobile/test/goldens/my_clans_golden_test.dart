// Golden images are host-renderer sensitive (plan caveat N5): baselines
// generated on macOS do not match Linux CI. These tests are tagged so CI can
// exclude them (`flutter test --exclude-tags golden`) while they still run
// locally, where the baselines were produced. M0 Task 19 owns the CI rewrite
// and can revisit this by generating baselines in a Linux container.
@Tags(<String>['golden'])
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:family_roots_mobile/domain/clan/clan_membership.dart';
import 'package:family_roots_mobile/domain/shared/ids.dart';
import 'package:family_roots_mobile/features/clan/presentation/my_clans_page.dart';

import '../features/clan/my_clans_view_test.dart' show host;
import '../support/load_app_fonts.dart';

final _clans = <ClanMembership>[
  const ClanMembership(
    clanId: ClanId('c1'),
    clanName: 'Họ Nguyễn Phúc',
    clanSlug: 'ho-nguyen-phuc',
    role: ClanRole.admin,
    joinedAt: null,
  ),
];

void main() {
  setUpAll(loadAppFonts);

  testWidgets('my clans at text scale 1.0', (tester) async {
    tester.view.physicalSize = const Size(1080, 1920);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(host(MyClansView(clans: _clans, onSelect: (_) {})));
    await tester.pumpAndSettle();

    await expectLater(
      find.byType(MyClansView),
      matchesGoldenFile('goldens/my_clans_1x.png'),
    );
  });

  testWidgets('my clans at text scale 2.0', (tester) async {
    tester.view.physicalSize = const Size(1080, 1920);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(
      host(MyClansView(clans: _clans, onSelect: (_) {}), scale: 2.0),
    );
    await tester.pumpAndSettle();

    await expectLater(
      find.byType(MyClansView),
      matchesGoldenFile('goldens/my_clans_2x.png'),
    );
  });
}
