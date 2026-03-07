import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:sign_in_with_apple/sign_in_with_apple.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

/// Remote data source for authentication via Supabase Auth.
///
/// Supports email/password, Google SSO, and Apple SSO (iOS/macOS).
class AuthRemoteDataSource {
  AuthRemoteDataSource({SupabaseClient? supabase})
      : _supabase = supabase ?? Supabase.instance.client;

  final SupabaseClient _supabase;

  /// Email + Password sign in.
  Future<AuthResponse> signInWithEmail(String email, String password) async {
    return await _supabase.auth.signInWithPassword(
      email: email,
      password: password,
    );
  }

  /// Google SSO — uses ID token flow (mobile).
  Future<AuthResponse> signInWithGoogle() async {
    final GoogleSignIn googleSignIn = GoogleSignIn(
      clientId: const String.fromEnvironment('GOOGLE_CLIENT_ID'),
      serverClientId: const String.fromEnvironment('GOOGLE_SERVER_CLIENT_ID'),
    );
    final googleUser = await googleSignIn.signIn();
    if (googleUser == null) {
      throw Exception('Google sign-in was cancelled');
    }
    final googleAuth = await googleUser.authentication;

    return await _supabase.auth.signInWithIdToken(
      provider: OAuthProvider.google,
      idToken: googleAuth.idToken!,
      accessToken: googleAuth.accessToken,
    );
  }

  /// Apple SSO — native OIDC flow (iOS/macOS only).
  Future<AuthResponse> signInWithApple() async {
    final rawNonce = _supabase.auth.generateRawNonce();
    final hashedNonce = sha256.convert(utf8.encode(rawNonce)).toString();

    final credential = await SignInWithApple.getAppleIDCredential(
      scopes: [
        AppleIDAuthorizationScopes.email,
        AppleIDAuthorizationScopes.fullName,
      ],
      nonce: hashedNonce,
    );

    return await _supabase.auth.signInWithIdToken(
      provider: OAuthProvider.apple,
      idToken: credential.identityToken!,
      nonce: rawNonce,
    );
  }

  /// Sign out from all providers.
  Future<void> signOut() async {
    await _supabase.auth.signOut();
  }
}
