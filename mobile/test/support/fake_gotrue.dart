import 'dart:convert';

import 'package:gotrue/gotrue.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

/// A GoTrue refusal: the HTTP status and GoTrue's own error `code`.
///
/// The codes are the ones `@supabase/auth-js` 2.111.0 lists in
/// `lib/error-codes.d.ts` (the web's copy, read 2026-10-10). gotrue-dart
/// 2.26.0's own `ErrorCode` enum has `email_not_confirmed` and lacks the other
/// two, so the client passes a code through whether or not it knows it.
class GoTrueRefusal {
  const GoTrueRefusal(this.status, this.code, this.message);

  /// A wrong password or an unknown address.
  static const invalidCredentials = GoTrueRefusal(
    400,
    'invalid_credentials',
    'Invalid login credentials',
  );

  /// A password sign-in for an address nobody has confirmed yet.
  static const emailNotConfirmed = GoTrueRefusal(
    400,
    'email_not_confirmed',
    'Email not confirmed',
  );

  final int status;
  final String code;
  final String message;
}

/// Supabase Auth behind a **real** [GoTrueClient], with only its HTTP
/// transport faked. A test that reads a bearer token off a backend request is
/// therefore reading the token this fake issued and the real client stored,
/// never one a test wrote into a provider by hand.
///
/// Wire shapes follow GoTrue at API version 2024-01-01, the version gotrue
/// 2.26.0 asks for: an error body is `{"code": <error code>, "message": …}`,
/// and it carries the `x-supabase-api-version` header. Without that header
/// the client reads the code from the older `error_code` field instead, and a
/// refusal would arrive with no code at all.
class FakeGoTrue {
  FakeGoTrue({this.refusal, this.offline = false, this.logoutStatus = 204});

  static const url = 'https://supabase.test/auth/v1';

  /// What a successful password sign-in issues.
  static const accessToken = 'gotrue-issued-access-token';
  static const refreshToken = 'gotrue-issued-refresh-token';

  /// When set, every password sign-in is refused with it.
  final GoTrueRefusal? refusal;

  /// When true, no request gets an answer, as with no network. Settable, so a
  /// test can sign in first and lose the network after.
  bool offline;

  /// What `POST /logout`, the server-side revoke, answers.
  final int logoutStatus;

  /// Every request the client sent, in order.
  final List<http.Request> received = <http.Request>[];

  late final GoTrueClient client = GoTrueClient(
    url: url,
    httpClient: MockClient(_answer),
    // No ticker. A periodic refresh timer outlives a widget test, which then
    // fails on "A Timer is still pending".
    autoRefreshToken: false,
  );

  /// The grant types the client asked `/token` for, in order.
  List<String?> get tokenGrants => received
      .where((r) => r.url.path.endsWith('/token'))
      .map((r) => r.url.queryParameters['grant_type'])
      .toList();

  Future<http.Response> _answer(http.Request request) async {
    received.add(request);
    if (offline) throw http.ClientException('Failed host lookup', request.url);

    final path = request.url.path;
    if (path.endsWith('/token')) {
      return switch (request.url.queryParameters['grant_type']) {
        'password' => _passwordGrant(request),
        // Nothing here hands out a second token. A test that reaches a
        // refresh has already lost the token it should have sent.
        _ => _refuse(
          const GoTrueRefusal(
            400,
            'refresh_token_not_found',
            'Invalid Refresh Token: Refresh Token Not Found',
          ),
        ),
      };
    }
    if (path.endsWith('/logout')) {
      return logoutStatus == 204
          ? http.Response('', 204)
          : http.Response('upstream unavailable', logoutStatus);
    }
    return http.Response('', 404);
  }

  http.Response _passwordGrant(http.Request request) {
    final refused = refusal;
    if (refused != null) return _refuse(refused);
    final body = jsonDecode(request.body) as Map<String, Object?>;
    return http.Response(
      jsonEncode(<String, Object?>{
        'access_token': accessToken,
        'token_type': 'bearer',
        'expires_in': 3600,
        'refresh_token': refreshToken,
        'user': <String, Object?>{
          'id': 'u1',
          'aud': 'authenticated',
          'role': 'authenticated',
          'email': body['email'],
          'email_confirmed_at': '2026-10-01T00:00:00Z',
          'app_metadata': <String, Object?>{'provider': 'email'},
          'user_metadata': <String, Object?>{},
          'created_at': '2026-10-01T00:00:00Z',
        },
      }),
      200,
      headers: _headers,
    );
  }

  http.Response _refuse(GoTrueRefusal r) => http.Response(
    jsonEncode(<String, Object?>{'code': r.code, 'message': r.message}),
    r.status,
    headers: _headers,
  );

  static const _headers = <String, String>{
    'content-type': 'application/json',
    'x-supabase-api-version': '2024-01-01',
  };
}
