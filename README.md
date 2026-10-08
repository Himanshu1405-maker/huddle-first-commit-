# ✳ Huddle — Real-time campus conversations

**First Commit · Kamand Prompt · IIT Mandi**

A complete, responsive real-time web chat application built around the challenge's mandatory requirements: **registration + login + persistent sessions, private 1:1 chat, WebSocket delivery, and reliable multi-user messaging**. It goes further with campus **Circles** (groups), member invitations, reactions, typing indicators, presence, read receipts, search, edit/delete, profiles, and accessible mobile UI.

**Built for a 24-hour hackathon: zero front-end compilation, zero paid APIs, and a single-command local server.**

## 1. Quick start

You need **Python 3.11+**. Open a terminal in this directory.

```bash
python -m venv .venv
# macOS / Linux:
source .venv/bin/activate
# Windows PowerShell:
# .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000** in your browser. Create two separate accounts using two private/incognito browser windows and start a conversation. Messages reach both browsers **live** over WebSockets and remain available after refreshing.

### Instant demo accounts

Want a pre-populated campus group? Launch in **local demo mode**:

**macOS / Linux:**

```bash
SEED_DEMO=1 uvicorn app.main:app --reload
```

**Windows PowerShell:**

```powershell
$env:SEED_DEMO="1"
uvicorn app.main:app --reload
```

Demo users (all share the password `DemoPass123!`):

| Username | Display name |
|---|---|
| `aarya` | Aarya Sharma |
| `kabir` | Kabir Mehta |
| `meera` | Meera Rao |

**Important:** These demonstration credentials are intentionally public; `SEED_DEMO=0` is the default and must be used for a public deployment. The demo seed is idempotent and creates a shared group with initial messages.

## 2. Features and scope

| Feature | How it's implemented |
|---|---|
| Register, login, logout | Argon2id password hashes, secure random session tokens, hashed database session records, HttpOnly/SameSite cookies, server-side logout invalidation |
| One-to-one chats | Idempotent room creation for unordered user pair, server-side membership checks |
| Real-time messaging | Native WebSocket (`/ws`) room fan-out, message acknowledgment + per-sender idempotency key, HTTP fallback, reconnection |
| Message persistence | SQLite (WAL, foreign keys, indexed rooms/messages/users) |
| Group Circles | Multiple participants, admin role, create groups, invite members |
| Status | Online/offline presence for connected users, typing notifications |
| Read receipts | Each room member has a last-read timestamp, per-message seen-by calculation |
| Reactions | Toggle supported emojis per account per message |
| Edit / Delete | Author-restricted endpoints; deleted message tombstones and removed reactions |
| History and search | Latest 60 messages with cursor pagination; server-filtered search only across rooms the user belongs to |
| Identity | User profiles, display name and bio |
| Experience | Desktop and mobile layouts, subtle animation, no third-party UI framework, keyboard-friendly composer |

### Feature honesty

Files, images, audio calls, end-to-end encrypted messages, and LLM agents are **not** implemented. The hackathon PDF lists these as optional examples, not mandatory requirements. This implementation prioritizes the reliable communication foundation plus several useful optional features. The connection is encrypted in transit **when deployed under HTTPS/WSS**, but message content is stored in regular SQLite and **is not end-to-end encrypted**.

## 3. Architecture

```text
                          ┌──────────────────────────────────┐
                          │ Browser (HTML, CSS, JavaScript)  │
                          │  responsive UI + local state     │
                          └───────────────┬──────────────────┘
                                          │
                   REST over HTTPS        │       WSS (WebSocket)
            auth / rooms / search / read   │       messages / typing / presence
                                          ▼
                          ┌──────────────────────────────────┐
                          │ FastAPI application (Python)     │
                          │                                  │
                          │ • identity + session checks      │
                          │ • room authorization             │
                          │ • WebSocket connection hub       │
                          │ • message persistence + events   │
                          └───────────────┬──────────────────┘
                                          │ SQL / transactions
                                          ▼
                          ┌──────────────────────────────────┐
                          │ SQLite persistent DB (WAL)       │
                          │ users, sessions, conversations,  │
                          │ members, messages, reactions     │
                          └──────────────────────────────────┘
```

**Message lifecycle:** a sender submits `message:send` with a unique nonce → the server validates its signed-in session and verifies membership → stores the message **before** broadcasting → sends `message:new` to every connected participant → acknowledges the sender with `message:ack`. Reloading a chat reads durable message history. If the socket drops, the browser reconnects and synchronizes rooms/history; sending via HTTP remains available as a fallback.

**Scaling note:** The in-memory WebSocket hub is meant for **one server worker/process**. Do not use `--workers > 1` without replacing the hub with a shared pub/sub layer (such as Redis) and using a scalable database (such as PostgreSQL). SQLite requires a persistent filesystem and is not suitable for ephemeral cloud storage if long-term history matters.

## 4. Project layout

```text
app/
  main.py             FastAPI routes, security, SQLite, WebSocket hub
  web/
    index.html        Authentication + chat + modal UI
    style.css         Responsive design
    app.js            Stateful JavaScript chat client
