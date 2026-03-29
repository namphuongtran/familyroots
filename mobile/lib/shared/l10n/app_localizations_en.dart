// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class AppLocalizationsEn extends AppLocalizations {
  AppLocalizationsEn([String locale = 'en']) : super(locale);

  @override
  String get appName => 'FamilyRoots';

  @override
  String get loginTitle => 'Sign In';

  @override
  String memberCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count members',
      one: '1 member',
      zero: 'No members',
    );
    return '$_temp0';
  }

  @override
  String generationLabel(int number) {
    return 'Generation $number';
  }

  @override
  String deathAnniversaryNotification(String name, int days) {
    return '$name\'s death anniversary is in $days days';
  }
}
