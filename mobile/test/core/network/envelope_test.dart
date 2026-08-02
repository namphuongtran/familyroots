import 'package:flutter_test/flutter_test.dart';
import 'package:family_roots_mobile/core/network/api_exception.dart';
import 'package:family_roots_mobile/core/network/envelope.dart';

void main() {
  group('unwrapData', () {
    test('pulls the data member', () {
      final v = unwrapData<String>(<String, Object?>{
        'data': 'hello',
      }, (j) => j! as String);
      expect(v, 'hello');
    });

    test('passes a map through to the parser', () {
      final v = unwrapData<int>(<String, Object?>{
        'data': <String, Object?>{'expires_in': 3600},
      }, (j) => (j! as Map<String, Object?>)['expires_in']! as int);
      expect(v, 3600);
    });

    test('throws MalformedResponseException when data is absent', () {
      expect(
        () => unwrapData<String>(<String, Object?>{
          'oops': 1,
        }, (j) => j! as String),
        throwsA(isA<MalformedResponseException>()),
      );
    });

    test('throws MalformedResponseException on a non-map body', () {
      expect(
        () => unwrapData<String>('not json', (j) => j! as String),
        throwsA(isA<MalformedResponseException>()),
      );
    });

    test('a null data member is legal and reaches the parser', () {
      final v = unwrapData<String?>(<String, Object?>{
        'data': null,
      }, (j) => j as String?);
      expect(v, isNull);
    });
  });

  group('unwrapPage', () {
    test('reads cursor meta', () {
      final p = unwrapPage<int>(<String, Object?>{
        'data': <Object?>[1, 2],
        'meta': <String, Object?>{
          'cursor': 'b3BhcXVl',
          'has_more': true,
          'limit': 2,
        },
      }, (j) => j! as int);
      expect(p.items, <int>[1, 2]);
      expect(p.cursor, 'b3BhcXVl');
      expect(p.hasMore, isTrue);
      expect(p.limit, 2);
    });

    test('tolerates a meta-less array — GET /me/clans is a plain array', () {
      final p = unwrapPage<int>(<String, Object?>{
        'data': <Object?>[7, 8, 9],
      }, (j) => j! as int);
      expect(p.items, <int>[7, 8, 9]);
      expect(p.cursor, isNull);
      expect(p.hasMore, isFalse);
      expect(p.limit, 3);
    });

    test('an empty list is a valid page, not an error', () {
      final p = unwrapPage<int>(<String, Object?>{
        'data': <Object?>[],
      }, (j) => j! as int);
      expect(p.items, isEmpty);
      expect(p.hasMore, isFalse);
    });

    test('throws when data is not a list', () {
      expect(
        () => unwrapPage<int>(<String, Object?>{
          'data': <String, Object?>{},
        }, (j) => j! as int),
        throwsA(isA<MalformedResponseException>()),
      );
    });

    test('the cursor is carried verbatim and never inspected', () {
      const weird = 'not-base64!!:{}';
      final p = unwrapPage<int>(<String, Object?>{
        'data': <Object?>[1],
        'meta': <String, Object?>{
          'cursor': weird,
          'has_more': true,
          'limit': 1,
        },
      }, (j) => j! as int);
      expect(p.cursor, weird);
    });
  });
}
