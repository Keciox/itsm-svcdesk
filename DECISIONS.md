---
svcdesk_decisions:
  C1: wallclock
  C2: immutable
  C3: vip
---
<!-- ai-generated: 65% - I drafted the decision rationale and refined the wording to match the actual service behavior. -->

# Decisions

## C1 - SLA clock for P1

**Decision:** We keep the P1 policy on the wall-clock SLA schedule, while P2-P4 continue to use the business-hours clock. This keeps the desk responsive for the most urgent incidents and matches the requirement that a P1 raised after-hours still counts the real elapsed time, without allowing the business-hours clock to silently extend the response window.

**Rejected alternative:** We rejected the business-hours-only option for P1 because it would delay the acknowledgement and resolution deadlines for overnight or weekend P1 incidents, creating a second-class service level for the most critical tickets and making the Monday morning backlog worse than the contract allows.

**Reason:** The service owner needs predictable accountability for outages. A P1 ticket is treated as a true emergency, and the wall-clock SLA respects the real elapsed time without waiting for the next business opening. This prevents escalation drift and keeps monitoring and desk workflow aligned with the real incident timeline.

**Service owner:** The internal IT operations manager signs off on the P1 escalation policy because the service desk must protect the organisation's most critical business functions and preserve service accountability around the clock.

**Customer outcome:** Reporters of critical outages see the desk react against real time, and the organisation gets a clearer signal when a P1 case is genuinely late instead of being deferred until the next business morning.

## C2 - Closed tickets and reopening

**Decision:** We keep closed tickets immutable. Reopen is permitted only from `resolved` tickets within the seven-day window; a closed ticket cannot be reopened and instead requires a new ticket related to the prior issue.

**Rejected alternative:** We rejected the `reopen` alternative for closed tickets because it weakens the audit trail, creates ambiguity about whether the old issue is still being handled, and makes it easier to continue a closed case without creating a fresh incident record.

**Reason:** The service desk needs a trustworthy record of closure and confirmation. Reopening a resolved case is useful when the fix fails, but allowing a closed ticket to reopen confuses ownership and makes closed cases behave like active work without a new incident identity.

**Service owner:** The service desk manager is the accountable role because they must preserve clear ownership, auditability, and a clean incident record for later reporting.

**Customer outcome:** Customers and agents can still report a failed fix quickly, while the organisation keeps a clean history of closed issues and avoids reopening old cases without a legitimate replacement ticket.

## C3 - VIP reporters and the priority matrix

**Decision:** We apply the VIP override in the `vip` direction: a VIP reporter at P3 or P4 is elevated to P2, while P1 and P2 remain unchanged. This preserves the matrix for the normal case and makes executive problems visible without disturbing the highest-severity tickets.

**Rejected alternative:** We rejected the `matrix` alternative because it treats VIP status as informational only and leaves executive tickets hidden behind the ordinary impact and urgency model, which undermines the service desk's purpose for high-visibility issues.

**Reason:** VIP reporters are senior stakeholders whose issues need immediate attention, and the desk must surface them without distorting the rest of the queue. Elevating only the lower matrix outcomes keeps the triage model understandable while still protecting the most urgent cases.

**Service owner:** The service desk lead is responsible for triage prioritisation because they must balance executive visibility with fair handling of the wider queue.

**Customer outcome:** VIP reporters receive a visible escalation path, while the rest of the queue remains governed by the same matrix so that priority decisions stay predictable and defensible.
