// GENERATED CODE - DO NOT MODIFY BY HAND
// coverage:ignore-file
// ignore_for_file: type=lint
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'user_profile.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

// dart format off
T _$identity<T>(T value) => value;
/// @nodoc
mixin _$UserProfile {

 UserId get id; String get email; String? get fullName; ClanId? get clanId; String? get clanName;// Non-null only when the membership is approved.
 ClanRole? get role; bool get isApproved; bool get hasPendingMembership; PersonId? get personId;
/// Create a copy of UserProfile
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$UserProfileCopyWith<UserProfile> get copyWith => _$UserProfileCopyWithImpl<UserProfile>(this as UserProfile, _$identity);



@override
bool operator ==(Object other) {
  return identical(this, other) || (other.runtimeType == runtimeType&&other is UserProfile&&(identical(other.id, id) || other.id == id)&&(identical(other.email, email) || other.email == email)&&(identical(other.fullName, fullName) || other.fullName == fullName)&&(identical(other.clanId, clanId) || other.clanId == clanId)&&(identical(other.clanName, clanName) || other.clanName == clanName)&&(identical(other.role, role) || other.role == role)&&(identical(other.isApproved, isApproved) || other.isApproved == isApproved)&&(identical(other.hasPendingMembership, hasPendingMembership) || other.hasPendingMembership == hasPendingMembership)&&(identical(other.personId, personId) || other.personId == personId));
}


@override
int get hashCode => Object.hash(runtimeType,id,email,fullName,clanId,clanName,role,isApproved,hasPendingMembership,personId);

@override
String toString() {
  return 'UserProfile(id: $id, email: $email, fullName: $fullName, clanId: $clanId, clanName: $clanName, role: $role, isApproved: $isApproved, hasPendingMembership: $hasPendingMembership, personId: $personId)';
}


}

/// @nodoc
abstract mixin class $UserProfileCopyWith<$Res>  {
  factory $UserProfileCopyWith(UserProfile value, $Res Function(UserProfile) _then) = _$UserProfileCopyWithImpl;
@useResult
$Res call({
 UserId id, String email, String? fullName, ClanId? clanId, String? clanName, ClanRole? role, bool isApproved, bool hasPendingMembership, PersonId? personId
});




}
/// @nodoc
class _$UserProfileCopyWithImpl<$Res>
    implements $UserProfileCopyWith<$Res> {
  _$UserProfileCopyWithImpl(this._self, this._then);

  final UserProfile _self;
  final $Res Function(UserProfile) _then;

/// Create a copy of UserProfile
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? id = null,Object? email = null,Object? fullName = freezed,Object? clanId = freezed,Object? clanName = freezed,Object? role = freezed,Object? isApproved = null,Object? hasPendingMembership = null,Object? personId = freezed,}) {
  return _then(_self.copyWith(
id: null == id ? _self.id : id // ignore: cast_nullable_to_non_nullable
as UserId,email: null == email ? _self.email : email // ignore: cast_nullable_to_non_nullable
as String,fullName: freezed == fullName ? _self.fullName : fullName // ignore: cast_nullable_to_non_nullable
as String?,clanId: freezed == clanId ? _self.clanId : clanId // ignore: cast_nullable_to_non_nullable
as ClanId?,clanName: freezed == clanName ? _self.clanName : clanName // ignore: cast_nullable_to_non_nullable
as String?,role: freezed == role ? _self.role : role // ignore: cast_nullable_to_non_nullable
as ClanRole?,isApproved: null == isApproved ? _self.isApproved : isApproved // ignore: cast_nullable_to_non_nullable
as bool,hasPendingMembership: null == hasPendingMembership ? _self.hasPendingMembership : hasPendingMembership // ignore: cast_nullable_to_non_nullable
as bool,personId: freezed == personId ? _self.personId : personId // ignore: cast_nullable_to_non_nullable
as PersonId?,
  ));
}

}


