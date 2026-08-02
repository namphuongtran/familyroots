import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localizations_en.dart';
import 'app_localizations_vi.dart';

// ignore_for_file: type=lint

/// Callers can lookup localized strings with an instance of AppLocalizations
/// returned by `AppLocalizations.of(context)`.
///
/// Applications need to include `AppLocalizations.delegate()` in their app's
/// `localizationDelegates` list, and the locales they support in the app's
/// `supportedLocales` list. For example:
///
/// ```dart
/// import 'generated/app_localizations.dart';
///
/// return MaterialApp(
///   localizationsDelegates: AppLocalizations.localizationsDelegates,
///   supportedLocales: AppLocalizations.supportedLocales,
///   home: MyApplicationHome(),
/// );
/// ```
///
/// ## Update pubspec.yaml
///
/// Please make sure to update your pubspec.yaml to include the following
/// packages:
///
/// ```yaml
/// dependencies:
///   # Internationalization support.
///   flutter_localizations:
///     sdk: flutter
///   intl: any # Use the pinned version from flutter_localizations
///
///   # Rest of dependencies
/// ```
///
/// ## iOS Applications
///
/// iOS applications define key application metadata, including supported
/// locales, in an Info.plist file that is built into the application bundle.
/// To configure the locales supported by your app, you’ll need to edit this
/// file.
///
/// First, open your project’s ios/Runner.xcworkspace Xcode workspace file.
/// Then, in the Project Navigator, open the Info.plist file under the Runner
/// project’s Runner folder.
///
/// Next, select the Information Property List item, select Add Item from the
/// Editor menu, then select Localizations from the pop-up menu.
///
/// Select and expand the newly-created Localizations item then, for each
/// locale your application supports, add a new item and select the locale
/// you wish to add from the pop-up menu in the Value field. This list should
/// be consistent with the languages listed in the AppLocalizations.supportedLocales
/// property.
abstract class AppLocalizations {
  AppLocalizations(String locale)
    : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static AppLocalizations of(BuildContext context) {
    return Localizations.of<AppLocalizations>(context, AppLocalizations)!;
  }

  static const LocalizationsDelegate<AppLocalizations> delegate =
      _AppLocalizationsDelegate();

  /// A list of this localizations delegate along with the default localizations
  /// delegates.
  ///
  /// Returns a list of localizations delegates containing this delegate along with
  /// GlobalMaterialLocalizations.delegate, GlobalCupertinoLocalizations.delegate,
  /// and GlobalWidgetsLocalizations.delegate.
  ///
  /// Additional delegates can be added by appending to this list in
  /// MaterialApp. This list does not have to be used at all if a custom list
  /// of delegates is preferred or required.
  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates =
      <LocalizationsDelegate<dynamic>>[
        delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
      ];

  /// A list of this localizations delegate's supported locales.
  static const List<Locale> supportedLocales = <Locale>[
    Locale('en'),
    Locale('vi'),
  ];

  /// No description provided for @appName.
  ///
  /// In vi, this message translates to:
  /// **'Gia Phả'**
  String get appName;

  /// No description provided for @greeting.
  ///
  /// In vi, this message translates to:
  /// **'Kính chào'**
  String get greeting;

  /// Main family name on home page
  ///
  /// In vi, this message translates to:
  /// **'Dòng họ {surname}'**
  String familyNameTitle(String surname);

  /// No description provided for @searchAction.
  ///
  /// In vi, this message translates to:
  /// **'Tìm kiếm'**
  String get searchAction;

  /// No description provided for @addMemberAction.
  ///
  /// In vi, this message translates to:
  /// **'Thêm người'**
  String get addMemberAction;

  /// No description provided for @eventsAction.
  ///
  /// In vi, this message translates to:
  /// **'Sự kiện'**
  String get eventsAction;

  /// No description provided for @genealogyAction.
  ///
  /// In vi, this message translates to:
  /// **'Gia phả'**
  String get genealogyAction;

  /// No description provided for @upcomingEvents.
  ///
  /// In vi, this message translates to:
  /// **'Sự Kiện Sắp Tới'**
  String get upcomingEvents;

