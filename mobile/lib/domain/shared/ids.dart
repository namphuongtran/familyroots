/// Zero-cost wrappers so a ClanId cannot be passed where a PersonId is meant.
///
/// Extension types may NOT declare `toString`, `==`, `hashCode`, `runtimeType`
/// or `noSuchMethod` — those conflict with the Object members and are a
/// compile error ("This extension member conflicts with Object member
/// 'toString'"). Use `.value` for interpolation.
extension type const ClanId(String value) {}

extension type const PersonId(String value) {}

extension type const UserId(String value) {}
