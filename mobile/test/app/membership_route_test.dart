// Seed S-093. Two states the domain layer distinguished — a pending member and
// a person attached to no clan at all — reached one screen, and that screen
// said "your join request is waiting" to somebody who had made no request.
//
// **These tests read the screen the app actually renders, never a predicate.**
// `UserProfile.needsOnboarding` already returned the right answer for 23 days
// while the router ignored it (`docs/SEEDS.md`, S-093), so a test that asserts
// the getter would have been green throughout the defect. That is the shape
// `.claude/rules/seeds.md` § "A test pins an outcome, not a setting" forbids,
// and the same rule's mobile instance — `dividerTheme.thickness == 0`, green
// for 19 days — is why it is written down.
//
// Nothing here names `MembershipStatus` or any router flag on purpose: the
// whole file compiles against the code from before the fix, which is what
// makes its failure against that code a real negative control.
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:family_roots_mobile/app/app.dart';
import 'package:family_roots_mobile/app/router/routes.dart';
import 'package:family_roots_mobile/features/auth/auth.dart';
import 'package:family_roots_mobile/features/clan/clan.dart';

import '../support/load_app_fonts.dart';
import '../support/main_container.dart';
import '../support/sequence_adapter.dart';

/// Copied from `lib/core/l10n/app_vi.arb`. `vi` is the app's default locale, so
/// this is the copy a user sees. Hard-coded rather than read back through
/// `AppLocalizations`, because reading the string through the same table that
/// produced it would assert nothing about which one the screen chose.
const _viPendingBody =
    'Yêu cầu tham gia của bạn đang chờ quản trị viên dòng họ duyệt.';
const _viOnboardingBody =
    'Bạn chưa thuộc dòng họ nào và cũng chưa gửi yêu cầu tham gia nào. '
    'Ứng dụng này chưa có bước tham gia hoặc tạo dòng họ, nên bạn chưa thể '
    'đi tiếp từ đây.';

/// Shape copied from `docs/contracts/rest-auth-api.md` §`POST /login`. The
/// nested `user` is discarded by [SessionController], which re-reads the
/// profile from `GET /auth/me`; only the tokens matter here.
const _login = <String, Object?>{
  'data': <String, Object?>{
    'access_token': 'eyJhbGciOi...',
    'refresh_token': 'v1.Mr7...',
    'expires_in': 3600,
    'user': <String, Object?>{
      'id': 'u1',
      'email': 'minh@example.com',
      'full_name': 'Nguyễn Văn Minh',
      'clan_id': null,
      'clan_name': null,
      'role': null,
      'is_approved': false,
      'has_pending_membership': false,
      'person_id': null,
      'preferred_locale': 'vi',
    },
  },
};

/// `GET /auth/me` — the profile object directly under `data`
/// (`docs/contracts/rest-auth-api.md`, `GET /me`).
Map<String, Object?> _me({
  required String? clanId,
  required bool isApproved,
  required bool hasPendingMembership,
}) => <String, Object?>{
  'data': <String, Object?>{
    'id': 'u1',
    'email': 'minh@example.com',
    'full_name': 'Nguyễn Văn Minh',
    'clan_id': clanId,
    'clan_name': clanId == null ? null : 'Họ Lê',
    'role': isApproved ? 'admin' : null,
    'is_approved': isApproved,
    'has_pending_membership': hasPendingMembership,
    'person_id': null,
    'preferred_locale': 'vi',
  },
};

/// `GET /me/clans` — approved memberships only, so it is empty for anyone who
/// is not approved (`docs/contracts/frontend-integration-guide.md:299-300`).
const _noClans = <String, Object?>{'data': <Object?>[]};
const _oneClan = <String, Object?>{
  'data': <Object?>[
    <String, Object?>{
      'clan_id': 'c1',
      'clan_name': 'Họ Nguyễn Phúc',
      'clan_slug': 'ho-nguyen-phuc',
      'role': 'admin',
      'joined_at': null,
    },
  ],
};

