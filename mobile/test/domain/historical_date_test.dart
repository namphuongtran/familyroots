import 'package:flutter_test/flutter_test.dart';
import 'package:family_roots_mobile/domain/shared/historical_date.dart';

void main() {
  test('renders date when precision is exact', () {
    const d = HistoricalDate(
      date: '1750-03-02',
      precision: DatePrecision.exact,
      display: 'khoảng 1750',
      lunar: null,
    );
    expect(d.rendered, '1750-03-02');
  });

  test('renders display when precision is not exact', () {
    const d = HistoricalDate(
      date: '1750-01-01',
      precision: DatePrecision.circa,
      display: 'khoảng 1750',
      lunar: null,
    );
    expect(d.rendered, 'khoảng 1750');
  });

  test('falls back to date when display is null', () {
    const d = HistoricalDate(
      date: '1750-01-01',
      precision: DatePrecision.year,
      display: null,
      lunar: null,
    );
    expect(d.rendered, '1750-01-01');
  });

  test('renders null when nothing is known', () {
    const d = HistoricalDate(
      date: null,
      precision: DatePrecision.unknown,
      display: null,
      lunar: null,
    );
    expect(d.rendered, isNull);
  });

  test('parses the wire shape from docs/contracts', () {
    final d = HistoricalDate.fromWire(<String, Object?>{
      'date': '1932-05-01',
      'precision': 'exact',
      'display': null,
      'lunar': '15/08 Nhâm Tý',
    });
    expect(d.precision, DatePrecision.exact);
    expect(d.lunar, '15/08 Nhâm Tý');
    expect(d.rendered, '1932-05-01');
  });

  test('an unknown precision string degrades to unknown, never throws', () {
    final d = HistoricalDate.fromWire(<String, Object?>{
      'date': null,
      'precision': 'something_new_from_the_backend',
      'display': 'thời Lê',
      'lunar': null,
    });
    expect(d.precision, DatePrecision.unknown);
    expect(d.rendered, 'thời Lê');
  });

  test('freezed gives value equality and copyWith', () {
    const a = HistoricalDate(
      date: '1900-01-01',
      precision: DatePrecision.exact,
      display: null,
      lunar: null,
    );
    const b = HistoricalDate(
      date: '1900-01-01',
      precision: DatePrecision.exact,
      display: null,
      lunar: null,
    );
    expect(a, b);
    expect(a.hashCode, b.hashCode);
    expect(
      a.copyWith(precision: DatePrecision.year).precision,
      DatePrecision.year,
    );
  });

  test('sortKey puts unknown dates last', () {
    const known = HistoricalDate(
      date: '1900-01-01',
      precision: DatePrecision.exact,
      display: null,
      lunar: null,
    );
    const unknown = HistoricalDate(
      date: null,
      precision: DatePrecision.unknown,
      display: null,
      lunar: null,
    );
    final list = <HistoricalDate>[unknown, known]
      ..sort((a, b) => b.sortKey.compareTo(a.sortKey));
    expect(list.first, known);
  });
}
