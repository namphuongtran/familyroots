import 'package:bloc_test/bloc_test.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:get_it/get_it.dart';
import 'package:family_roots_mobile/domain/entities/entities.dart';
import 'package:family_roots_mobile/features/members/presentation/bloc/member_list_cubit.dart';
import 'package:family_roots_mobile/features/members/presentation/bloc/member_list_state.dart';
import 'package:family_roots_mobile/features/members/presentation/pages/member_directory_page.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:family_roots_mobile/shared/l10n/app_localizations.dart';

class MockMemberListCubit extends MockCubit<MemberListState> implements MemberListCubit {}

void main() {
  setUpAll(() {
    registerFallbackValue('');
  });

  late MockMemberListCubit mockCubit;
  final getIt = GetIt.instance;

  setUp(() {
    mockCubit = MockMemberListCubit();
    // Register the mock cubit so the page can use it
    getIt.registerFactory<MemberListCubit>(() => mockCubit);
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

  group('MemberDirectoryPage Widget Tests', () {
    testWidgets('shows loading spinner when state is loading', (WidgetTester tester) async {
      when(() => mockCubit.loadMembers()).thenAnswer((_) async {});
      when(() => mockCubit.state).thenReturn(const MemberListLoading());
      
      await tester.pumpWidget(buildTestableWidget(const MemberDirectoryPage()));
      
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
    });

    testWidgets('shows members list when state is loaded', (WidgetTester tester) async {
      when(() => mockCubit.loadMembers()).thenAnswer((_) async {});
      final members = [
        const MemberModel(id: '1', name: 'John Doe', generation: 1, branch: '1'),
        const MemberModel(id: '2', name: 'Jane Doe', generation: 2, branch: '1'),
      ];
      
      when(() => mockCubit.state).thenReturn(MemberListLoaded(members: members, allMembers: members));
      
      await tester.pumpWidget(buildTestableWidget(const MemberDirectoryPage()));
      await tester.pumpAndSettle();
      
      expect(find.text('John Doe'), findsOneWidget);
      expect(find.text('Jane Doe'), findsOneWidget);
    });

    testWidgets('triggers search method when typing in search field', (WidgetTester tester) async {
      when(() => mockCubit.loadMembers()).thenAnswer((_) async {});
      when(() => mockCubit.state).thenReturn(const MemberListLoaded(members: [], allMembers: []));
      when(() => mockCubit.searchMembers(any())).thenReturn(null);
      
      await tester.pumpWidget(buildTestableWidget(const MemberDirectoryPage()));
      await tester.pumpAndSettle();
      
      final searchField = find.byType(TextField);
      expect(searchField, findsOneWidget);
      
      await tester.enterText(searchField, 'John');
      verify(() => mockCubit.searchMembers('John')).called(1);
    });
  });
}
