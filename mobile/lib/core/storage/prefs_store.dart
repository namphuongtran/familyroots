import 'package:shared_preferences/shared_preferences.dart';

/// Non-secret client state: the selected clan and the user's chosen locale.
/// The app owns the locale and never reads the backend's `preferred_locale`,
/// which always returns "vi" (documented backend gap, spec R3).
class PrefsStore {
  PrefsStore(this._prefs);

  static const _clanKey = 'familyroots.selected_clan_id';
  static const _localeKey = 'familyroots.locale';

  final SharedPreferences _prefs;

  static Future<PrefsStore> open() async =>
      PrefsStore(await SharedPreferences.getInstance());

  String? readClanId() => _prefs.getString(_clanKey);
  Future<void> writeClanId(String clanId) => _prefs.setString(_clanKey, clanId);
  Future<void> clearClanId() => _prefs.remove(_clanKey);

  String? readLocale() => _prefs.getString(_localeKey);
  Future<void> writeLocale(String locale) =>
      _prefs.setString(_localeKey, locale);
}
