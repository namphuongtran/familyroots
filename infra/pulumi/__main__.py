"""FamilyRoots infrastructure entrypoint.

Manages external services only. No per-clan resource provisioning —
clan isolation is handled by RLS at the database level.
"""

import pulumi

# TODO: implement in Prompt 2 — import and instantiate resource modules
# from resources.vercel_project import create_vercel_project
# from resources.firebase_project import configure_firebase
# from resources.github_settings import apply_branch_protection

config = pulumi.Config()
environment = config.require("environment")

# TODO: implement in Prompt 2
# vercel_project = create_vercel_project(environment)
# firebase = configure_firebase(environment)
# apply_branch_protection()

pulumi.export("environment", environment)
# TODO: implement in Prompt 2
# pulumi.export("web_url", vercel_project.url)
# pulumi.export("firebase_project_id", firebase.project_id)
