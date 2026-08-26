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
  String get greeting => 'Welcome';

  @override
  String familyNameTitle(String surname) {
    return 'The $surname Family';
  }

  @override
  String get searchAction => 'Search';

  @override
  String get addMemberAction => 'Add Person';

  @override
  String get eventsAction => 'Events';

  @override
  String get genealogyAction => 'Genealogy';

  @override
  String get upcomingEvents => 'Upcoming Events';

  @override
  String get viewAll => 'View all';

  @override
  String get recentActivity => 'Recent Activity';

  @override
  String hoursAgo(int count) {
    return '$count hours ago';
  }

  @override
  String get loginTitle => 'Sign In';

  @override
  String get loginSubtitle => 'Preserve your roots — Connect the future';

  @override
  String get emailLabel => 'Email';

  @override
  String get emailHint => 'Enter your email';

  @override
  String get passwordLabel => 'Password';

  @override
  String get passwordHint => 'Enter your password';

  @override
  String get forgotPassword => 'Forgot password?';

  @override
  String get loginButton => 'Sign In';

  @override
  String get orDivider => 'Or';

  @override
  String get noAccountPrompt => 'Don\'t have an account? ';

  @override
  String get registerLink => 'Register now';

  @override
  String get registerTitle => 'Create Account';

  @override
  String get registerSubtitle =>
      'Start your journey to preserve family heritage';

  @override
  String get fullNameLabel => 'Full name';

  @override
  String get fullNameHint => 'Enter your full name';

  @override
  String get confirmPasswordLabel => 'Confirm password';

  @override
  String get confirmPasswordHint => 'Re-enter your password';

  @override
  String get registerButton => 'Register';

  @override
  String get hasAccountPrompt => 'Already have an account? ';

  @override
  String get loginLink => 'Sign in';

  @override
  String get membersTitle => 'Members';

  @override
  String get searchMembersHint => 'Search members...';

  @override
  String generationBranch(int gen, int branch) {
    return 'Generation $gen · Branch $branch';
  }

  @override
  String get genealogyTitle => 'Genealogy';

  @override
  String get addBranch => 'Add branch';

  @override
  String generationLabel(int number) {
    return 'Generation $number';
  }

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
  String deathAnniversaryNotification(String name, int days) {
    return '$name\'s death anniversary is in $days days';
  }

  @override
  String get profileBirthYear => 'Birth year';

  @override
  String get profileStatus => 'Status';

  @override
  String get profileStatusAlive => 'Living';

  @override
  String get profileDescendants => 'Descendants';

  @override
  String get biographyTitle => 'Biography';

  @override
  String get familyRelationsTitle => 'Family Relations';

  @override
  String get relationFather => 'Father';

  @override
  String get relationMother => 'Mother';

  @override
  String get relationWife => 'Wife';

  @override
  String get relationHusband => 'Husband';

  @override
  String get relationSon => 'Son';

  @override
  String get relationDaughter => 'Daughter';

  @override
  String get profileStatusDeceased => 'Deceased';

  @override
  String get lunarCalendar => 'Lunar';

  @override
  String get solarCalendar => 'Solar';

  @override
  String get myClansTitle => 'My clans';

  @override
  String get clanPickerTitle => 'Choose a clan';

  @override
  String clanCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count clans',
      one: '1 clan',
      zero: 'No clans',
    );
    return '$_temp0';
  }

  @override
  String staleDataBanner(String date) {
    return 'Data from $date';
  }

  @override
  String get signOutAction => 'Sign out';

  @override
  String get retryAction => 'Retry';

  @override
  String get errorOffline => 'No network connection';

  @override
  String get errorTimeout => 'The server took too long to respond';

  @override
  String get errorUnexpected => 'Something went wrong';

  @override
  String errorTraceId(String traceId) {
    return 'Error id: $traceId';
  }

  @override
  String get pendingApprovalTitle => 'Awaiting approval';

  @override
  String get pendingApprovalBody =>
      'Your join request is waiting for a clan admin to approve it.';

  @override
  String get verifyEmailTitle => 'Verify your email';

  @override
  String get verifyEmailBody =>
      'Open your email and tap the verification link.';

  @override
  String get resendVerificationAction => 'Resend verification email';

  @override
  String get onboardingTitle => 'Join a clan';

  @override
  String get onboardingUnavailableBody =>
      'You do not belong to any clan yet, and you have sent no join request. This app does not have the step to join or create a clan yet, so you cannot go further here.';

  @override
  String get accountBlockedTitle => 'Account blocked';

  @override
  String get clanSuspendedTitle => 'Clan suspended';
}
