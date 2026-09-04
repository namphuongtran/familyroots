import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../domain/auth/user_profile.dart';
import '../../features/auth/auth.dart';
import '../../features/clan/clan.dart';
import 'routes.dart';

/// Whether the clan picker is required — **gated on there being a session**.
///
/// Watching `clanResolutionProvider` directly from the app shell fires
/// `GET /me/clans` the moment the app starts, before anyone has signed in.
/// That is an unauthenticated request to a clan-scoped-adjacent endpoint: it
/// 401s, the refresh interceptor then finds no session to refresh, and the
/// result is a sign-out triggered by app launch. It also blocks the login
/// screen behind a network round-trip it has no reason to make.
final clanPickRequiredProvider = FutureProvider<bool>((ref) async {
  final profile = await ref.watch(sessionControllerProvider.future);
  if (profile == null) return false;
  final resolution = await ref.watch(clanResolutionProvider.future);
  return resolution == ClanResolution.needsPicker;
});

/// The live [AuthRouteState] the router is listening to, so a screen that
/// changes a guard condition can clear it *before* it navigates.
///
/// That ordering is load-bearing, not incidental. go_router 17 re-runs
/// `redirect` for the CURRENT location, so:
///   * navigating first bounces straight back — the guard still holds; and
///   * clearing first without navigating leaves you where you are, because
///     `redirect` returns null for the location you are already on.
/// Only "clear, then navigate" escapes the picker. Overridden in
/// ProviderScope at bootstrap.
final authRouteStateProvider = Provider<AuthRouteState>(
  (ref) => throw UnimplementedError('override in ProviderScope'),
);

/// Drives router re-evaluation when session or clan state changes.
class AuthRouteState extends ChangeNotifier {
  bool signedIn = false;
  bool emailVerified = true;

  /// Three states, not a boolean. Flattening `pending` and `onboarding` into
  /// one flag is what sent a clanless user to a screen saying their join
  /// request was waiting.
  MembershipStatus membership = MembershipStatus.approved;
  bool needsClanPick = false;

  void set({
    bool? signedIn,
    bool? emailVerified,
    MembershipStatus? membership,
    bool? needsClanPick,
  }) {
    this.signedIn = signedIn ?? this.signedIn;
    this.emailVerified = emailVerified ?? this.emailVerified;
    this.membership = membership ?? this.membership;
    this.needsClanPick = needsClanPick ?? this.needsClanPick;
    notifyListeners();
  }
}

const _publicRoutes = <String>{Routes.login, Routes.verifyEmail};

GoRouter buildRouter(AuthRouteState auth) {
  return GoRouter(
    initialLocation: '/login',
    refreshListenable: auth,
    redirect: (BuildContext context, GoRouterState state) {
      final loc = state.matchedLocation;
      if (!auth.signedIn) {
        return _publicRoutes.contains(loc) ? null : Routes.login;
      }
      if (!auth.emailVerified) {
        return loc == Routes.verifyEmail ? null : Routes.verifyEmail;
      }
      // One route for both non-approved states, per spec § 7.2a: the
      // no-membership case is the "onboarding variant of this screen", so what
      // changes is the copy [PendingApprovalPage] renders, not the path.
      if (auth.membership != MembershipStatus.approved) {
        return loc == Routes.pending ? null : Routes.pending;
      }
      if (auth.needsClanPick) {
        return loc == Routes.clanPicker ? null : Routes.clanPicker;
      }
      if (_publicRoutes.contains(loc)) return Routes.clans;
      return null;
    },
    // `(_, _)` is two bare underscores: flutter_lints 6 flags `(_, __)` as
    // unnecessary_underscores.
    routes: <RouteBase>[
      GoRoute(path: Routes.login, builder: (_, _) => const LoginRoute()),
      GoRoute(
        path: Routes.verifyEmail,
        builder: (_, _) => const VerifyEmailRoute(),
      ),
      GoRoute(path: Routes.pending, builder: (_, _) => const PendingRoute()),
      GoRoute(
        path: Routes.clanPicker,
        builder: (_, _) => const ClanPickerRoute(),
      ),
      GoRoute(path: Routes.clans, builder: (_, _) => const MyClansRoute()),
    ],
  );
}
