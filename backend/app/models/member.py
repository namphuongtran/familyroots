"""Member ORM model — uses ClanScopedMixin for clan_id isolation."""

# TODO: implement in Prompt 2
#
# class Member(ClanScopedMixin, Base):
#     __tablename__ = "members"
#     id, full_name, birth_date, death_date, gender, generation, bio, avatar_url
#     clan_id inherited from ClanScopedMixin
#     created_at, updated_at inherited from TimestampMixin (via ClanScopedMixin)
