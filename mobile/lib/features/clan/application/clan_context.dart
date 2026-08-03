import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../core/storage/prefs_store.dart';
import '../../../domain/clan/clan_membership.dart';
import '../../../domain/shared/ids.dart';
import '../data/clan_repository.dart';

part 'clan_context.g.dart';

final clanRepositoryProvider = Provider<ClanRepository>(
  (ref) => throw UnimplementedError('override in ProviderScope'),
);

final prefsStoreProvider = Provider<PrefsStore>(
  (ref) => throw UnimplementedError('override in ProviderScope'),
);

/// GET /me/clans — approved memberships only.
@Riverpod(keepAlive: true)
Future<List<ClanMembership>> myClans(Ref ref) =>
    ref.watch(clanRepositoryProvider).myClans();

enum ClanResolution { none, resolved, needsPicker }

/// The active clan, persisted locally (not a secret) and sent as
/// X-Current-Clan-Id on every clan-scoped request thereafter.
@Riverpod(keepAlive: true)
class SelectedClan extends _$SelectedClan {
  @override
  ClanId? build() {
    final stored = ref.read(prefsStoreProvider).readClanId();
    return stored == null ? null : ClanId(stored);
  }

  Future<void> select(ClanId id) async {
    await ref.read(prefsStoreProvider).writeClanId(id.value);
    state = id;
  }

  /// On 400 invalid_clan_id_format: clear the stored clan and re-resolve.
  Future<void> clear() async {
    await ref.read(prefsStoreProvider).clearClanId();
    state = null;
  }

  /// Called once by the app shell after sign-in. A single-clan user is
  /// selected silently; the header is still sent so behaviour stays
  /// deterministic if they later join a second clan.
  ///
  /// This is a METHOD, not a provider body: writing to this notifier from
  /// inside a provider that also watches it deadlocks the container
  /// ("disposed during loading state, yet no value could be emitted").
  Future<ClanResolution> resolve() async {
    final clans = await ref.read(myClansProvider.future);
    if (clans.isEmpty) return ClanResolution.none;

    final selected = state;
    if (selected != null && clans.any((c) => c.clanId == selected)) {
      return ClanResolution.resolved;
    }
    if (selected != null) {
      // The stored clan is no longer an approved membership.
      await clear();
    }
    if (clans.length == 1) {
      await select(clans.single.clanId);
      return ClanResolution.resolved;
    }
    return ClanResolution.needsPicker;
  }
}

/// PURE — read-only. See the note on [SelectedClan.resolve].
@Riverpod(keepAlive: true)
Future<ClanResolution> clanResolution(Ref ref) async {
  final clans = await ref.watch(myClansProvider.future);
  if (clans.isEmpty) return ClanResolution.none;

  final selected = ref.watch(selectedClanProvider);
  if (selected != null && clans.any((c) => c.clanId == selected)) {
    return ClanResolution.resolved;
  }
  if (clans.length == 1) return ClanResolution.resolved;
  return ClanResolution.needsPicker;
}
