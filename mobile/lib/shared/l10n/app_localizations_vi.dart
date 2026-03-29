// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Vietnamese (`vi`).
class AppLocalizationsVi extends AppLocalizations {
  AppLocalizationsVi([String locale = 'vi']) : super(locale);

  @override
  String get appName => 'Gia Phả';

  @override
  String get loginTitle => 'Đăng nhập';

  @override
  String memberCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count thành viên',
      one: '1 thành viên',
      zero: 'Chưa có thành viên',
    );
    return '$_temp0';
  }

  @override
  String generationLabel(int number) {
    return 'Đời thứ $number';
  }

  @override
  String deathAnniversaryNotification(String name, int days) {
    return 'Ngày giỗ của $name còn $days ngày nữa';
  }
}
