import 'package:bloc_test/bloc_test.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:get_it/get_it.dart';
import 'package:family_roots_mobile/domain/entities/entities.dart';
import 'package:family_roots_mobile/features/members/presentation/bloc/member_detail_cubit.dart';
import 'package:family_roots_mobile/features/members/presentation/bloc/member_detail_state.dart';
import 'package:family_roots_mobile/features/members/presentation/pages/member_profile_page.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:family_roots_mobile/shared/l10n/app_localizations.dart';

class MockMemberDetailCubit extends MockCubit<MemberDetailState> implements MemberDetailCubit {}

void main() {
  setUpAll(() {
    registerFallbackValue('');
  });

  late MockMemberDetailCubit mockCubit;
  final getIt = GetIt.instance;

  setUp(() {
    mockCubit = MockMemberDetailCubit();
    getIt.registerFactory<MemberDetailCubit>(() => mockCubit);
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

  group('MemberProfilePage Widget Tests', () {
    testWidgets('shows loading spinner when state is loading', (WidgetTester tester) async {
      when(() => mockCubit.loadMember(any())).thenAnswer((_) async {});
      when(() => mockCubit.state).thenReturn(const MemberDetailLoading());

      await tester.pumpWidget(buildTestableWidget(const MemberProfilePage(memberId: '1')));

      expect(find.byType(CircularProgressIndicator), findsOneWidget);
    });

    testWidgets('shows member details and relationships when state is loaded', (WidgetTester tester) async {
      when(() => mockCubit.loadMember(any())).thenAnswer((_) async {});
      const member = MemberModel(
        id: '1',
        name: 'Jane Doe',
        generation: 2,
        branch: '1',
        birthYear: 1980,
      );
      final relationships = [
        const Relationship(memberId: '1', relatedMemberId: '2', relatedMemberName: 'John Doe', relationType: 'father'),
      ];

      when(() => mockCubit.state).thenReturn(MemberDetailLoaded(member: member, relationships: relationships));

      await tester.pumpWidget(buildTestableWidget(const MemberProfilePage(memberId: '1')));
      await tester.pumpAndSettle();

      expect(find.text('Jane Doe'), findsWidgets); // Found in Appbar
      expect(find.text('1980'), findsOneWidget); // Found in stat card
      expect(find.text('Living'), findsOneWidget); // Found in stat card
      expect(find.text('John Doe'), findsOneWidget); // Found in relationships
      expect(find.text('Father'), findsOneWidget); // Localized relationType
    });
  });
}
