import 'package:supabase_flutter/supabase_flutter.dart';

/// Remote data source for authentication via Supabase Auth (web variant).
///
/// Web uses OAuth redirect flow instead of native ID token flow.
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

  /// Google SSO — OAuth redirect flow (web).
  Future<void> signInWithGoogleWeb() async {
    await _supabase.auth.signInWithOAuth(
      OAuthProvider.google,
      redirectTo: '${Uri.base.origin}/auth/callback',
    );
  }

  /// Apple SSO — OAuth redirect flow (web).
  Future<void> signInWithAppleWeb() async {
    await _supabase.auth.signInWithOAuth(
      OAuthProvider.apple,
      redirectTo: '${Uri.base.origin}/auth/callback',
    );
  }

  /// Sign out from all providers.
  Future<void> signOut() async {
    await _supabase.auth.signOut();
  }
}
