// GENERATED CODE - DO NOT MODIFY BY HAND
// coverage:ignore-file
// ignore_for_file: type=lint
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'historical_date.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

// dart format off
T _$identity<T>(T value) => value;
/// @nodoc
mixin _$HistoricalDate {

 String? get date; DatePrecision get precision; String? get display; String? get lunar;
/// Create a copy of HistoricalDate
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$HistoricalDateCopyWith<HistoricalDate> get copyWith => _$HistoricalDateCopyWithImpl<HistoricalDate>(this as HistoricalDate, _$identity);



@override
bool operator ==(Object other) {
  return identical(this, other) || (other.runtimeType == runtimeType&&other is HistoricalDate&&(identical(other.date, date) || other.date == date)&&(identical(other.precision, precision) || other.precision == precision)&&(identical(other.display, display) || other.display == display)&&(identical(other.lunar, lunar) || other.lunar == lunar));
}


@override
int get hashCode => Object.hash(runtimeType,date,precision,display,lunar);

@override
String toString() {
  return 'HistoricalDate(date: $date, precision: $precision, display: $display, lunar: $lunar)';
}


}

/// @nodoc
abstract mixin class $HistoricalDateCopyWith<$Res>  {
  factory $HistoricalDateCopyWith(HistoricalDate value, $Res Function(HistoricalDate) _then) = _$HistoricalDateCopyWithImpl;
@useResult
$Res call({
 String? date, DatePrecision precision, String? display, String? lunar
});




}
/// @nodoc
class _$HistoricalDateCopyWithImpl<$Res>
    implements $HistoricalDateCopyWith<$Res> {
  _$HistoricalDateCopyWithImpl(this._self, this._then);

  final HistoricalDate _self;
  final $Res Function(HistoricalDate) _then;

/// Create a copy of HistoricalDate
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? date = freezed,Object? precision = null,Object? display = freezed,Object? lunar = freezed,}) {
  return _then(_self.copyWith(
date: freezed == date ? _self.date : date // ignore: cast_nullable_to_non_nullable
as String?,precision: null == precision ? _self.precision : precision // ignore: cast_nullable_to_non_nullable
as DatePrecision,display: freezed == display ? _self.display : display // ignore: cast_nullable_to_non_nullable
as String?,lunar: freezed == lunar ? _self.lunar : lunar // ignore: cast_nullable_to_non_nullable
as String?,
  ));
}

}


/// Adds pattern-matching-related methods to [HistoricalDate].
extension HistoricalDatePatterns on HistoricalDate {
/// A variant of `map` that fallback to returning `orElse`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _HistoricalDate value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _HistoricalDate() when $default != null:
return $default(_that);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// Callbacks receives the raw object, upcasted.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case final Subclass2 value:
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _HistoricalDate value)  $default,){
final _that = this;
switch (_that) {
case _HistoricalDate():
return $default(_that);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `map` that fallback to returning `null`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _HistoricalDate value)?  $default,){
final _that = this;
switch (_that) {
case _HistoricalDate() when $default != null:
return $default(_that);case _:
  return null;

}
}
/// A variant of `when` that fallback to an `orElse` callback.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( String? date,  DatePrecision precision,  String? display,  String? lunar)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _HistoricalDate() when $default != null:
return $default(_that.date,_that.precision,_that.display,_that.lunar);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// As opposed to `map`, this offers destructuring.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case Subclass2(:final field2):
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( String? date,  DatePrecision precision,  String? display,  String? lunar)  $default,) {final _that = this;
switch (_that) {
case _HistoricalDate():
return $default(_that.date,_that.precision,_that.display,_that.lunar);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `when` that fallback to returning `null`
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( String? date,  DatePrecision precision,  String? display,  String? lunar)?  $default,) {final _that = this;
switch (_that) {
case _HistoricalDate() when $default != null:
return $default(_that.date,_that.precision,_that.display,_that.lunar);case _:
  return null;

}
}

}

/// @nodoc


class _HistoricalDate extends HistoricalDate {
  const _HistoricalDate({required this.date, required this.precision, required this.display, required this.lunar}): super._();
  

@override final  String? date;
@override final  DatePrecision precision;
@override final  String? display;
@override final  String? lunar;

/// Create a copy of HistoricalDate
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$HistoricalDateCopyWith<_HistoricalDate> get copyWith => __$HistoricalDateCopyWithImpl<_HistoricalDate>(this, _$identity);



@override
bool operator ==(Object other) {
  return identical(this, other) || (other.runtimeType == runtimeType&&other is _HistoricalDate&&(identical(other.date, date) || other.date == date)&&(identical(other.precision, precision) || other.precision == precision)&&(identical(other.display, display) || other.display == display)&&(identical(other.lunar, lunar) || other.lunar == lunar));
}


@override
int get hashCode => Object.hash(runtimeType,date,precision,display,lunar);

@override
String toString() {
  return 'HistoricalDate(date: $date, precision: $precision, display: $display, lunar: $lunar)';
}


}

/// @nodoc
abstract mixin class _$HistoricalDateCopyWith<$Res> implements $HistoricalDateCopyWith<$Res> {
  factory _$HistoricalDateCopyWith(_HistoricalDate value, $Res Function(_HistoricalDate) _then) = __$HistoricalDateCopyWithImpl;
@override @useResult
$Res call({
 String? date, DatePrecision precision, String? display, String? lunar
});




}
/// @nodoc
class __$HistoricalDateCopyWithImpl<$Res>
    implements _$HistoricalDateCopyWith<$Res> {
  __$HistoricalDateCopyWithImpl(this._self, this._then);

  final _HistoricalDate _self;
  final $Res Function(_HistoricalDate) _then;

/// Create a copy of HistoricalDate
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? date = freezed,Object? precision = null,Object? display = freezed,Object? lunar = freezed,}) {
  return _then(_HistoricalDate(
date: freezed == date ? _self.date : date // ignore: cast_nullable_to_non_nullable
as String?,precision: null == precision ? _self.precision : precision // ignore: cast_nullable_to_non_nullable
as DatePrecision,display: freezed == display ? _self.display : display // ignore: cast_nullable_to_non_nullable
as String?,lunar: freezed == lunar ? _self.lunar : lunar // ignore: cast_nullable_to_non_nullable
as String?,
  ));
}


}

// dart format on