  /// No description provided for @viewAll.
  ///
  /// In vi, this message translates to:
  /// **'Xem tất cả'**
  String get viewAll;

  /// No description provided for @recentActivity.
  ///
  /// In vi, this message translates to:
  /// **'Hoạt Động Mới Nhất'**
  String get recentActivity;

  /// Relative time display
  ///
  /// In vi, this message translates to:
  /// **'{count} giờ trước'**
  String hoursAgo(int count);

  /// No description provided for @loginTitle.
  ///
  /// In vi, this message translates to:
  /// **'Đăng nhập'**
  String get loginTitle;

  /// No description provided for @loginSubtitle.
  ///
  /// In vi, this message translates to:
  /// **'Lưu giữ cội nguồn - Kết nối tương lai'**
  String get loginSubtitle;

  /// No description provided for @emailLabel.
  ///
  /// In vi, this message translates to:
  /// **'Email'**
  String get emailLabel;

  /// No description provided for @emailHint.
  ///
  /// In vi, this message translates to:
  /// **'Nhập email của bạn'**
  String get emailHint;

  /// No description provided for @passwordLabel.
  ///
  /// In vi, this message translates to:
  /// **'Mật khẩu'**
  String get passwordLabel;

  /// No description provided for @passwordHint.
  ///
  /// In vi, this message translates to:
  /// **'Nhập mật khẩu'**
  String get passwordHint;

  /// No description provided for @forgotPassword.
  ///
  /// In vi, this message translates to:
  /// **'Quên mật khẩu?'**
  String get forgotPassword;

  /// No description provided for @loginButton.
  ///
  /// In vi, this message translates to:
  /// **'Đăng Nhập'**
  String get loginButton;

  /// No description provided for @orDivider.
  ///
  /// In vi, this message translates to:
  /// **'Hoặc'**
  String get orDivider;

  /// No description provided for @noAccountPrompt.
  ///
  /// In vi, this message translates to:
  /// **'Chưa có tài khoản? '**
  String get noAccountPrompt;

  /// No description provided for @registerLink.
  ///
  /// In vi, this message translates to:
  /// **'Đăng ký ngay'**
  String get registerLink;

  /// No description provided for @registerTitle.
  ///
  /// In vi, this message translates to:
  /// **'Tạo Tài Khoản'**
  String get registerTitle;

  /// No description provided for @registerSubtitle.
  ///
  /// In vi, this message translates to:
  /// **'Bắt đầu hành trình lưu giữ di sản gia đình'**
  String get registerSubtitle;

  /// No description provided for @fullNameLabel.
  ///
  /// In vi, this message translates to:
  /// **'Họ và tên'**
  String get fullNameLabel;

  /// No description provided for @fullNameHint.
  ///
  /// In vi, this message translates to:
  /// **'Nhập họ và tên của bạn'**
  String get fullNameHint;

  /// No description provided for @confirmPasswordLabel.
  ///
  /// In vi, this message translates to:
  /// **'Xác nhận mật khẩu'**
  String get confirmPasswordLabel;

  /// No description provided for @confirmPasswordHint.
  ///
  /// In vi, this message translates to:
  /// **'Nhập lại mật khẩu'**
  String get confirmPasswordHint;

  /// No description provided for @registerButton.
  ///
  /// In vi, this message translates to:
  /// **'Đăng Ký'**
  String get registerButton;

  /// No description provided for @hasAccountPrompt.
  ///
  /// In vi, this message translates to:
  /// **'Đã có tài khoản? '**
  String get hasAccountPrompt;

  /// No description provided for @loginLink.
  ///
  /// In vi, this message translates to:
  /// **'Đăng nhập'**
  String get loginLink;

  /// No description provided for @membersTitle.
  ///
  /// In vi, this message translates to:
  /// **'Thành viên'**
  String get membersTitle;

  /// No description provided for @searchMembersHint.
  ///
  /// In vi, this message translates to:
  /// **'Tìm kiếm thành viên...'**
  String get searchMembersHint;