requirements.txt      Python dependencies
requirements-dev.txt  Test dependencies
tests/test_app.py     HTTP + WebSocket integration tests
tests/browser_smoke.py Optional browser QA utility (requires Playwright)
docs/                 Demo/pitch notes
Dockerfile            Optional container deployment
railway.json          Single-replica Railway health check/build config
.dockerignore         Prevents dev databases and demo assets entering builds
.env.example          Environment options
```

## 5. Run the automated tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Coverage includes unauthenticated access, registration/login/logout, duplicate handles, origin protection, duplicate room prevention, delivery over WebSockets, persistence after disconnect, idempotent sends, group chats, reactions, seen states, authorized editing/deleting, membership-based message privacy, security headers, and message-rate limits. For a genuine over-the-network WebSocket integration check, run `python tests/socket_network_smoke.py` after installing `requests` and `websockets`.

### Manual two-browser acceptance test (ideal for judges)

1. Register **User A** in regular Chrome, **User B** in Incognito.
2. A creates a private chat with B. Both can see it immediately.
3. A sends `Hello from First Commit!`. B receives it instantly **without refreshing**.
4. B opens the room: A's ✓ changes to ✓✓ as the message is seen.
5. B types: A sees B's typing indicator. B sends a response.
6. Add a third account and create a **Circle** with all three accounts.
7. Try emoji reactions, edit/delete, refresh both windows, then search history.
8. Open on a phone-sized browser window. Verify the conversation drawer and composer.

## 6. Configuration and deployment

Copy `.env.example` if you want a reference; variables are read from the environment (not loaded automatically from the `.env` file).

| Variable | Default | Meaning |
|---|---|---|
| `HUDDLE_DB` | `./huddle.db` | Writable SQLite path |
| `SEED_DEMO` | `0` | Only enable locally to load sample accounts |
| `SECURE_COOKIES` | `0` | Set `1` when public app runs under HTTPS |

Simple process deployment:

```bash
HUDDLE_DB=/data/huddle.db SECURE_COOKIES=1 SEED_DEMO=0 \
  uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

For a public deployment, set up **HTTPS / WSS** at your host or reverse proxy and provide a **persistent disk volume** for the SQLite file. Do not expose this developer server directly to the Internet without HTTPS and normal infrastructure safeguards. Docker deployment is supported by the included Dockerfile (mount `/data` as a persistent volume). Do **not** commit a filled-in `.env`, database, or credentials to Git. For free-tier hosting instructions, practical limits, and data-loss warnings, read [`docs/PUBLIC_DEPLOYMENT.md`](docs/PUBLIC_DEPLOYMENT.md).

## 7. Submission guide for First Commit

The PDF explicitly asks for:

1. **GitHub repository** containing complete source code and README. Keep private until the hackathon ends; public visibility is allowed at final submission.
2. **Working web application** for judges to run and test. Public deployment is optional, but helps.
3. **PowerPoint presentation** uploaded to Google Drive with public-link access.
4. **Short actual demo video** uploaded publicly on YouTube, with the shareable URL.

The PPT and a precise live-demo/video script are provided alongside this project bundle. A **genuine screen recording of this app running in your own browser** must be captured and uploaded to YouTube. Likewise, GitHub, Drive, and public hosting need access to accounts you control; URLs cannot be generated locally.

### Judging strategy

- **Shortlisting (50):** core functionality 20 + technical implementation 15 + useful optional features 15.
- **Final judging (50 more):** reliable live demo 25 + compelling pitch 25.
- **24-hour build:** prioritize a working two-user demo over speculative AI add-ons.

## 8. Security notes

- Passwords are Argon2id-hashed; sessions use random tokens whose **hashes**, not raw values, are stored in DB.
- Cookies are HttpOnly, SameSite=Strict. Enable Secure cookies when behind HTTPS.
- Mutation requests and WebSocket connections reject mismatched `Origin` headers.
- Server checks every room membership before reading or sending messages, or seeing message search results.
- SQL operations are parameterized, user HTML is escaped client-side, and session expiration is checked.
- Login attempts have basic per-IP throttling, but a high-traffic production service requires shared rate limiting, observability, monitoring, abuse controls, and coordinated multi-node infrastructure.
- No E2EE claim: server administrators with database access can read message bodies.

## 9. Roadmap

A second iteration could add file uploads with type validation/scanning, notifications, channels for clubs/events, push delivery, database migrations, automated browser tests in CI, Redis-backed horizontal scaling, and opt-in AI message summaries. These are **future ideas**, not already built.

---

**Pitch line:** *Huddle turns scattered campus messages into a real place for the people and projects that matter.*

### Start without typing setup commands

- **Windows:** double-click `start_demo_windows.bat` (Python 3 must be installed).
- **macOS/Linux:** run `bash start_demo_mac_linux.sh`.

Both starter scripts use sample data and should be used only on your own laptop.

For an organizer-facing submission summary and final links checklist, see [`docs/SUBMISSION_CHECKLIST.md`](docs/SUBMISSION_CHECKLIST.md).