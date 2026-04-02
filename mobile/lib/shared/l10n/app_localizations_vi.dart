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
  String get greeting => 'Kính chào';

  @override
  String familyNameTitle(String surname) {
    return 'Dòng họ $surname';
  }

  @override
  String get searchAction => 'Tìm kiếm';

  @override
  String get addMemberAction => 'Thêm người';

  @override
  String get eventsAction => 'Sự kiện';

  @override
  String get genealogyAction => 'Gia phả';

  @override
  String get upcomingEvents => 'Sự Kiện Sắp Tới';

  @override
  String get viewAll => 'Xem tất cả';

  @override
  String get recentActivity => 'Hoạt Động Mới Nhất';

  @override
  String hoursAgo(int count) {
    return '$count giờ trước';
  }

  @override
  String get loginTitle => 'Đăng nhập';

  @override
  String get loginSubtitle => 'Lưu giữ cội nguồn - Kết nối tương lai';

  @override
  String get emailLabel => 'Email';

  @override
  String get emailHint => 'Nhập email của bạn';

  @override
  String get passwordLabel => 'Mật khẩu';

  @override
  String get passwordHint => 'Nhập mật khẩu';

  @override
  String get forgotPassword => 'Quên mật khẩu?';

  @override
  String get loginButton => 'Đăng Nhập';

  @override
  String get orDivider => 'Hoặc';

  @override
  String get noAccountPrompt => 'Chưa có tài khoản? ';

  @override
  String get registerLink => 'Đăng ký ngay';

  @override
  String get registerTitle => 'Tạo Tài Khoản';

  @override
  String get registerSubtitle => 'Bắt đầu hành trình lưu giữ di sản gia đình';

  @override
  String get fullNameLabel => 'Họ và tên';

  @override
  String get fullNameHint => 'Nhập họ và tên của bạn';

  @override
  String get confirmPasswordLabel => 'Xác nhận mật khẩu';

  @override
  String get confirmPasswordHint => 'Nhập lại mật khẩu';

  @override
  String get registerButton => 'Đăng Ký';

  @override
  String get hasAccountPrompt => 'Đã có tài khoản? ';

  @override
  String get loginLink => 'Đăng nhập';

  @override
  String get membersTitle => 'Thành viên';

  @override
  String get searchMembersHint => 'Tìm kiếm thành viên...';

  @override
  String generationBranch(int gen, int branch) {
    return 'Đời thứ $gen · Nhánh $branch';
  }

  @override
  String get genealogyTitle => 'Gia Phả';

  @override
  String get addBranch => 'Thêm nhánh';

  @override
  String generationLabel(int number) {
    return 'Đời thứ $number';
  }

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
  String deathAnniversaryNotification(String name, int days) {
    return 'Ngày giỗ của $name còn $days ngày nữa';
  }

  @override
  String get profileBirthYear => 'Năm sinh';

  @override
  String get profileStatus => 'Tình trạng';

  @override
  String get profileStatusAlive => 'Còn sống';

  @override
  String get profileDescendants => 'Hậu duệ';

  @override
  String get biographyTitle => 'Tiểu Sử';

  @override
  String get familyRelationsTitle => 'Quan hệ gia đình';

  @override
  String get relationFather => 'Bố';

  @override
  String get relationWife => 'Vợ';

  @override
  String get relationSon => 'Con trai';

  @override
  String get relationDaughter => 'Con gái';

  @override
  String get lunarCalendar => 'Âm lịch';

  @override
  String get solarCalendar => 'Dương lịch';
}
