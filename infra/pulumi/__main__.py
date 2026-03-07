"""FamilyRoots infrastructure entrypoint."""

import pulumi

# TODO: implement in Prompt 2 — import and instantiate resource modules
# from resources.vercel_project import create_vercel_project
# from resources.supabase_project import create_supabase_project
# from resources.firebase_project import create_firebase_project
# from resources.github_settings import configure_github_settings

config = pulumi.Config()
environment = config.require("environment")

pulumi.export("environment", environment)