/// Adds pattern-matching-related methods to [UserProfile].
extension UserProfilePatterns on UserProfile {
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

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _UserProfile value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _UserProfile() when $default != null:
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

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _UserProfile value)  $default,){
final _that = this;
switch (_that) {
case _UserProfile():
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

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _UserProfile value)?  $default,){
final _that = this;
switch (_that) {
case _UserProfile() when $default != null:
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

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( UserId id,  String email,  String? fullName,  ClanId? clanId,  String? clanName,  ClanRole? role,  bool isApproved,  bool hasPendingMembership,  PersonId? personId)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _UserProfile() when $default != null:
return $default(_that.id,_that.email,_that.fullName,_that.clanId,_that.clanName,_that.role,_that.isApproved,_that.hasPendingMembership,_that.personId);case _:
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

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( UserId id,  String email,  String? fullName,  ClanId? clanId,  String? clanName,  ClanRole? role,  bool isApproved,  bool hasPendingMembership,  PersonId? personId)  $default,) {final _that = this;
switch (_that) {
case _UserProfile():
return $default(_that.id,_that.email,_that.fullName,_that.clanId,_that.clanName,_that.role,_that.isApproved,_that.hasPendingMembership,_that.personId);case _:
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

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( UserId id,  String email,  String? fullName,  ClanId? clanId,  String? clanName,  ClanRole? role,  bool isApproved,  bool hasPendingMembership,  PersonId? personId)?  $default,) {final _that = this;
switch (_that) {
case _UserProfile() when $default != null:
return $default(_that.id,_that.email,_that.fullName,_that.clanId,_that.clanName,_that.role,_that.isApproved,_that.hasPendingMembership,_that.personId);case _:
  return null;

}
}

}

/// @nodoc


class _UserProfile extends UserProfile {
  const _UserProfile({required this.id, required this.email, required this.fullName, required this.clanId, required this.clanName, required this.role, required this.isApproved, required this.hasPendingMembership, required this.personId}): super._();
  

@override final  UserId id;
@override final  String email;
@override final  String? fullName;
@override final  ClanId? clanId;
@override final  String? clanName;
// Non-null only when the membership is approved.
@override final  ClanRole? role;
@override final  bool isApproved;
@override final  bool hasPendingMembership;
@override final  PersonId? personId;

/// Create a copy of UserProfile
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$UserProfileCopyWith<_UserProfile> get copyWith => __$UserProfileCopyWithImpl<_UserProfile>(this, _$identity);



@override
bool operator ==(Object other) {
  return identical(this, other) || (other.runtimeType == runtimeType&&other is _UserProfile&&(identical(other.id, id) || other.id == id)&&(identical(other.email, email) || other.email == email)&&(identical(other.fullName, fullName) || other.fullName == fullName)&&(identical(other.clanId, clanId) || other.clanId == clanId)&&(identical(other.clanName, clanName) || other.clanName == clanName)&&(identical(other.role, role) || other.role == role)&&(identical(other.isApproved, isApproved) || other.isApproved == isApproved)&&(identical(other.hasPendingMembership, hasPendingMembership) || other.hasPendingMembership == hasPendingMembership)&&(identical(other.personId, personId) || other.personId == personId));
}


@override
int get hashCode => Object.hash(runtimeType,id,email,fullName,clanId,clanName,role,isApproved,hasPendingMembership,personId);

@override
String toString() {
  return 'UserProfile(id: $id, email: $email, fullName: $fullName, clanId: $clanId, clanName: $clanName, role: $role, isApproved: $isApproved, hasPendingMembership: $hasPendingMembership, personId: $personId)';
}


}

/// @nodoc
abstract mixin class _$UserProfileCopyWith<$Res> implements $UserProfileCopyWith<$Res> {
  factory _$UserProfileCopyWith(_UserProfile value, $Res Function(_UserProfile) _then) = __$UserProfileCopyWithImpl;
@override @useResult
$Res call({
 UserId id, String email, String? fullName, ClanId? clanId, String? clanName, ClanRole? role, bool isApproved, bool hasPendingMembership, PersonId? personId
});




}
/// @nodoc
class __$UserProfileCopyWithImpl<$Res>
    implements _$UserProfileCopyWith<$Res> {
  __$UserProfileCopyWithImpl(this._self, this._then);

  final _UserProfile _self;
  final $Res Function(_UserProfile) _then;

/// Create a copy of UserProfile
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? id = null,Object? email = null,Object? fullName = freezed,Object? clanId = freezed,Object? clanName = freezed,Object? role = freezed,Object? isApproved = null,Object? hasPendingMembership = null,Object? personId = freezed,}) {
  return _then(_UserProfile(
id: null == id ? _self.id : id // ignore: cast_nullable_to_non_nullable
as UserId,email: null == email ? _self.email : email // ignore: cast_nullable_to_non_nullable
as String,fullName: freezed == fullName ? _self.fullName : fullName // ignore: cast_nullable_to_non_nullable
as String?,clanId: freezed == clanId ? _self.clanId : clanId // ignore: cast_nullable_to_non_nullable
as ClanId?,clanName: freezed == clanName ? _self.clanName : clanName // ignore: cast_nullable_to_non_nullable
as String?,role: freezed == role ? _self.role : role // ignore: cast_nullable_to_non_nullable
as ClanRole?,isApproved: null == isApproved ? _self.isApproved : isApproved // ignore: cast_nullable_to_non_nullable
as bool,hasPendingMembership: null == hasPendingMembership ? _self.hasPendingMembership : hasPendingMembership // ignore: cast_nullable_to_non_nullable
as bool,personId: freezed == personId ? _self.personId : personId // ignore: cast_nullable_to_non_nullable
as PersonId?,
  ));
}


}

// dart format on
