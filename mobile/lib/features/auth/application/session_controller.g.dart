// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'session_controller.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning
/// Signed-out is a state, not an error — hence UserProfile? rather than
/// throwing. keepAlive because the session outlives any one screen.

@ProviderFor(SessionController)
final sessionControllerProvider = SessionControllerProvider._();

/// Signed-out is a state, not an error — hence UserProfile? rather than
/// throwing. keepAlive because the session outlives any one screen.
final class SessionControllerProvider
    extends $AsyncNotifierProvider<SessionController, UserProfile?> {
  /// Signed-out is a state, not an error — hence UserProfile? rather than
  /// throwing. keepAlive because the session outlives any one screen.
  SessionControllerProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'sessionControllerProvider',
        isAutoDispose: false,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$sessionControllerHash();

  @$internal
  @override
  SessionController create() => SessionController();
}

String _$sessionControllerHash() => r'81795a47f1917356ae2997a886c30ad01c61df41';

/// Signed-out is a state, not an error — hence UserProfile? rather than
/// throwing. keepAlive because the session outlives any one screen.

abstract class _$SessionController extends $AsyncNotifier<UserProfile?> {
  FutureOr<UserProfile?> build();
  @$mustCallSuper
  @override
  void runBuild() {
    final ref = this.ref as $Ref<AsyncValue<UserProfile?>, UserProfile?>;
    final element =
        ref.element
            as $ClassProviderElement<
              AnyNotifier<AsyncValue<UserProfile?>, UserProfile?>,
              AsyncValue<UserProfile?>,
              Object?,
              Object?
            >;
    element.handleCreate(ref, build);
  }
}
