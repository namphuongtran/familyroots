// GENERATED CODE - DO NOT MODIFY BY HAND
// coverage:ignore-file
// ignore_for_file: type=lint
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'clan_membership.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

// dart format off
T _$identity<T>(T value) => value;
/// @nodoc
mixin _$ClanMembership {

 ClanId get clanId; String get clanName; String get clanSlug; ClanRole get role; DateTime? get joinedAt;
/// Create a copy of ClanMembership
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$ClanMembershipCopyWith<ClanMembership> get copyWith => _$ClanMembershipCopyWithImpl<ClanMembership>(this as ClanMembership, _$identity);



@override
bool operator ==(Object other) {
  return identical(this, other) || (other.runtimeType == runtimeType&&other is ClanMembership&&(identical(other.clanId, clanId) || other.clanId == clanId)&&(identical(other.clanName, clanName) || other.clanName == clanName)&&(identical(other.clanSlug, clanSlug) || other.clanSlug == clanSlug)&&(identical(other.role, role) || other.role == role)&&(identical(other.joinedAt, joinedAt) || other.joinedAt == joinedAt));
}


@override
int get hashCode => Object.hash(runtimeType,clanId,clanName,clanSlug,role,joinedAt);

@override
String toString() {
  return 'ClanMembership(clanId: $clanId, clanName: $clanName, clanSlug: $clanSlug, role: $role, joinedAt: $joinedAt)';
}


}

/// @nodoc
abstract mixin class $ClanMembershipCopyWith<$Res>  {
  factory $ClanMembershipCopyWith(ClanMembership value, $Res Function(ClanMembership) _then) = _$ClanMembershipCopyWithImpl;
@useResult
$Res call({
 ClanId clanId, String clanName, String clanSlug, ClanRole role, DateTime? joinedAt
});




}
/// @nodoc
class _$ClanMembershipCopyWithImpl<$Res>
    implements $ClanMembershipCopyWith<$Res> {
  _$ClanMembershipCopyWithImpl(this._self, this._then);

  final ClanMembership _self;
  final $Res Function(ClanMembership) _then;

/// Create a copy of ClanMembership
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? clanId = null,Object? clanName = null,Object? clanSlug = null,Object? role = null,Object? joinedAt = freezed,}) {
  return _then(_self.copyWith(
clanId: null == clanId ? _self.clanId : clanId // ignore: cast_nullable_to_non_nullable
as ClanId,clanName: null == clanName ? _self.clanName : clanName // ignore: cast_nullable_to_non_nullable
as String,clanSlug: null == clanSlug ? _self.clanSlug : clanSlug // ignore: cast_nullable_to_non_nullable
as String,role: null == role ? _self.role : role // ignore: cast_nullable_to_non_nullable
as ClanRole,joinedAt: freezed == joinedAt ? _self.joinedAt : joinedAt // ignore: cast_nullable_to_non_nullable
as DateTime?,
  ));
}

}


/// Adds pattern-matching-related methods to [ClanMembership].
extension ClanMembershipPatterns on ClanMembership {
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

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _ClanMembership value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _ClanMembership() when $default != null:
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

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _ClanMembership value)  $default,){
final _that = this;
switch (_that) {
case _ClanMembership():
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

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _ClanMembership value)?  $default,){
final _that = this;
switch (_that) {
case _ClanMembership() when $default != null:
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

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( ClanId clanId,  String clanName,  String clanSlug,  ClanRole role,  DateTime? joinedAt)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _ClanMembership() when $default != null:
return $default(_that.clanId,_that.clanName,_that.clanSlug,_that.role,_that.joinedAt);case _:
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

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( ClanId clanId,  String clanName,  String clanSlug,  ClanRole role,  DateTime? joinedAt)  $default,) {final _that = this;
switch (_that) {
case _ClanMembership():
return $default(_that.clanId,_that.clanName,_that.clanSlug,_that.role,_that.joinedAt);case _:
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

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( ClanId clanId,  String clanName,  String clanSlug,  ClanRole role,  DateTime? joinedAt)?  $default,) {final _that = this;
switch (_that) {
case _ClanMembership() when $default != null:
return $default(_that.clanId,_that.clanName,_that.clanSlug,_that.role,_that.joinedAt);case _:
  return null;

}
}

}

/// @nodoc


class _ClanMembership extends ClanMembership {
  const _ClanMembership({required this.clanId, required this.clanName, required this.clanSlug, required this.role, required this.joinedAt}): super._();
  

@override final  ClanId clanId;
@override final  String clanName;
@override final  String clanSlug;
@override final  ClanRole role;
@override final  DateTime? joinedAt;

/// Create a copy of ClanMembership
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$ClanMembershipCopyWith<_ClanMembership> get copyWith => __$ClanMembershipCopyWithImpl<_ClanMembership>(this, _$identity);



@override
bool operator ==(Object other) {
  return identical(this, other) || (other.runtimeType == runtimeType&&other is _ClanMembership&&(identical(other.clanId, clanId) || other.clanId == clanId)&&(identical(other.clanName, clanName) || other.clanName == clanName)&&(identical(other.clanSlug, clanSlug) || other.clanSlug == clanSlug)&&(identical(other.role, role) || other.role == role)&&(identical(other.joinedAt, joinedAt) || other.joinedAt == joinedAt));
}


@override
int get hashCode => Object.hash(runtimeType,clanId,clanName,clanSlug,role,joinedAt);

@override
String toString() {
  return 'ClanMembership(clanId: $clanId, clanName: $clanName, clanSlug: $clanSlug, role: $role, joinedAt: $joinedAt)';
}


}

/// @nodoc
abstract mixin class _$ClanMembershipCopyWith<$Res> implements $ClanMembershipCopyWith<$Res> {
  factory _$ClanMembershipCopyWith(_ClanMembership value, $Res Function(_ClanMembership) _then) = __$ClanMembershipCopyWithImpl;
@override @useResult
$Res call({
 ClanId clanId, String clanName, String clanSlug, ClanRole role, DateTime? joinedAt
});




}
/// @nodoc
class __$ClanMembershipCopyWithImpl<$Res>
    implements _$ClanMembershipCopyWith<$Res> {
  __$ClanMembershipCopyWithImpl(this._self, this._then);

  final _ClanMembership _self;
  final $Res Function(_ClanMembership) _then;

/// Create a copy of ClanMembership
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? clanId = null,Object? clanName = null,Object? clanSlug = null,Object? role = null,Object? joinedAt = freezed,}) {
  return _then(_ClanMembership(
clanId: null == clanId ? _self.clanId : clanId // ignore: cast_nullable_to_non_nullable
as ClanId,clanName: null == clanName ? _self.clanName : clanName // ignore: cast_nullable_to_non_nullable
as String,clanSlug: null == clanSlug ? _self.clanSlug : clanSlug // ignore: cast_nullable_to_non_nullable
as String,role: null == role ? _self.role : role // ignore: cast_nullable_to_non_nullable
as ClanRole,joinedAt: freezed == joinedAt ? _self.joinedAt : joinedAt // ignore: cast_nullable_to_non_nullable
as DateTime?,
  ));
}


}

// dart format on
