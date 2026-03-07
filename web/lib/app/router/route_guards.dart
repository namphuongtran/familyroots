import 'dart:async';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

// TODO: implement in Prompt 2
//
// Route guards for authentication and role-based access.
//
// - authGuard: redirect to /login if not authenticated
// - adminGuard: check user has admin role for /admin/* routes

/// Route guard that restricts access to platform super admin only.
///
/// Redirects non-super-admin users to /dashboard.
class SuperAdminGuard {
  /// Returns a redirect path if the user is not a super admin, or null to allow.
  FutureOr<String?> redirect(BuildContext context, GoRouterState state) {
    // TODO: implement in Prompt 2 — read user from AuthBloc state
    // final user = context.read<AuthBloc>().state.user;
    // if (user?.platformRole != 'super_admin') return '/dashboard';
    return null; // Allow access (placeholder until auth wiring)
  }
}
