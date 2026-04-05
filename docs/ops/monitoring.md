# Monitoring

## Overview
FamilyRoots uses Sentry for error and performance monitoring and backend logs/audit trails for domain visibility.

## What to Document Here
- What gets sent to Sentry
- What should be logged locally versus centrally
- Key alerts or thresholds for backend, web, and mobile
- Audit log expectations for domain mutations

## Current Known Risks
- Alerting policy is not yet documented.
- In-process events can be lost before audit or downstream processing if the process crashes.
- Mobile and web observability should be aligned with backend error envelopes.
