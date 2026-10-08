# Huddle — quality assurance and launch notes

## Automated checks

- Backend tests cover authentication and sessions, private direct chats, real-time WebSocket message delivery, group membership/authorization, read receipts, search, message edit/delete/reactions, rate limiting, public response security headers, input validation, history pagination (including 60-message boundary and equal timestamps), and access controls.
- A network smoke test sends actual WebSocket traffic through a locally running Uvicorn server with two signed-in users.
- A Node-based UI event smoke test checks existence of DOM selectors, username/display-name validation, registration HTTP payload, state reset after sign-out, and HTML escaping.
- JavaScript syntax is checked with `node --check`.

Execute from the repository root:

```shell
python -m pip install -r requirements-dev.txt
python -m pytest -q
node --check app/web/app.js
node tests/frontend_smoke.cjs
python tests/socket_network_smoke.py
```

## Fixes from deployment audit

1. Explicit domain target port 8000 to address Railway HTTP 502 connection-refused errors.
2. Improved username/name registration instructions and separate server-side validation messages.
3. Friendly schema-validation details instead of a generic 'Request failed' when an API responds with a structured 422.
4. Correct pagination with no phantom older page when history contains exactly 60 messages and stable cursor ordering for duplicate timestamps.
5. Fixed foreground return handling by attaching `visibilitychange` to `document`, not `window`.
6. Reset sign-in mode and clear pending outgoing messages on logout.
7. Added automated regression coverage and GitHub Actions tests.

## Known limits

- This is a single-worker, SQLite-based small-audience pilot; it is not a high-scale, zero-downtime, production chat platform.
- Messages are encrypted in transit under HTTPS/WSS but are not end-to-end encrypted.
- Cloud free-tier credit/uptime/storage are constrained. Keep an off-site backup for any valuable long-term message data.
- Media upload, phone or email verification, account recovery, abuse reporting, moderator tools and notification delivery have not been implemented.
- Chromium automated navigation is blocked by the current execution environment policy (`ERR_BLOCKED_BY_ADMINISTRATOR`). Browser layout and user-facing workflows should be independently acceptance tested from actual phones and laptops. This is distinct from the backend and synthetic UI checks passing.
