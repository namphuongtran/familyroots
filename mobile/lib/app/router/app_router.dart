import 'package:go_router/go_router.dart';
import '../../features/auth/presentation/pages/login_page.dart';
import '../../features/home/presentation/pages/home_page.dart';

/// Mobile app router configuration using GoRouter.
final GoRouter appRouter = GoRouter(
  initialLocation: '/login', // Start at login for now
  routes: [
    GoRoute(
      path: '/login',
      builder: (context, state) => const LoginPage(),
    ),
    GoRoute(
      path: '/',
      builder: (context, state) => const HomePage(),
    ),
  ],
);
