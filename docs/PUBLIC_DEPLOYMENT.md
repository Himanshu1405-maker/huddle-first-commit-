# Huddle — free-tier public deployment

## Non-negotiable data warning
The SQLite chat database is not end-to-end encrypted. Hosts/administrators with database access can read message content. Don't use this as a private messenger for sensitive information. Railway's trial and free storage are **not a permanent archival guarantee**; back up the DB using Railway's approved export tools before credits expire. All free quotas and current billing limits should be checked in the account dashboard before use.

## Installation and deployment
1. Create a **private** GitHub repository and upload the application sources. Include Dockerfile, requirements.txt, railway.json, and app/. Do not upload `.env` or any `*.db` files. Hackathon rules say keep GitHub private until submission.
2. Connect that repository to Railway, in the private `Huddle — First Commit` project. Only one service/replica/worker is supported with the SQLite chat architecture and in-memory WebSocket fanout.
3. Add a Railway persistent Volume with mount path `/data`. Without it, the SQLite DB is ephemeral and accounts and chats can be lost upon redeployment.
4. Configure service variables: `HUDDLE_DB=/data/huddle.db`, `SECURE_COOKIES=1`, `SEED_DEMO=0`, `PYTHONUNBUFFERED=1`. No secrets are needed for the basic app.
5. Use the included Dockerfile to build. Use `/health` for health checks. Generate a free `*.up.railway.app` domain to enable HTTPS/WSS.
6. Register **two new accounts in separate browsers**. Test cross-device real-time messaging, refresh persistence, group invites, reactions, logout, and rejection of outsider access.
7. Review **Usage** and **Billing** in Railway regularly. Remain on Free/Trial; never upgrade without explicit consent.

## Scale and lifecycle boundaries
- The single-service SQLite design is suited to small pilot / hackathon traffic. No promise of unlimited concurrent users, uptime, or multi-replica scaling. For genuine large-audience production use, adopt managed PostgreSQL, shared WebSocket pub/sub, anti-abuse/report/block tooling, observability, backups and a formal privacy/security review.
- Free trial includes a time-limited credit; after trial the free monthly usage credit is small. The service can go offline when credits are depleted; persistent data is subject to provider retention rules. Export backups before the free trial expires.
- This is a public preview; the service is not end-to-end encrypted and does not support email verification or password reset. Do not present it as a production-grade replacement for established secure messengers.