  /// Member generation and branch info
  ///
  /// In vi, this message translates to:
  /// **'Đời thứ {gen} · Nhánh {branch}'**
  String generationBranch(int gen, int branch);

  /// No description provided for @genealogyTitle.
  ///
  /// In vi, this message translates to:
  /// **'Gia Phả'**
  String get genealogyTitle;

  /// No description provided for @addBranch.
  ///
  /// In vi, this message translates to:
  /// **'Thêm nhánh'**
  String get addBranch;

  /// Generation label in family tree
  ///
  /// In vi, this message translates to:
  /// **'Đời thứ {number}'**
  String generationLabel(int number);

  /// Member count with plural
  ///
  /// In vi, this message translates to:
  /// **'{count, plural, =0{Chưa có thành viên} =1{1 thành viên} other{{count} thành viên}}'**
  String memberCount(int count);

  /// Notification for upcoming death anniversary
  ///
  /// In vi, this message translates to:
  /// **'Ngày giỗ của {name} còn {days} ngày nữa'**
  String deathAnniversaryNotification(String name, int days);

  /// No description provided for @profileBirthYear.
  ///
  /// In vi, this message translates to:
  /// **'Năm sinh'**
  String get profileBirthYear;

  /// No description provided for @profileStatus.
  ///
  /// In vi, this message translates to:
  /// **'Tình trạng'**
  String get profileStatus;

  /// No description provided for @profileStatusAlive.
  ///
  /// In vi, this message translates to:
  /// **'Còn sống'**
  String get profileStatusAlive;

  /// No description provided for @profileDescendants.
  ///
  /// In vi, this message translates to:
  /// **'Hậu duệ'**
  String get profileDescendants;

  /// No description provided for @biographyTitle.
  ///
  /// In vi, this message translates to:
  /// **'Tiểu Sử'**
  String get biographyTitle;

  /// No description provided for @familyRelationsTitle.
  ///
  /// In vi, this message translates to:
  /// **'Quan hệ gia đình'**
  String get familyRelationsTitle;

  /// No description provided for @relationFather.
  ///
  /// In vi, this message translates to:
  /// **'Bố'**
  String get relationFather;

  /// No description provided for @relationMother.
  ///
  /// In vi, this message translates to:
  /// **'Mẹ'**
  String get relationMother;

  /// No description provided for @relationWife.
  ///
  /// In vi, this message translates to:
  /// **'Vợ'**
  String get relationWife;

  /// No description provided for @relationHusband.
  ///
  /// In vi, this message translates to:
  /// **'Chồng'**
  String get relationHusband;

  /// No description provided for @relationSon.
  ///
  /// In vi, this message translates to:
  /// **'Con trai'**
  String get relationSon;

  /// No description provided for @relationDaughter.
  ///
  /// In vi, this message translates to:
  /// **'Con gái'**
  String get relationDaughter;

  /// No description provided for @profileStatusDeceased.
  ///
  /// In vi, this message translates to:
  /// **'Đã mất'**
  String get profileStatusDeceased;

  /// No description provided for @lunarCalendar.
  ///
  /// In vi, this message translates to:
  /// **'Âm lịch'**
  String get lunarCalendar;

  /// No description provided for @solarCalendar.
  ///
  /// In vi, this message translates to:
  /// **'Dương lịch'**
  String get solarCalendar;
}

class _AppLocalizationsDelegate
    extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  Future<AppLocalizations> load(Locale locale) {
    return SynchronousFuture<AppLocalizations>(lookupAppLocalizations(locale));
  }

  @override
  bool isSupported(Locale locale) =>
      <String>['en', 'vi'].contains(locale.languageCode);

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}

AppLocalizations lookupAppLocalizations(Locale locale) {
  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'en':
      return AppLocalizationsEn();
    case 'vi':
      return AppLocalizationsVi();
  }

  throw FlutterError(
    'AppLocalizations.delegate failed to load unsupported locale "$locale". This is likely '
    'an issue with the localizations generation tool. Please file an issue '
    'on GitHub with a reproducible sample app and the gen-l10n configuration '
    'that was used.',
  );
}
