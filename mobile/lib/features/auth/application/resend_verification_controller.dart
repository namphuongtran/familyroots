import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'session_controller.dart';

/// The state of "resend the verification email": idle (`data(null)`), in
/// flight, the backend's localised `message`, or the failure it ended in.
///
/// The presentation layer reaches the repository only through here.
class ResendVerificationController extends Notifier<AsyncValue<String?>> {
  @override
  AsyncValue<String?> build() => const AsyncValue<String?>.data(null);

  /// A press while a request is in flight is dropped, so two quick presses
  /// send one request. Never throws: a failure becomes the error state.
  Future<void> resend(String email) async {
    if (state.isLoading) return;
    state = const AsyncValue<String?>.loading();
    final repo = ref.read(authRepositoryProvider);
    state = await AsyncValue.guard<String?>(
      () => repo.resendVerification(email),
    );
  }
}

final resendVerificationProvider =
    NotifierProvider.autoDispose<
      ResendVerificationController,
      AsyncValue<String?>
    >(ResendVerificationController.new);
