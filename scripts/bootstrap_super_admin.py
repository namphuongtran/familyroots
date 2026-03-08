#!/usr/bin/env python3
"""Bootstrap the platform super admin account.

Run once during initial platform setup::

    uv run python scripts/bootstrap_super_admin.py

Requires environment variables:
    SUPABASE_URL              — Supabase project URL
    SUPABASE_SERVICE_ROLE_KEY — Supabase service role key (bypasses RLS)

Will fail if a super_admin already exists.
"""

import asyncio
import getpass
import os
import sys

from supabase import create_client


async def bootstrap() -> None:
    """Create the single platform super admin account."""
    supabase_url = os.environ.get("SUPABASE_URL")
    service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not service_role_key:
        print("❌ SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set.")
        sys.exit(1)

    supabase = create_client(supabase_url, service_role_key)

    # Check if super_admin already exists
    existing = (
        supabase.table("user_profiles")
        .select("id")
        .eq("platform_role", "super_admin")
        .execute()
    )
    if existing.data:
        print("❌ A super admin already exists. This script can only be run once.")
        sys.exit(1)

    email = input("Super admin email: ").strip()
    if not email:
        print("❌ Email is required.")
        sys.exit(1)

    password = getpass.getpass("Super admin password (min 12 chars): ")
    if len(password) < 12:
        print("❌ Password must be at least 12 characters.")
        sys.exit(1)

    # Create Supabase Auth user
    auth_response = supabase.auth.admin.create_user(
        {
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {"platform_role": "super_admin"},
        }
    )

    # Register in public.user_profiles
    supabase.table("user_profiles").insert(
        {
            "id": auth_response.user.id,
            "email": email,
            "display_name": "Super Admin",
            "platform_role": "super_admin",
        }
    ).execute()

    print(f"✅ Super admin created: {email}")
    print("⚠️  Store these credentials securely. This script cannot be run again.")


if __name__ == "__main__":
    asyncio.run(bootstrap())
