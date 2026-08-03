/// Public surface of the clan slice.
library;

export 'application/clan_context.dart'
    show
        ClanResolution,
        SelectedClan,
        clanRepositoryProvider,
        clanResolutionProvider,
        myClansProvider,
        prefsStoreProvider,
        selectedClanProvider;
export 'data/clan_repository.dart' show ClanRepository;

// presentation/ exports are added in Task 17, once those files exist.
