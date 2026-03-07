"""JWT decode, password hashing, and auth utilities."""

# TODO: implement in Prompt 2
#
# This module will provide:
# - verify_jwt_token(token: str) -> dict — decode and validate Supabase JWT
# - hash_password(password: str) -> str — bcrypt hash
# - verify_password(plain: str, hashed: str) -> bool — bcrypt verify
# - get_current_user dependency for FastAPI route protection
