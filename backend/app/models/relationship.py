"""Relationship ORM model — uses ClanScopedMixin for clan_id isolation."""

# TODO: implement in Prompt 2
#
# class Relationship(ClanScopedMixin, Base):
#     __tablename__ = "relationships"
#     id, from_member_id, to_member_id, type (parent, spouse, sibling)
#     clan_id inherited from ClanScopedMixin
#     created_at, updated_at inherited from TimestampMixin (via ClanScopedMixin)
