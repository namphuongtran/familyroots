import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../domain/clan/clan_membership.dart';
import '../../features/auth/auth.dart';
import '../../features/clan/clan.dart';
import '../../shared/widgets/error_view.dart';
import 'app_router.dart';

/// Route paths in one place so guards and navigation cannot drift apart.
abstract final class Routes {
  static const login = '/login';
  static const verifyEmail = '/verify-email';
  static const pending = '/pending';
  static const clanPicker = '/clan-picker';
  static const clans = '/clans';
}

/// Keys let the router test assert *which route rendered* without depending on
/// the copy inside it.
abstract final class RouteKeys {
  static const login = Key('route-login');
  static const verifyEmail = Key('route-verify-email');
  static const pending = Key('route-pending');
  static const clanPicker = Key('route-clan-picker');
  static const clans = Key('route-clans');
}

/// Shared async scaffolding: a spinner while loading, [ErrorView] on failure.
/// The key stays attached in every state so route assertions are stable
/// regardless of whether the request has resolved.
class _AsyncClans extends ConsumerWidget {
  const _AsyncClans({required this.routeKey, required this.builder});

  final Key routeKey;
  final Widget Function(BuildContext, WidgetRef, List<ClanMembership>) builder;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final clans = ref.watch(myClansProvider);
    return KeyedSubtree(
      key: routeKey,
      child: clans.when(
        loading: () =>
            const Scaffold(body: Center(child: CircularProgressIndicator())),
        error: (e, _) => Scaffold(
          body: Center(
            child: ErrorView(
              error: e,
              onRetry: () => ref.invalidate(myClansProvider),
            ),
          ),
        ),
        data: (list) => builder(context, ref, list),
      ),
    );
  }
}

/// `/clans` — the signed-in landing screen.
class MyClansRoute extends StatelessWidget {
  const MyClansRoute({super.key});

  @override
  Widget build(BuildContext context) => _AsyncClans(
    routeKey: RouteKeys.clans,
    builder: (context, ref, list) => MyClansView(
      clans: list,
      // Selecting from the list re-scopes the app to that clan.
      onSelect: (clan) =>
          ref.read(selectedClanProvider.notifier).select(clan.clanId),
    ),
  );
}

/// `/clan-picker` — shown when the user has several approved memberships.
class ClanPickerRoute extends StatelessWidget {
  const ClanPickerRoute({super.key});

  @override
  Widget build(BuildContext context) => _AsyncClans(
    routeKey: RouteKeys.clanPicker,
    builder: (context, ref, list) => ClanPickerView(
      clans: list,
      onSelect: (clan) async {
        await ref.read(selectedClanProvider.notifier).select(clan.clanId);
        if (!context.mounted) return;
        // Order matters, and both halves are required (plan V13):
        //   1. clear the guard FIRST — navigating while it still holds gets
        //      redirected straight back here; and
        //   2. navigate explicitly — clearing alone leaves the user on this
        //      screen, because redirect returns null for the current location.
        ref.read(authRouteStateProvider).set(needsClanPick: false);
        context.go(Routes.clans);
      },
    ),
  );
}

/// `/verify-email` — offers resend only when we know which address to use.
class VerifyEmailRoute extends ConsumerWidget {
  const VerifyEmailRoute({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Riverpod 3.2.1 exposes the nullable accessor as `value`, not
    // `valueOrNull` — the latter does not exist on AsyncValue in this version.
    final email = ref.watch(sessionControllerProvider).value?.email;
    return KeyedSubtree(
      key: RouteKeys.verifyEmail,
      child: VerifyEmailPage(email: email),
    );
  }
}

/// `/pending` — a stable keyed wrapper so the router can assert this route.
class PendingRoute extends StatelessWidget {
  const PendingRoute({super.key});

  @override
  Widget build(BuildContext context) =>
      const KeyedSubtree(key: RouteKeys.pending, child: PendingApprovalPage());
}

/// `/login`.
class LoginRoute extends StatelessWidget {
  const LoginRoute({super.key});

  @override
  Widget build(BuildContext context) =>
      const KeyedSubtree(key: RouteKeys.login, child: LoginPage());
}
