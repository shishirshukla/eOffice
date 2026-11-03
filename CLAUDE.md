# CLAUDE.md – eOffice project context and decision history

This file keeps the project context and the history of design discussions so work can continue from any machine or session.

## Project

eOffice is a paperless approval and sanction workflow for a bank (Branch → Regional Office → Head Office). It does not integrate with CBS, LOS or HRMS.

- Original requirement note: [Agents.md](Agents.md)
- Functional Requirements Specification (source of truth): [docs/eOffice-FRS.md](docs/eOffice-FRS.md)
- Online copy of the FRS (not synced with the repo): https://claude.ai/artifact/Pvvjs93u3r6sWcr9s5QGkK

Required stack: Python backend, HTML + JS + Bootstrap frontend, PostgreSQL. Users sign with HYP2003 DSC USB tokens.

## Conversation history (3 Nov 2026)

1. **Requirement shared.** Agents.md describes the stages (Initiator → Recommender → Approver → Control), the CO/RO/BO hierarchy and its levels, committees, the DoFP-based auto path, custom paths, incremental PDF signing, storage, and email of the final PDF.
2. **First design proposed.** Django + PostgreSQL; steps assigned to positions, not named people; an auto path built from the DoFP table; signing split between the server (pyHanko prepares the PDF) and a local agent on the user's PC that signs with the HYP2003 token.
3. **Control.** Control is the step after sanction and is the final signature.
4. **Committee quorum.** Each committee has its own quorum rule.
5. **Administrative approvals.** Their paths are configured by the administrator.
6. **Comments.** Users can add a comment before signing. The comment is locked on signing and printed in the visible signature stamp, so it is covered by the signature.
7. **Branch proposals.** Every branch proposal must pass through its parent RO.
8. **BM within powers.** When the amount is within the Branch Manager's powers, the BM sanctions and the RO does Control.
9. **Self-sanction.** A BM can sanction their own proposal. Control is not set by the auto path; it is assigned by hand.
10. **RO queue.** Control after a BM sanction goes to an RO queue.
11. **Queue manager.** RO and CO each have Control queues. A designated Desk Officer (Queue Manager) assigns each item to the right Control officer.
12. **Department queues.** Every department at RO and HO has its own queue. Control for RO-level sanctions goes to HO.
13. **Grade rule.** Control is generally one grade above the sanctioning authority, including committees. If an RO Senior Manager sanctions, Control stays at the RO.
14. **Grade exception.** An RO Senior Manager is normally one grade above a BM. If no Senior Manager is above the BM (for example, a senior-grade BM), the RO Committee does Control. Grades are stored per officer (actual grade), not only per role.
15. **Final sanctions.** At CO, Control is done by AGMs/GMs, who are always above the RM. When the Chairman or an HO committee sanctions, that is the last stage and there is no Control.
16. **GM sanctions.** The Chairman does Control for GM sanctions. The Chairman can both sanction and control.
17. **FRS written.** The FRS was written for business, IT and developers. The tech stack was simplified for the bank's IT team (see below).
18. **Repo set up.** The FRS was saved to docs/ and pushed to GitHub (shishirshukla/eOffice) so work can continue from another location.

## Final Control matrix

| Sanctioned by | Control queue | Control officer |
| --- | --- | --- |
| Branch Manager (incl. self-sanction) | Parent RO department queue | RO Senior Manager above the BM's grade, or RM; RO Committee if no Senior Manager is above the BM |
| RO Senior Manager | RO department queue | Regional Manager |
| Regional Manager / RO Committee | HO department queue | AGM / GM |
| HO Head of Department | HO department queue | AGM / GM |
| HO AGM | HO department queue | GM |
| HO GM | HO department queue | Chairman |
| Chairman / HO Committee 1 / HO Committee 2 | – | None (sanction is final) |

## Agreed simplified tech stack

- A single Django app with server-rendered templates, Bootstrap 5 and plain JS (no separate REST layer)
- PostgreSQL
- A scheduled job (cron or Windows Task Scheduler) for email and reminders, instead of Celery/Redis
- File storage in a server folder or on a NAS, instead of MinIO
- ReportLab to generate PDFs and pyHanko to sign them incrementally
- A ready-made vendor DSC signer utility for HYP2003, instead of a custom agent
- Django admin plus maker-checker for master data
- Django login, with LDAP added later if needed

## Open points

- Confirm the grade ladder, including the HoD's grade relative to the RM
- Confirm the DoFP table (heads and amount limits)
- Confirm the quorum rule for each committee
- Confirm the reminder and escalation days for each stage
- Confirm the retention period for signed documents
- Confirm whether a time-stamping service and LDAP are available
- Decide: buy a vendor DSC signer utility, or have the IT team build one

## Working notes

- docs/eOffice-FRS.md is the main copy. Update it whenever a business rule changes, and add the decision to the history above.
