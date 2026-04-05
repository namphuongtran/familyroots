import 'package:family_roots_mobile/domain/entities/entities.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('MemberModel', () {
    test('fromJson creates valid model', () {
      final json = {
        'id': '1',
        'name': 'Trần Văn Khảo',
        'generation': 1,
        'branch': '1',
        'birth_year': 1910,
        'death_year': 1985,
        'biography': 'Cụ tổ dòng họ.',
        'gender': 'male',
        'profile_image_url': null,
      };

      final member = MemberModel.fromJson(json);

      expect(member.id, '1');
      expect(member.name, 'Trần Văn Khảo');
      expect(member.generation, 1);
      expect(member.birthYear, 1910);
      expect(member.deathYear, 1985);
      expect(member.isAlive, false);
    });

    test('isAlive returns true when no death year', () {
      const member = MemberModel(
        id: '2',
        name: 'Trần Văn Minh',
        generation: 2,
        branch: '1',
        birthYear: 1950,
      );

      expect(member.isAlive, true);
    });

    test('toJson produces correct map', () {
      const member = MemberModel(
        id: '1',
        name: 'Trần Văn Khảo',
        generation: 1,
        branch: '1',
        birthYear: 1910,
        gender: 'male',
      );

      final json = member.toJson();

      expect(json['id'], '1');
      expect(json['name'], 'Trần Văn Khảo');
      expect(json['generation'], 1);
      expect(json['birth_year'], 1910);
      expect(json['death_year'], null);
    });

    test('equatable works for same properties', () {
      const member1 = MemberModel(id: '1', name: 'Test', generation: 1, branch: '1');
      const member2 = MemberModel(id: '1', name: 'Test', generation: 1, branch: '1');

      expect(member1, equals(member2));
    });
  });

  group('FamilyEvent', () {
    test('fromJson creates valid model', () {
      final json = {
        'id': '1',
        'title': 'Giỗ Tổ',
        'date': '10/03 ÂL',
        'description': 'Họp mặt.',
        'is_lunar': true,
      };

      final event = FamilyEvent.fromJson(json);

      expect(event.id, '1');
      expect(event.title, 'Giỗ Tổ');
      expect(event.isLunar, true);
    });

    test('toJson roundtrips correctly', () {
      const event = FamilyEvent(
        id: '1',
        title: 'Giỗ Tổ',
        date: '10/03 ÂL',
        description: 'Họp mặt.',
        isLunar: true,
      );

      final json = event.toJson();
      final roundTripped = FamilyEvent.fromJson(json);

      expect(roundTripped, equals(event));
    });
  });

  group('Relationship', () {
    test('fromJson creates valid model', () {
      final json = {
        'member_id': '2',
        'related_member_id': '1',
        'relation_type': 'father',
        'related_member_name': 'Trần Văn Khảo',
      };

      final rel = Relationship.fromJson(json);

      expect(rel.relationType, 'father');
      expect(rel.relatedMemberName, 'Trần Văn Khảo');
    });
  });
}
