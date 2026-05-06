# Security

AXTree API can observe and control real macOS applications through Accessibility permissions. Treat anything built with it as a privileged local automation tool.

## Safe Usage

- Grant Accessibility permission only to terminals, IDEs, or launchers you trust.
- Run agents in a dedicated macOS user account when possible.
- Avoid using this project on screens containing secrets, passwords, payment details, or private customer data unless you have strong safeguards.
- Keep a human approval step for purchases, authenticated account changes, file deletion, messages, email sending, or anything hard to reverse.
- Prefer allowlists for apps, actions, and workflows.
- Log actions during development so unexpected behavior can be audited.

## Reporting Vulnerabilities

This project is not yet tied to a public security mailbox. Until one exists, please use GitHub private vulnerability reporting if it is enabled. If it is not enabled, open a minimal public issue asking for a private contact path and avoid posting exploit details. Include:

- A short description of the vulnerability.
- Steps to reproduce.
- Affected macOS version and app, if relevant.
- Whether the issue allows unintended observation, action execution, privilege escalation, or data exposure.

Please do not publish working exploit details before maintainers have had a reasonable chance to respond.

## Scope

In scope:

- Bugs that let commands execute outside the intended local daemon protocol.
- Bugs that expose more UI state than requested by the frontmost-app model.
- Unsafe defaults in examples or documentation.

Out of scope:

- General macOS Accessibility permission risks that are inherent to user-approved Accessibility access.
- Behavior from third-party apps that expose incorrect or incomplete Accessibility metadata.
