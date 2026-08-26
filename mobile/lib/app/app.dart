import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/l10n/generated/app_localizations.dart';
import '../core/theme/app_theme.dart';
import '../domain/auth/user_profile.dart';
import '../features/auth/auth.dart';
import '../features/clan/clan.dart';
import 'router/app_router.dart';

class FamilyRootsApp extends ConsumerStatefulWidget {
  const FamilyRootsApp({super.key});

  @override
  ConsumerState<FamilyRootsApp> createState() => _FamilyRootsAppState();
}

class _FamilyRootsAppState extends ConsumerState<FamilyRootsApp> {
  late final AuthRouteState _authRouteState;
  late final _router = buildRouter(_authRouteState);

  @override
  void initState() {
    super.initState();
    // Shared with the widget tree via authRouteStateProvider, so a screen that
    // clears a guard (the clan picker) mutates the same instance the router is
    // listening to.
    _authRouteState = ref.read(authRouteStateProvider);
  }

  @override
  Widget build(BuildContext context) {
    // Bridge Riverpod state onto the router's ChangeNotifier.
    ref.listen(sessionControllerProvider, (previous, next) {
      final profile = next.value;
      _authRouteState.set(
        signedIn: profile != null,
        // The whole three-way answer, not `isApproved` flattened to a bool: a
        // clanless user and a pending user need different copy on the same
        // route (spec § 7.2a, seed S-093). No profile means signed out, so the
        // membership guard must not hold anyone anywhere.
        membership: profile?.membershipStatus ?? MembershipStatus.approved,
      );
    });

    // Clan resolution decides whether the picker is required. Gated on a
    // session (see clanPickRequiredProvider) so nothing calls GET /me/clans
    // before sign-in. The picker also clears this itself before navigating —
    // see authRouteStateProvider.
    ref.listen(clanPickRequiredProvider, (previous, next) {
      final required = next.value;
      if (required == null) return;
      _authRouteState.set(needsClanPick: required);
    });

    return MaterialApp.router(
      routerConfig: _router,
      theme: buildAppTheme(),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      // vi is default and fallback; nothing assumes the set is exactly two.
      // Seeded from PrefsStore rather than the device locale, because vi is
      // the documented default (plan open question 5).
      locale: Locale(ref.watch(prefsStoreProvider).readLocale() ?? 'vi'),
    );
  }
}
