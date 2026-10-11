<!-- ai-generated: 70% - AI drafted the initial requirements breakdown and API contract mapping; I reviewed and revised the final wording. -->
# svcdesk specification

This specification records the service contract for the internal Service Desk ticketing API. The scope covers health checks, ticket creation and retrieval, validation rules, priority assignment, state transitions, SLA calculation, and persistence in a containerized environment.

## Functional requirements

- The service must expose an HTTP API on port 8080 using JSON for request and response bodies.
- Health endpoint returns a stable status payload for monitoring.
- Ticket creation requires a title, agent-supplied reporter data, and valid impact/urgency values.
- Tickets are assigned a priority using the impact-urgency matrix, with VIP overrides handled as a deliberate design choice.
- State changes follow a strict workflow from `new` through `acknowledged`, `in_progress`, `resolved`, and `closed`.
- Reopen rules are limited to resolved tickets within the policy window; closed tickets remain immutable.
- SLA due instants are calculated in UTC and are based on the configured business-hour policy for the relevant priority.
- The service supports the test clock header in the configured test environment and keeps data persisted across container restarts.

## Non-functional requirements

- No host-path bind mounts are used in the Docker configuration.
- The application must run from a Docker Compose project with `svcdesk` built from the repository.
- The container must not require network access at runtime after build.
- The implementation must keep JSON response bodies consistent with the checker contract and include `error` objects for validation and not-found cases.

## Decisions captured for this build

- C1: `wallclock` for P1 with business-hours behavior for all other priorities.
- C2: `immutable` for closed tickets; reopen is only allowed from resolved tickets within the configured window.
- C3: `vip` for VIP reporters; low-priority VIP tickets are elevated to P2, while P1 and P2 remain unchanged.

This specification was prepared before the code implementation and is intended as the design baseline for the subsequent build and verification work.
