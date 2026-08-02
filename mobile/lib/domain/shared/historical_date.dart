import 'package:freezed_annotation/freezed_annotation.dart';

part 'historical_date.freezed.dart';

enum DatePrecision {
  exact,
  month,
  year,
  circa,
  unknown;

  /// Never throws: an unrecognised backend value degrades to [unknown] so a
  /// new precision on the server cannot crash a shipped client.
  static DatePrecision fromWire(Object? raw) {
    for (final p in DatePrecision.values) {
      if (p.name == raw) return p;
    }
    return DatePrecision.unknown;
  }
}

/// ADR-011. A model with behaviour, not a struct: it owns the render rule and
/// the sort key so no widget re-implements them.
@freezed
abstract class HistoricalDate with _$HistoricalDate {
  const factory HistoricalDate({
    required String? date,
    required DatePrecision precision,
    required String? display,
    required String? lunar,
  }) = _HistoricalDate;

  const HistoricalDate._();

  factory HistoricalDate.fromWire(Map<String, Object?> json) => HistoricalDate(
    date: json['date'] as String?,
    precision: DatePrecision.fromWire(json['precision']),
    display: json['display'] as String?,
    lunar: json['lunar'] as String?,
  );

  /// Render `date` when precision is exact, else `display`, falling back to
  /// `date`. `display` and `lunar` are stored user-entered text and are
  /// returned verbatim in every locale — never translate them.
  String? get rendered {
    if (precision == DatePrecision.exact && date != null) return date;
    return display ?? date;
  }

  /// ISO date when known, else empty so unknowns sort last.
  String get sortKey => date ?? '';
}
