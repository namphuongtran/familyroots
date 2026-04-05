# Deployment

## Overview
FamilyRoots currently uses a hybrid deployment model:
- Backend runtime via Docker and Render
- Web runtime via Next.js and Vercel
- Mobile delivery via Flutter build pipelines
- Infrastructure intent captured in Pulumi, but some resources remain scaffolded

## What to Document Here
- Dev to staging to production promotion path
- Which workflow owns each runtime deploy
- How database migrations are sequenced relative to app deploys
- Rollback expectations for backend and web releases

## Current Known Risks
- Pulumi resources are not fully implemented.
- Deployment authority may be split between manual actions and CI workflows.
- Database migrations need explicit sequencing to avoid contract drift.
