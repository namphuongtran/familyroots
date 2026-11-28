import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'session_controller.dart';

/// The state of one "resend verification" request on the verify screen:
/// `data(null)` before any press, `loading` in flight, `data(message)` with the
/// backend's already-localised message, or `error` with the [AppException].
class ResendVerification extends Notifier<AsyncValue<String?>> {
  @override
  AsyncValue<String?> build() => const AsyncValue<String?>.data(null);

  Future<void> resend(String email) async {
    // A second press while one is in flight must not send a second request.
    if (state.isLoading) return;
    state = const AsyncValue<String?>.loading();
    state = await AsyncValue.guard<String?>(
      () => ref.read(authRepositoryProvider).resendVerification(email),
    );
  }
}

final resendVerificationProvider =
    NotifierProvider.autoDispose<ResendVerification, AsyncValue<String?>>(
      ResendVerification.new,
    );
