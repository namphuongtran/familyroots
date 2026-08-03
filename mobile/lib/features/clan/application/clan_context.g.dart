// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'clan_context.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning
/// GET /me/clans — approved memberships only.

@ProviderFor(myClans)
final myClansProvider = MyClansProvider._();

/// GET /me/clans — approved memberships only.

final class MyClansProvider
    extends
        $FunctionalProvider<
          AsyncValue<List<ClanMembership>>,
          List<ClanMembership>,
          FutureOr<List<ClanMembership>>
        >
    with
        $FutureModifier<List<ClanMembership>>,
        $FutureProvider<List<ClanMembership>> {
  /// GET /me/clans — approved memberships only.
  MyClansProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'myClansProvider',
        isAutoDispose: false,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$myClansHash();

  @$internal
  @override
  $FutureProviderElement<List<ClanMembership>> $createElement(
    $ProviderPointer pointer,
  ) => $FutureProviderElement(pointer);

  @override
  FutureOr<List<ClanMembership>> create(Ref ref) {
    return myClans(ref);
  }
}

String _$myClansHash() => r'86f9089fbf00f62e8c07485c1f46f1049b77505b';

/// The active clan, persisted locally (not a secret) and sent as
/// X-Current-Clan-Id on every clan-scoped request thereafter.

@ProviderFor(SelectedClan)
final selectedClanProvider = SelectedClanProvider._();

/// The active clan, persisted locally (not a secret) and sent as
/// X-Current-Clan-Id on every clan-scoped request thereafter.
final class SelectedClanProvider
    extends $NotifierProvider<SelectedClan, ClanId?> {
  /// The active clan, persisted locally (not a secret) and sent as
  /// X-Current-Clan-Id on every clan-scoped request thereafter.
  SelectedClanProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'selectedClanProvider',
        isAutoDispose: false,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$selectedClanHash();

  @$internal
  @override
  SelectedClan create() => SelectedClan();

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(ClanId? value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<ClanId?>(value),
    );
  }
}

String _$selectedClanHash() => r'c4de48674bb0c457996d177f39ba3000cae4dbb2';

/// The active clan, persisted locally (not a secret) and sent as
/// X-Current-Clan-Id on every clan-scoped request thereafter.

abstract class _$SelectedClan extends $Notifier<ClanId?> {
  ClanId? build();
  @$mustCallSuper
  @override
  void runBuild() {
    final ref = this.ref as $Ref<ClanId?, ClanId?>;
    final element =
        ref.element
            as $ClassProviderElement<
              AnyNotifier<ClanId?, ClanId?>,
              ClanId?,
              Object?,
              Object?
            >;
    element.handleCreate(ref, build);
  }
}

/// PURE — read-only. See the note on [SelectedClan.resolve].

@ProviderFor(clanResolution)
final clanResolutionProvider = ClanResolutionProvider._();

/// PURE — read-only. See the note on [SelectedClan.resolve].

final class ClanResolutionProvider
    extends
        $FunctionalProvider<
          AsyncValue<ClanResolution>,
          ClanResolution,
          FutureOr<ClanResolution>
        >
    with $FutureModifier<ClanResolution>, $FutureProvider<ClanResolution> {
  /// PURE — read-only. See the note on [SelectedClan.resolve].
  ClanResolutionProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'clanResolutionProvider',
        isAutoDispose: false,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$clanResolutionHash();

  @$internal
  @override
  $FutureProviderElement<ClanResolution> $createElement(
    $ProviderPointer pointer,
  ) => $FutureProviderElement(pointer);

  @override
  FutureOr<ClanResolution> create(Ref ref) {
    return clanResolution(ref);
  }
}

String _$clanResolutionHash() => r'723059d775112bd279cb13bccf5ea199953b2fbc';
