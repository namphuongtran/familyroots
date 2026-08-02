# 5.3 Mobile — C4 Level 3 (Components)

`mobile/lib/` · Flutter · Clean Architecture + feature-first modules + BLoC.

## 5.3.1 Component diagram

```mermaid
graph TB
  main["main.dart<br/>configureDependencies then runApp"]:::comp

  subgraph shell[app/ - shell]
    mr[MaterialApp.router · app/app.dart]:::comp
    rtr[router/app_router.dart · go_router]:::comp
    grd[router/route_guards.dart]:::comp
    thm[theme · Arbor Heritage tokens]:::comp
  end

  subgraph feat[features/feature - auth, family_tree, members, documents, events, home, notifications]
    prsn[presentation<br/>BLoC, Cubit, pages, widgets]:::comp
    fdom[domain<br/>entities, usecases, repositories]:::core
    data[data<br/>datasources on Dio/Retrofit, models, repository impls]:::comp
  end

  subgraph topdom[lib/domain/ - cross-feature]
    ports[repositories · abstract ports]:::core
    ent[entities · shared]:::core
    mocks[mocks · MockMemberRepository, MockEventRepository]:::comp
  end

  subgraph core[core/]
    di[di/injection.dart · get_it and injectable]:::comp
    net[network/api_client.dart<br/>network/auth_interceptor.dart<br/>TODO scaffold]:::v2
    err[error/]:::comp
    cst[constants/]:::comp
  end

  subgraph shared[shared/]
    l10n[l10n · arb to AppLocalizations]:::comp
    sw[widgets and extensions]:::comp
  end

  sb[supabase_flutter<br/>google_sign_in, sign_in_with_apple]:::ext
  fcm[firebase_messaging · init TODO]:::v2
  hive[hive local cache · init TODO]:::v2
  sen[sentry_flutter · init TODO]:::v2
  api[backend /api/v1]:::host

  main --> di
  main --> mr
  mr --> rtr
  rtr --> grd
  rtr --> prsn
  prsn --> fdom
  fdom --> ports
  fdom --> ent
  di -.->|today binds| mocks
  di -.->|target binding| data
  data --> net
  net --> api
  net --> sb
  prsn --> l10n
  prsn --> thm
  prsn --> sw
  prsn --> err
  prsn --> cst
  main --> sb
  main --> fcm
  main --> hive
  main --> sen

  classDef host fill:#1168bd,stroke:#0b4884,color:#ffffff
  classDef comp fill:#85bbf0,stroke:#5d82a8,color:#000000
  classDef core fill:#e8a33d,stroke:#a9741f,color:#000000
  classDef ext fill:#999999,stroke:#6b6b6b,color:#ffffff
  classDef v2 fill:#7b4fa0,stroke:#54356f,color:#ffffff,stroke-dasharray:5 4
```

## 5.3.2 Two "domain" locations — read carefully

```mermaid
graph LR
  topdom[lib/domain/<br/>cross-feature ports and shared mocks]:::core
  featdom[lib/features/feature/domain/<br/>feature-local entities and usecases]:::core
  di[core/di/injection.dart]:::comp
  data[features/feature/data/<br/>Api repositories]:::comp
  ui[presentation<br/>depends on the abstract port only]:::comp

  di -->|today: Mock repository| topdom
  di -.->|one-line flip| data
  ui --> topdom
  ui --> featdom

  classDef comp fill:#85bbf0,stroke:#5d82a8,color:#000000
  classDef core fill:#e8a33d,stroke:#a9741f,color:#000000
```

Flipping a feature from mock to real API is a **one-line DI change** — no widget edits.

## 5.3.3 Building blocks

| Concern | Choice | Note |
|---|---|---|
| State | `flutter_bloc` — Cubit (simple) / BLoC (event-driven) | Cubits registered **factory** → fresh per screen |
| DI | `get_it` + `injectable` (codegen) | Manual bindings in `core/di/injection.dart` |
| Routing | `go_router` + guards | Root is `MaterialApp.router` |
| Network | `dio` + `retrofit` typed clients | Interceptor must attach the 3 contract headers + refresh on 401 |
| Local cache | `hive` / `hive_flutter` | Init is TODO |
| Auth | `supabase_flutter` | + Google / Apple sign-in |
| Push | `firebase_core` + `firebase_messaging` | Init is TODO |
| Errors | `sentry_flutter` | Init is TODO |
| i18n | `.arb` in `shared/l10n` → `AppLocalizations` | No hardcoded user-facing strings |
| Codegen | `build_runner` | Re-run after BLoC/Freezed/Retrofit/injectable changes |

## 5.3.4 UI-first workflow (mandated)

```mermaid
graph LR
  d1[1 Design in Stitch<br/>reviewed and approved]:::comp
  d2[2 Review spec<br/>tokens, type, colour]:::comp
  d3[3 Build UI against<br/>lib/domain/mocks/]:::comp
  d4[4 Flip DI to<br/>Api repository]:::good

  d1 --> d2
  d2 --> d3
  d3 --> d4

  classDef comp fill:#85bbf0,stroke:#5d82a8,color:#000000
  classDef good fill:#4f9a68,stroke:#357049,color:#ffffff
```

Arbor Heritage mandates: no 1px separator borders, Plus Jakarta Sans (headings) /
Manrope (body), radius `9999px` buttons and `2rem` nodes, ambient depth not drop
shadows, glass surfaces at 80% + 20px blur, never `#000000`.

## 5.3.5 Known scaffold state

`core/network/api_client.dart`, `core/network/auth_interceptor.dart`, Firebase/Sentry/Hive
init in `main.dart`, and most per-feature `data/` adapters are **intentional stubs**;
the DI container still resolves mocks. Gate: `flutter test && dart analyze .`.
