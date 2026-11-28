import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'session_controller.dart';

/// The resend button's state: null before a press, the backend's already
/// localised `message` after a 200, the error after a failure. Loading while a
/// request is in flight, which is what stops a second press.
class ResendVerificationController extends Notifier<AsyncValue<String?>> {
  @override
  AsyncValue<String?> build() => const AsyncValue<String?>.data(null);

  Future<void> resend(String email) async {
    if (state.isLoading) return;
    final repo = ref.read(authRepositoryProvider);
    state = const AsyncValue<String?>.loading();
    final result = await AsyncValue.guard<String?>(
      () => repo.resendVerification(email),
    );
    // Dropped if the screen went away while the request was in flight.
    if (ref.mounted) state = result;
  }
}

final resendVerificationProvider =
    NotifierProvider.autoDispose<
      ResendVerificationController,
      AsyncValue<String?>
    >(ResendVerificationController.new);
