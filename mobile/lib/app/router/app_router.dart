import 'package:go_router/go_router.dart';
import '../../features/auth/presentation/pages/login_page.dart';
import '../../features/auth/presentation/pages/register_page.dart';
import '../../features/home/presentation/pages/home_page.dart';
import '../../features/members/presentation/pages/member_directory_page.dart';
import '../../features/members/presentation/pages/member_profile_page.dart';
import '../../features/family_tree/presentation/pages/family_tree_page.dart';

/// Mobile app router configuration using GoRouter.
final GoRouter appRouter = GoRouter(
  initialLocation: '/login', // Start at login for now
  routes: [
    GoRoute(
      path: '/login',
      builder: (context, state) => const LoginPage(),
    ),
    GoRoute(
      path: '/register',
      builder: (context, state) => const RegisterPage(),
    ),
    GoRoute(
      path: '/',
      builder: (context, state) => const HomePage(),
    ),
    GoRoute(
      path: '/members',
      builder: (context, state) => const MemberDirectoryPage(),
    ),
    GoRoute(
      path: '/member_profile/:id',
      builder: (context, state) {
        final id = state.pathParameters['id']!;
        return MemberProfilePage(memberId: id);
      },
    ),
    GoRoute(
      path: '/tree',
      builder: (context, state) => const FamilyTreePage(),
    ),
  ],
);
