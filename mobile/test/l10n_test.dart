import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:family_roots_mobile/shared/l10n/app_localizations.dart';

void main() {
  group('AppLocalizations', () {
    testWidgets('Vietnamese locale loads correctly', (tester) async {
      late AppLocalizations l10n;

      await tester.pumpWidget(
        MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          locale: const Locale('vi'),
          home: Builder(
            builder: (context) {
              l10n = AppLocalizations.of(context);
              return const SizedBox();
            },
          ),
        ),
      );

      expect(l10n.appName, 'Gia Phả');
      expect(l10n.greeting, 'Kính chào');
      expect(l10n.loginButton, 'Đăng Nhập');
      expect(l10n.familyNameTitle('Trần Văn'), 'Dòng họ Trần Văn');
      expect(l10n.generationLabel(3), 'Đời thứ 3');
      expect(l10n.memberCount(0), 'Chưa có thành viên');
      expect(l10n.memberCount(1), '1 thành viên');
      expect(l10n.memberCount(5), '5 thành viên');
    });

    testWidgets('English locale loads correctly', (tester) async {
      late AppLocalizations l10n;

      await tester.pumpWidget(
        MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          locale: const Locale('en'),
          home: Builder(
            builder: (context) {
              l10n = AppLocalizations.of(context);
              return const SizedBox();
            },
          ),
        ),
      );

      expect(l10n.appName, 'FamilyRoots');
      expect(l10n.greeting, 'Welcome');
      expect(l10n.loginButton, 'Sign In');
      expect(l10n.familyNameTitle('Tran Van'), 'The Tran Van Family');
      expect(l10n.generationLabel(3), 'Generation 3');
      expect(l10n.memberCount(0), 'No members');
      expect(l10n.memberCount(1), '1 member');
      expect(l10n.memberCount(5), '5 members');
    });
  });
}
