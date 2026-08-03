import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

const _defaultStorage = FlutterSecureStorage(
  // v10's default is already KeyStore-backed AES-GCM with RSA-OAEP key
  // wrapping. `encryptedSharedPreferences` is deprecated, ignored, and gone
  // in v11 — do not pass it.
  aOptions: AndroidOptions(),
  iOptions: IOSOptions(
    accessibility: KeychainAccessibility.first_unlock_this_device,
  ),
);

/// The Supabase session at rest: iOS Keychain / Android Keystore, never
/// SharedPreferences (frontend-integration-guide.md §2, ADR-034 D6).
class SecureSessionStore extends LocalStorage {
  SecureSessionStore({FlutterSecureStorage? storage})
    : _storage = storage ?? _defaultStorage;

  static const sessionKey = 'familyroots.supabase.session';

  final FlutterSecureStorage _storage;

  @override
  Future<void> initialize() async {}

  @override
  Future<bool> hasAccessToken() => _storage.containsKey(key: sessionKey);

  @override
  Future<String?> accessToken() => _storage.read(key: sessionKey);

  @override
  Future<void> removePersistedSession() => _storage.delete(key: sessionKey);

  @override
  Future<void> persistSession(String persistSessionString) =>
      _storage.write(key: sessionKey, value: persistSessionString);
}

/// The PKCE code verifier needs securing too — the default implementation
/// writes it to SharedPreferences in plaintext.
class SecurePkceStore extends GotrueAsyncStorage {
  SecurePkceStore({FlutterSecureStorage? storage})
    : _storage = storage ?? _defaultStorage;

  final FlutterSecureStorage _storage;

  @override
  Future<String?> getItem({required String key}) => _storage.read(key: key);

  @override
  Future<void> removeItem({required String key}) => _storage.delete(key: key);

  @override
  Future<void> setItem({required String key, required String value}) =>
      _storage.write(key: key, value: value);
}
