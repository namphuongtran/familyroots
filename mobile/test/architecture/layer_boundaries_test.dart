import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;

/// Matches `import '...'` and `export '...'`, single or double quoted.
final _directive = RegExp(
  r"""^\s*(?:import|export)\s+(?:'([^']+)'|"([^"]+)")""",
  multiLine: true,
);

final _blockComment = RegExp(r'/\*.*?\*/', dotAll: true);
final _lineComment = RegExp(r'^\s*//.*$', multiLine: true);

List<String> parseDirectives(String source) {
  final stripped = source
      .replaceAll(_blockComment, '')
      .replaceAll(_lineComment, '');
  return _directive
      .allMatches(stripped)
      .map((m) => m.group(1) ?? m.group(2)!)
      .toList();
}

/// Resolves a relative import to a `lib/`-root-relative path so relative and
/// `package:` imports are checked by the same rules.
String? normalize(String directive, String fileLibRelPath) {
  if (directive.startsWith('dart:')) return null;
  if (directive.startsWith('package:family_roots_mobile/')) {
    return directive.substring('package:family_roots_mobile/'.length);
  }
  if (directive.startsWith('package:')) return directive;
  final dir = p.dirname(fileLibRelPath);
  return p.normalize(p.join(dir, directive));
}

const _domainForbiddenPackages = <String>[
  'package:flutter/',
  'package:dio/',
  'package:flutter_riverpod/',
  'package:riverpod/',
  'package:riverpod_annotation/',
  'package:supabase_flutter/',
  'package:supabase/',
  'package:json_annotation/',
];

/// Returns a human-readable violation, or null.
String? violationFor(String libRelPath, String target) {
  if (libRelPath.startsWith('domain/')) {
    for (final banned in _domainForbiddenPackages) {
      if (target.startsWith(banned)) {
        return '$libRelPath imports $target — domain must stay framework-agnostic';
      }
    }
    if (target.startsWith('core/') ||
        target.startsWith('features/') ||
        target.startsWith('app/') ||
        target.startsWith('shared/')) {
      return '$libRelPath imports $target — domain may import only domain/** and dart:*';
    }
  }

  if (libRelPath.startsWith('core/') && target.startsWith('features/')) {
    return '$libRelPath imports $target — core must not depend on features';
  }

  final presentation = RegExp(r'^features/([^/]+)/presentation/');
  if (presentation.hasMatch(libRelPath)) {
    if (RegExp(r'^features/[^/]+/data/').hasMatch(target)) {
      return '$libRelPath imports $target — presentation must not import data';
    }
  }

  final sliceOf = RegExp(r'^features/([^/]+)/');
  final from = sliceOf.firstMatch(libRelPath);
  final to = sliceOf.firstMatch(target);
  if (from != null && to != null && from.group(1) != to.group(1)) {
    final slice = to.group(1)!;
    if (target != 'features/$slice/$slice.dart') {
      return '$libRelPath imports $target — cross-slice imports must go '
          'through features/$slice/$slice.dart';
    }
  }

  if (libRelPath.startsWith('app/') &&
      RegExp(r'^features/[^/]+/data/').hasMatch(target)) {
    return '$libRelPath imports $target — app must not import data';
  }

  return null;
}

void main() {
  test('parseDirectives extracts imports and ignores comments', () {
    const src = '''
// import 'package:evil/evil.dart';
/* import 'package:also_evil/x.dart'; */
import 'dart:async';
import "package:dio/dio.dart";
import '../shared/page.dart';
export 'package:family_roots_mobile/domain/shared/page.dart';
''';
    expect(parseDirectives(src), <String>[
      'dart:async',
      'package:dio/dio.dart',
      '../shared/page.dart',
      'package:family_roots_mobile/domain/shared/page.dart',
    ]);
  });

  test('violationFor flags a domain file importing dio', () {
    expect(
      violationFor('domain/person/person.dart', 'package:dio/dio.dart'),
      isNotNull,
    );
    expect(
      violationFor(
        'domain/person/person.dart',
        'package:collection/collection.dart',
      ),
      isNull,
    );
  });

  test('violationFor flags relative domain->core escape', () {
    final target = normalize(
      '../../core/network/x.dart',
      'domain/person/person.dart',
    );
    expect(target, 'core/network/x.dart');
    expect(violationFor('domain/person/person.dart', target!), isNotNull);
  });

  test('violationFor flags cross-slice deep import', () {
    expect(
      violationFor(
        'features/clan/application/x.dart',
        'features/auth/data/auth_repository.dart',
      ),
      isNotNull,
    );
    expect(
      violationFor(
        'features/clan/application/x.dart',
        'features/auth/auth.dart',
      ),
      isNull,
    );
  });

  test('violationFor flags presentation importing data', () {
    expect(
      violationFor(
        'features/clan/presentation/clan_page.dart',
        'features/clan/data/clan_repository.dart',
      ),
      isNotNull,
    );
  });

  test('lib/ has no layer-boundary violations', () {
    final libDir = Directory('lib');
    expect(libDir.existsSync(), isTrue, reason: 'run from the package root');

    final violations = <String>[];
    for (final entity in libDir.listSync(recursive: true)) {
      if (entity is! File || !entity.path.endsWith('.dart')) continue;
      final libRel = p.relative(entity.path, from: 'lib');
      for (final d in parseDirectives(entity.readAsStringSync())) {
        final target = normalize(d, libRel);
        if (target == null) continue;
        final v = violationFor(libRel, target);
        if (v != null) violations.add(v);
      }
    }

    expect(violations, isEmpty, reason: violations.join('\n'));
  });
}
