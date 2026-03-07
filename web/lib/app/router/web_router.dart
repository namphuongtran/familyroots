import 'package:go_router/go_router.dart';

// TODO: implement in Prompt 2 — import page widgets

// Platform admin pages (super admin only)
// import 'package:family_roots_web/features/admin/platform/pages/platform_dashboard_page.dart';
// import 'package:family_roots_web/features/admin/platform/pages/clan_management_page.dart';
// import 'package:family_roots_web/features/admin/platform/pages/platform_metrics_page.dart';
// import 'package:family_roots_web/features/admin/platform/pages/platform_audit_page.dart';

/// Web app router configuration using GoRouter.
/// Includes both public routes and admin panel routes.
final GoRouter webRouter = GoRouter(
  initialLocation: '/',
  routes: [
    // TODO: implement in Prompt 2 — define routes

    // Public routes
    // GoRoute(path: '/', builder: (context, state) => const HomePage()),
    // GoRoute(path: '/login', builder: (context, state) => const LoginPage()),
    // GoRoute(path: '/tree', builder: (context, state) => const TreePage()),
    // GoRoute(path: '/members', builder: (context, state) => const MembersPage()),
    // GoRoute(path: '/members/:id', builder: (context, state) => const MemberDetailPage()),
    // GoRoute(path: '/documents', builder: (context, state) => const DocumentsPage()),
    // GoRoute(path: '/events', builder: (context, state) => const EventsPage()),

    // Admin routes (role-gated)
    // ShellRoute(
    //   builder: (context, state, child) => const AdminShell(child: child),
    //   routes: [
    //     GoRoute(path: '/admin', builder: (context, state) => const DashboardPage()),
    //     GoRoute(path: '/admin/users', builder: (context, state) => const UserApprovalPage()),
    //     GoRoute(path: '/admin/settings', builder: (context, state) => const ClanSettingsPage()),
    //     GoRoute(path: '/admin/audit', builder: (context, state) => const AuditLogPage()),
    //   ],
    // ),

    // Platform super admin routes (protected by SuperAdminGuard)
    // GoRoute(path: '/platform', builder: (context, state) => const PlatformDashboardPage()),
    // GoRoute(path: '/platform/clans', builder: (context, state) => const ClanManagementPage()),
    // GoRoute(path: '/platform/metrics', builder: (context, state) => const PlatformMetricsPage()),
    // GoRoute(path: '/platform/audit', builder: (context, state) => const PlatformAuditPage()),
  ],
  // redirect: routeGuard,
);
