import 'package:bloc_test/bloc_test.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:get_it/get_it.dart';
import 'package:family_roots_mobile/domain/entities/entities.dart';
import 'package:family_roots_mobile/features/home/presentation/bloc/event_list_cubit.dart';
import 'package:family_roots_mobile/features/home/presentation/bloc/event_list_state.dart';
import 'package:family_roots_mobile/features/home/presentation/pages/home_page.dart';
import 'package:family_roots_mobile/shared/l10n/app_localizations.dart';

class MockEventListCubit extends MockCubit<EventListState> implements EventListCubit {}

void main() {
  late MockEventListCubit mockCubit;
  final getIt = GetIt.instance;

  setUpAll(() {
    TestWidgetsFlutterBinding.ensureInitialized();
  });

  setUp(() {
    mockCubit = MockEventListCubit();
    // Register the mock cubit so the page can use it
    getIt.registerFactory<EventListCubit>(() => mockCubit);
  });

  tearDown(() {
    getIt.reset();
  });

  Widget buildTestableWidget(Widget widget) {
    return MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      locale: const Locale('en'),
      home: widget,
    );
  }

  group('HomePage Widget Tests', () {
    testWidgets('shows loading spinner for events section when state is loading', (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 2.0;
      addTearDown(() => tester.view.resetPhysicalSize());
      addTearDown(() => tester.view.resetDevicePixelRatio());

      when(() => mockCubit.loadUpcomingEvents()).thenAnswer((_) async {});
      when(() => mockCubit.state).thenReturn(const EventListLoading());

      await tester.pumpWidget(buildTestableWidget(const HomePage()));

      expect(find.byType(CircularProgressIndicator), findsOneWidget);
    });

    testWidgets('shows events list when state is loaded', (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 2.0;
      addTearDown(() => tester.view.resetPhysicalSize());
      addTearDown(() => tester.view.resetDevicePixelRatio());

      when(() => mockCubit.loadUpcomingEvents()).thenAnswer((_) async {});
      final events = [
        const FamilyEvent(id: '1', title: 'Grandpa Memorial', date: '01/01/2026', description: 'At the ancestral house', isLunar: true),
        const FamilyEvent(id: '2', title: 'Family Reunion', date: '10/05/2026', description: 'Annual gathering', isLunar: false),
      ];

      when(() => mockCubit.state).thenReturn(EventListLoaded(events));

      await tester.pumpWidget(buildTestableWidget(const HomePage()));
      await tester.pumpAndSettle();

      expect(find.text('Grandpa Memorial'), findsOneWidget);
      expect(find.text('Family Reunion'), findsOneWidget);
      
      // Also verify static content
      expect(find.text('Upcoming Events'), findsOneWidget);
      expect(find.text('Recent Activity'), findsOneWidget);
    });

    testWidgets('shows no events message when state is loaded with empty list', (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 2.0;
      addTearDown(() => tester.view.resetPhysicalSize());
      addTearDown(() => tester.view.resetDevicePixelRatio());

      when(() => mockCubit.loadUpcomingEvents()).thenAnswer((_) async {});
      when(() => mockCubit.state).thenReturn(const EventListLoaded([]));

      await tester.pumpWidget(buildTestableWidget(const HomePage()));
      await tester.pumpAndSettle();

      expect(find.text('No upcoming events'), findsOneWidget);
    });
  });
}
