# FamilyRoots

A Vietnamese genealogy platform where several clans keep their family trees side by side, each
clan's records kept apart from every other clan's.

## Language

### Ownership

**Clan-owned**:
A record that belongs to exactly one clan, which decides whether the record lives and who may see
it.
_Avoid_: tenant data, clan-scoped (when ownership is meant)

**User-owned**:
A record that belongs to an account rather than to a clan. The account can exist before it joins
any clan, and while it belongs to several.
_Avoid_: global, shared

### Belonging

**Session**:
A signed-in identity, from sign-in to sign-out. It says who the user is, never which clan they act in.
_Avoid_: auth, login (when the identity is meant)

**Membership**:
A user's place in one clan, carrying a clan role. A user may hold several, in several clans.
_Avoid_: clan role (when the place is meant), user-clan

**Pending membership**:
A membership no admin of its clan has approved yet. It grants nothing in that clan.
_Avoid_: pending user, unapproved account

**Active clan**:
The one clan, among a user's approved memberships, that the user is acting in right now.
_Avoid_: current clan, selected clan

**Suspended clan**:
A clan the platform has switched off. Its memberships still exist, but none of them can be acted in.
_Avoid_: inactive clan, disabled clan
