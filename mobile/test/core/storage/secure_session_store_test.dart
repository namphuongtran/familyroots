import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import 'package:family_roots_mobile/core/storage/prefs_store.dart';
import 'package:family_roots_mobile/core/storage/secure_session_store.dart';

class _MockSecureStorage extends Mock implements FlutterSecureStorage {}

void main() {
  late _MockSecureStorage storage;
  late SecureSessionStore store;

  setUp(() {
    storage = _MockSecureStorage();
    store = SecureSessionStore(storage: storage);
  });

  test('is a supabase LocalStorage', () {
    expect(store, isA<LocalStorage>());
  });

  test('initialize does not touch the keystore', () async {
    await store.initialize();
    verifyZeroInteractions(storage);
  });

  test('persistSession writes under the namespaced key', () async {
    when(
      () => storage.write(
        key: any(named: 'key'),
        value: any(named: 'value'),
      ),
    ).thenAnswer((_) async {});

    await store.persistSession('{"access_token":"a"}');

    verify(
      () => storage.write(
        key: SecureSessionStore.sessionKey,
        value: '{"access_token":"a"}',
      ),
    ).called(1);
  });

  test('accessToken, hasAccessToken and removePersistedSession', () async {
    when(
      () => storage.read(key: SecureSessionStore.sessionKey),
    ).thenAnswer((_) async => '{"access_token":"a"}');
    when(
      () => storage.containsKey(key: SecureSessionStore.sessionKey),
    ).thenAnswer((_) async => true);
    when(() => storage.delete(key: any(named: 'key'))).thenAnswer((_) async {});

    expect(await store.accessToken(), '{"access_token":"a"}');
    expect(await store.hasAccessToken(), isTrue);

    await store.removePersistedSession();
    verify(() => storage.delete(key: SecureSessionStore.sessionKey)).called(1);
  });

  test('the PKCE verifier store is secure too', () async {
    final pkce = SecurePkceStore(storage: storage);
    expect(pkce, isA<GotrueAsyncStorage>());

    when(
      () => storage.write(
        key: any(named: 'key'),
        value: any(named: 'value'),
      ),
    ).thenAnswer((_) async {});

    await pkce.setItem(key: 'verifier', value: 'v1');
    verify(() => storage.write(key: 'verifier', value: 'v1')).called(1);
  });

  test('PrefsStore round-trips clan id and locale', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final prefs = await PrefsStore.open();

    expect(prefs.readClanId(), isNull);
    await prefs.writeClanId('clan-1');
    expect(prefs.readClanId(), 'clan-1');
    await prefs.clearClanId();
    expect(prefs.readClanId(), isNull);

    expect(prefs.readLocale(), isNull);
    await prefs.writeLocale('vi');
    expect(prefs.readLocale(), 'vi');
  });
}
