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
/// import 'l10n/app_localizations.dart';
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
    Locale('vi')
  ];

  /// The name of the application
  ///
  /// In en, this message translates to:
  /// **'FamilyRoots'**
  String get appName;

  /// Home page greeting
  ///
  /// In en, this message translates to:
  /// **'Welcome'**
  String get greeting;

  /// Main family name on home page
  ///
  /// In en, this message translates to:
  /// **'The {surname} Family'**
  String familyNameTitle(String surname);

  /// Quick action: search
  ///
  /// In en, this message translates to:
  /// **'Search'**
  String get searchAction;

  /// Quick action: add member
  ///
  /// In en, this message translates to:
  /// **'Add Person'**
  String get addMemberAction;

  /// Quick action: events
  ///
  /// In en, this message translates to:
  /// **'Events'**
  String get eventsAction;

  /// Quick action: genealogy
  ///
  /// In en, this message translates to:
  /// **'Genealogy'**
  String get genealogyAction;

  /// Section title for events
  ///
  /// In en, this message translates to:
  /// **'Upcoming Events'**
  String get upcomingEvents;

  /// View all button text
  ///
  /// In en, this message translates to:
  /// **'View all'**
  String get viewAll;

  /// Section title for activity feed
  ///
  /// In en, this message translates to:
  /// **'Recent Activity'**
  String get recentActivity;

  /// Relative time display
  ///
  /// In en, this message translates to:
  /// **'{count} hours ago'**
  String hoursAgo(int count);

  /// Login screen title
  ///
  /// In en, this message translates to:
  /// **'Sign In'**
  String get loginTitle;

  /// Login screen subtitle
  ///
  /// In en, this message translates to:
  /// **'Preserve your roots — Connect the future'**
  String get loginSubtitle;

  /// Email field label
  ///
  /// In en, this message translates to:
  /// **'Email'**
  String get emailLabel;

  /// Email field placeholder
  ///
  /// In en, this message translates to:
  /// **'Enter your email'**
  String get emailHint;

  /// Password field label
  ///
  /// In en, this message translates to:
  /// **'Password'**
  String get passwordLabel;

  /// Password field placeholder
  ///
  /// In en, this message translates to:
  /// **'Enter your password'**
  String get passwordHint;

  /// Forgot password link
  ///
  /// In en, this message translates to:
  /// **'Forgot password?'**
  String get forgotPassword;

  /// Login button text
  ///
  /// In en, this message translates to:
  /// **'Sign In'**
  String get loginButton;

  /// Divider between login methods
  ///
  /// In en, this message translates to:
  /// **'Or'**
  String get orDivider;

  /// Register prompt text
  ///
  /// In en, this message translates to:
  /// **'Don\'t have an account? '**
  String get noAccountPrompt;

  /// Register link text
  ///
  /// In en, this message translates to:
  /// **'Register now'**
  String get registerLink;

  /// Register screen title
  ///
  /// In en, this message translates to:
  /// **'Create Account'**
  String get registerTitle;

  /// Register screen subtitle
  ///
  /// In en, this message translates to:
  /// **'Start your journey to preserve family heritage'**
  String get registerSubtitle;

  /// Full name field label
  ///
  /// In en, this message translates to:
  /// **'Full name'**
  String get fullNameLabel;

  /// Full name field placeholder
  ///
  /// In en, this message translates to:
  /// **'Enter your full name'**
  String get fullNameHint;

  /// Confirm password field label
  ///
  /// In en, this message translates to:
  /// **'Confirm password'**
  String get confirmPasswordLabel;

  /// Confirm password field placeholder
  ///
  /// In en, this message translates to:
  /// **'Re-enter your password'**
  String get confirmPasswordHint;

  /// Register button text
  ///
  /// In en, this message translates to:
  /// **'Register'**
  String get registerButton;

  /// Login prompt text
  ///
  /// In en, this message translates to:
  /// **'Already have an account? '**
  String get hasAccountPrompt;

  /// Login link text
  ///
  /// In en, this message translates to:
  /// **'Sign in'**
  String get loginLink;

  /// Member directory title
  ///
  /// In en, this message translates to:
  /// **'Members'**
  String get membersTitle;

  /// Member search placeholder
  ///
  /// In en, this message translates to:
  /// **'Search members...'**
  String get searchMembersHint;

  /// Member generation and branch info
  ///
  /// In en, this message translates to:
  /// **'Generation {gen} · Branch {branch}'**
  String generationBranch(int gen, int branch);

  /// Family tree page title
  ///
  /// In en, this message translates to:
  /// **'Genealogy'**
  String get genealogyTitle;

  /// Add branch FAB label
  ///
  /// In en, this message translates to:
  /// **'Add branch'**
  String get addBranch;

  /// Generation label in family tree
  ///
  /// In en, this message translates to:
  /// **'Generation {number}'**
  String generationLabel(int number);

  /// Member count with plural
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =0{No members} =1{1 member} other{{count} members}}'**
  String memberCount(int count);

  /// Notification for upcoming death anniversary
  ///
  /// In en, this message translates to:
  /// **'{name}\'s death anniversary is in {days} days'**
  String deathAnniversaryNotification(String name, int days);

  /// Profile stat label
  ///
  /// In en, this message translates to:
  /// **'Birth year'**
  String get profileBirthYear;

  /// Profile stat label
  ///
  /// In en, this message translates to:
  /// **'Status'**
  String get profileStatus;

  /// Living status
  ///
  /// In en, this message translates to:
  /// **'Living'**
  String get profileStatusAlive;

  /// Deceased status
  ///
  /// In en, this message translates to:
  /// **'Deceased'**
  String get profileStatusDeceased;

  /// Profile stat label
  ///
  /// In en, this message translates to:
  /// **'Descendants'**
  String get profileDescendants;

  /// Biography section title
  ///
  /// In en, this message translates to:
  /// **'Biography'**
  String get biographyTitle;

  /// Family relations section title
  ///
  /// In en, this message translates to:
  /// **'Family Relations'**
  String get familyRelationsTitle;

  /// Father relation
  ///
  /// In en, this message translates to:
  /// **'Father'**
  String get relationFather;

  /// Wife relation
  ///
  /// In en, this message translates to:
  /// **'Wife'**
  String get relationWife;

  /// Husband relation
  ///
  /// In en, this message translates to:
  /// **'Husband'**
  String get relationHusband;

  /// Son relation
  ///
  /// In en, this message translates to:
  /// **'Son'**
  String get relationSon;

  /// Daughter relation
  ///
  /// In en, this message translates to:
  /// **'Daughter'**
  String get relationDaughter;

  /// Mother relation
  ///
  /// In en, this message translates to:
  /// **'Mother'**
  String get relationMother;

  /// Lunar calendar tag
  ///
  /// In en, this message translates to:
  /// **'Lunar'**
  String get lunarCalendar;

  /// Solar calendar tag
  ///
  /// In en, this message translates to:
  /// **'Solar'**
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
      'that was used.');
}
