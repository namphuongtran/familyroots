import 'package:get_it/get_it.dart';
import '../../domain/domain.dart';
import '../../features/home/presentation/bloc/event_list_cubit.dart';
import '../../features/members/presentation/bloc/member_detail_cubit.dart';
import '../../features/members/presentation/bloc/member_list_cubit.dart';

final getIt = GetIt.instance;

/// Configure all dependency injection bindings.
///
/// To switch from mock to real API, change the repository registrations:
/// ```dart
/// getIt.registerLazySingleton<MemberRepository>(() => ApiMemberRepository(dio));
/// ```
void configureDependencies() {
  // ── Repositories ──────────────────────────────────────────────────────
  // Swap Mock → Api implementations here when backend is ready.
  getIt.registerLazySingleton<MemberRepository>(MockMemberRepository.new);
  getIt.registerLazySingleton<EventRepository>(MockEventRepository.new);

  // ── Cubits ────────────────────────────────────────────────────────────
  // Factory = fresh instance per screen (disposed when page pops).
  getIt.registerFactory(() => MemberListCubit(getIt<MemberRepository>()));
  getIt.registerFactory(() => MemberDetailCubit(getIt<MemberRepository>()));
  getIt.registerFactory(() => EventListCubit(getIt<EventRepository>()));
}
