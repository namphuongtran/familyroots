// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'clan_context.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning
/// GET /me/clans — approved memberships only, read through the offline cache.
/// [Stale.asOf] is non-null when the network failed and the cache answered.

@ProviderFor(myClans)
final myClansProvider = MyClansProvider._();

/// GET /me/clans — approved memberships only, read through the offline cache.
/// [Stale.asOf] is non-null when the network failed and the cache answered.

final class MyClansProvider
    extends
        $FunctionalProvider<
          AsyncValue<Stale<List<ClanMembership>>>,
          Stale<List<ClanMembership>>,
          FutureOr<Stale<List<ClanMembership>>>
        >
    with
        $FutureModifier<Stale<List<ClanMembership>>>,
        $FutureProvider<Stale<List<ClanMembership>>> {
  /// GET /me/clans — approved memberships only, read through the offline cache.
  /// [Stale.asOf] is non-null when the network failed and the cache answered.
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
  $FutureProviderElement<Stale<List<ClanMembership>>> $createElement(
    $ProviderPointer pointer,
  ) => $FutureProviderElement(pointer);

  @override
  FutureOr<Stale<List<ClanMembership>>> create(Ref ref) {
    return myClans(ref);
  }
}

String _$myClansHash() => r'03020d5e3bbf4dd856a4c43c6defa31a9d152f55';

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

String _$selectedClanHash() => r'0967a941c968882d82e179f5aaf79ce5cca7c580';

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

String _$clanResolutionHash() => r'214c49e625bc499e802b4027143cf271dc9e48dc';