/// Assembles the real app over the real router and signs a user in, so the
/// reading below is the destination the app produced for that profile — not a
/// destination the test set by hand.
Future<SequenceAdapter> _signIn(
  WidgetTester tester, {
  required Map<String, Object?> me,
  Map<String, Object?> clans = _noClans,
  bool loadClanList = false,
}) async {
  final adapter = SequenceAdapter(<Canned>[
    const Canned(200, _login),
    Canned(200, me),
    Canned(200, clans),
  ]);
  final container = await mainContainer(adapter: adapter);
  addTearDown(container.dispose);

  await tester.pumpWidget(
    UncontrolledProviderScope(
      container: container,
      child: const FamilyRootsApp(),
    ),
  );
  await tester.pumpAndSettle();
  expect(find.byKey(RouteKeys.login), findsOneWidget);

  // `runAsync`, not a bare `await`. Measured 2026-08-26 in this worktree:
  // awaiting this future directly inside a `testWidgets` body hangs for as
  // long as you leave it — 25 minutes, no output, `flutter_tester` at 0% CPU,
  // and the per-test timeout never fires, because the fake clock never
  // advances. Dio schedules work that needs a real event-loop turn, and the
  // fake-async zone only turns it when the tester pumps, which an `await`
  // never does. `runAsync` runs the request in the real zone; the pump after
  // it is what lets the router act on the new session. Verified 2026-08-27:
  // the same test finishes in under a second this way. See mobile/CLAUDE.md,
  // test-host trap 2.
  await tester.runAsync(() async {
    await container
        .read(sessionControllerProvider.notifier)
        .signIn(email: 'minh@example.com', password: 'secret');
    // Only `/clans` needs this. It renders a `CircularProgressIndicator` while
    // `GET /me/clans` is in flight, and an indeterminate spinner never
    // settles, so `pumpAndSettle` below times out instead of failing on the
    // assertion. Resolving the list here — still in the real zone — means the
    // approved user's screen is the loaded one, which is also the screen the
    // reading is about.
    if (loadClanList) await container.read(myClansProvider.future);
  });
  await tester.pumpAndSettle();
  return adapter;
}

void main() {
  setUpAll(loadAppFonts);

  testWidgets('a clanless profile reaches the onboarding copy, and is never '
      'told a request is waiting', (tester) async {
    final adapter = await _signIn(
      tester,
      // The triple spec § 7.2a names: is_approved false,
      // has_pending_membership false, clan_id null. Reachable through
      // registration since ADR-058.
      me: _me(clanId: null, isApproved: false, hasPendingMembership: false),
    );

    expect(
      find.text(_viOnboardingBody),
      findsOneWidget,
      reason:
          'a person attached to no clan must be told that, not that an '
          'admin is reviewing a request they never sent',
    );
    expect(find.text('Tham gia dòng họ'), findsOneWidget);
    expect(find.text(_viPendingBody), findsNothing);
    expect(find.text('Đang chờ duyệt'), findsNothing);
    // The positional canning above only lines up if the app asks in this
    // order, so the order is pinned: a future extra call fails loudly here
    // rather than silently handing one endpoint another endpoint's body.
    //
    // Only the two calls sign-in itself makes are pinned. Measured
    // 2026-08-27: `GET /me/clans` is *not* reached in these tests, because
    // `clanPickRequiredProvider` fires it back inside the fake-async zone,
    // where the request never turns over. That is a property of the test host,
    // not of the routing decision under test, so asserting either way about it
    // would be asserting something about `flutter test` rather than about the
    // app.
    expect(adapter.received.map((r) => r.path).take(2).toList(), <String>[
      '/auth/login',
      '/auth/me',
    ]);
  });

  testWidgets('a pending profile reaches the waiting copy', (tester) async {
    await _signIn(
      tester,
      me: _me(clanId: 'c1', isApproved: false, hasPendingMembership: true),
    );

    expect(find.text(_viPendingBody), findsOneWidget);
    expect(find.text('Đang chờ duyệt'), findsOneWidget);
    expect(find.text(_viOnboardingBody), findsNothing);
  });

  testWidgets('an approved profile reaches the clan list, not either message '
      'screen', (tester) async {
    await _signIn(
      tester,
      me: _me(clanId: 'c1', isApproved: true, hasPendingMembership: false),
      clans: _oneClan,
      loadClanList: true,
    );

    expect(find.byKey(RouteKeys.clans), findsOneWidget);
    expect(find.byKey(RouteKeys.pending), findsNothing);
    expect(find.text(_viPendingBody), findsNothing);
    expect(find.text(_viOnboardingBody), findsNothing);
  });

  testWidgets('the combination the contract forbids still lands on copy that '
      'is true', (tester) async {
    // `clan_id` non-null with `is_approved` false names a membership row whose
    // own `is_approved` is false, so `has_pending_membership` cannot be false
    // as well (`docs/contracts/rest-auth-api.md:124-125,132-133`). The client
    // still has to answer, and "attached to a clan, not approved" reads as
    // waiting — so it must not fall through to the onboarding copy, which
    // would tell a clan's applicant they belong to no clan.
    await _signIn(
      tester,
      me: _me(clanId: 'c1', isApproved: false, hasPendingMembership: false),
    );

    expect(find.byKey(RouteKeys.pending), findsOneWidget);
    expect(find.text(_viPendingBody), findsOneWidget);
    expect(find.text(_viOnboardingBody), findsNothing);
  });
}
