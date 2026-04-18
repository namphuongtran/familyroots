import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:family_roots_mobile/shared/widgets/event_card.dart';

void main() {
  group('EventCard Widget Tests', () {
    testWidgets('renders correctly with given data', (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: EventCard(
              title: 'Family Reunion',
              date: '10/05/2026',
              description: 'Annual gathering',
              isLunar: false,
              lunarLabel: 'Lunar',
              solarLabel: 'Solar',
            ),
          ),
        ),
      );

      expect(find.text('Family Reunion'), findsOneWidget);
      expect(find.text('10/05/2026'), findsOneWidget);
      expect(find.text('Annual gathering'), findsOneWidget);
      expect(find.text('Solar'), findsOneWidget);
    });

    testWidgets('shows lunar label when isLunar is true', (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: EventCard(
              title: 'Tet Festival',
              date: '01/01',
              description: 'Lunar New Year',
              isLunar: true,
              lunarLabel: 'Lunar',
              solarLabel: 'Solar',
            ),
          ),
        ),
      );

      expect(find.text('Lunar'), findsOneWidget);
    });
  });
}
