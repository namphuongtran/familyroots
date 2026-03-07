"""Document ORM model — uses ClanScopedMixin for clan_id isolation."""

# TODO: implement in Prompt 2
#
# class Document(ClanScopedMixin, Base):
#     __tablename__ = "documents"
#     id, title, file_url, file_type, member_id, uploaded_by
#     clan_id inherited from ClanScopedMixin
#     created_at, updated_at inherited from TimestampMixin (via ClanScopedMixin)
