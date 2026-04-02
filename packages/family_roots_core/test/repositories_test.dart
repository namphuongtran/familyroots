import 'package:family_roots_core/family_roots_core.dart';
import 'package:test/test.dart';

void main() {
  group('MockMemberRepository', () {
    late MockMemberRepository repo;

    setUp(() {
      repo = MockMemberRepository();
    });

    test('getMembers returns non-empty list', () async {
      final members = await repo.getMembers();

      expect(members, isNotEmpty);
      expect(members.length, 10);
    });

    test('getMemberById returns correct member', () async {
      final member = await repo.getMemberById('1');

      expect(member.name, 'Trần Văn Khảo');
      expect(member.generation, 1);
    });

    test('getMemberById throws for unknown id', () async {
      expect(
        () => repo.getMemberById('unknown'),
        throwsA(isA<StateError>()),
      );
    });

    test('searchMembers filters by name', () async {
      final results = await repo.searchMembers('Minh');

      expect(results.length, 1);
      expect(results.first.name, contains('Minh'));
    });

    test('searchMembers returns empty for no match', () async {
      final results = await repo.searchMembers('zzzzz');

      expect(results, isEmpty);
    });

    test('getRelationships returns relationships for member', () async {
      final rels = await repo.getRelationships('2');

      expect(rels, isNotEmpty);
      expect(rels.any((r) => r.relationType == 'father'), true);
    });
  });

  group('MockEventRepository', () {
    late MockEventRepository repo;

    setUp(() {
      repo = MockEventRepository();
    });

    test('getUpcomingEvents returns non-empty list', () async {
      final events = await repo.getUpcomingEvents();

      expect(events, isNotEmpty);
      expect(events.length, 3);
    });

    test('getEventById returns correct event', () async {
      final event = await repo.getEventById('1');

      expect(event.title, 'Giỗ Tổ Dòng Họ');
      expect(event.isLunar, true);
    });
  });
}
