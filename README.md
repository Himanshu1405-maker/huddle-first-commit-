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

File attachments, voice/video calls, and end-to-end encrypted messages are **not** implemented. Huddle AI chat and image generation integrations are implemented but require external provider credentials and available credits to activate. The hackathon PDF lists these as optional examples, not mandatory requirements. This implementation prioritizes the reliable communication foundation plus several useful optional features. The connection is encrypted in transit **when deployed under HTTPS/WSS**, but message content is stored in regular SQLite and **is not end-to-end encrypted**.

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

## Huddle 2.1 · Google sign-in (OAuth)

Google login uses **Google Identity Services** and secure server-side verification of ID tokens (signed public keys, audience, issuer, verified email and stable Google subject). No Google client secret is required for the popup-based button. Existing Huddle accounts are **never silently matched or taken over via email**; users can sign into their current account with password and link Google from **Profile**. Google-only accounts have a random unguessable stored password hash, so they cannot use password login unless a separate recovery flow is implemented.

Setup (free OAuth credentials):

1. Go to [Google Auth Platform / Clients](https://console.cloud.google.com/auth/clients) and create a **Web application** OAuth 2.0 client ID, after configuring the consent screen and app audience as required. For public users, use an External app. Configure testing or publish your app as appropriate.
2. Add **Authorized JavaScript origin** `https://huddle-web-production-76f3.up.railway.app` (no trailing slash). The popup-based GIS callback is handled in first-party JavaScript and does not require a redirect URI.
3. Copy the **client ID only** (format `...apps.googleusercontent.com`) into **Railway → Huddle → huddle-web → Variables** as `GOOGLE_CLIENT_ID`. A client ID is public configuration, **not** a secret; nevertheless avoid posting credentials other than this ID in chat. Never share a Google password, OAuth client secret or Google/Brevo/Gemini API key.
4. Redeploy/restart and open `/api/config` to confirm `google_login: true`; the branded Google button appears on both login and signup. The button is hidden when not configured so nobody encounters a fake sign-in feature.
5. Test a new Google account, sign out, sign in again, and test linking an existing password account in Profile. Do not attempt to merge accounts by matching unverified email addresses.

**Verification note:** Automated tests mock cryptographic verification only to test business logic; genuine Google OAuth cannot be fully tested until an OAuth client ID and authorized origin have been set in Google Cloud.

## Huddle 2.0 · Email OTP, Huddle AI, mobile UX

This release preserves existing accounts and chat history. It adds an email-verification flow for **new** registrations, a private AI assistant area, optional AI-image generation, and smoother mobile scrolling and navigation. Existing accounts have no email on record and remain usable without verification. Verification is not retroactively applied to them.

### Enable real OTP email delivery (free provider, owner setup)

1. Sign up for a Brevo account on the **Free** plan (currently limited to 300 emails/day). Verify a sender email/domain in Brevo and enable transactional email sending.
2. Generate a transactional email API key. In **Railway > huddle-web > Variables**, set `BREVO_API_KEY` to the key and `MAIL_FROM` to the *verified* sender address. Do **not** put secrets into GitHub, the frontend, screenshots, or a chat conversation.
3. Restart/redeploy the service so it picks up both environment variables. Open `/api/config`; `email_otp` must be `true`. New registrations now request an email address and enter a six-digit OTP before their accounts are created.
4. OTP codes expire after 10 minutes, allow at most 5 wrong attempts and at most one resend per minute. Codes are hashed in persistent SQLite; they are never logged, committed, or exposed to the frontend except in the actual email. No user session is created until verification.
5. If the provider is NOT configured, the old signup works to avoid unexpectedly locking out users. In that case OTP verification is **not active**. Do not advertise verified accounts unless `/api/config` confirms that the sender is configured and delivery is proven with a real test email.

### Enable Huddle AI

- For Q&A / tutoring, create a Gemini Developer API key for an account with free-tier API access and add `GEMINI_API_KEY` to Railway Variables. `GEMINI_MODEL` defaults to `gemini-3.5-flash-lite` (change to another available free text model when necessary). Requests are made from the **server**, with no key exposed in the browser. Questions and responses appear in the private Huddle AI tab and persist separately per user.
- For text-to-image, get a Hugging Face Inference Providers token with the needed permissions and credits. Add `HF_TOKEN`, then set `AI_IMAGES_ENABLED=1` **only if you have confirmed its available credits/charges**. The app calls a supported image provider via `huggingface_hub`; created images are stored on the persistent volume and can be opened only by their owner. The default model is `black-forest-labs/FLUX.1-schnell`. Verify current availability in the provider dashboard. Image generation is limited to two images/user/day. **The free allowance is very small; image generation is not unlimited or guaranteed to be free.**
- New AI functions are displayed in the side navigation, but if no provider is configured they honestly say so rather than pretending to generate text or images.
- The AI sends only the text explicitly entered in the Huddle AI tab. It **does not** read private conversations, other members' messages, or message history by default. Avoid entering sensitive information. Provider data-handling terms apply.

### Mobile performance and privacy

The UI uses smaller containment zones, less scroll restoration, native touch momentum, mobile-safe view heights, a responsive AI panel, and reduced-motion support. The AI and OTP endpoints enforce authorization/quotas. The app is still a single-process/SQLite hackathon pilot, not production infrastructure for large-scale public use. Mobile scrolling needs real-device validation; browser automation may be blocked in limited test environments.

### Verify release

Run `python -m pytest -q` and `node tests/frontend_smoke.cjs && node tests/frontend_otp_ai.cjs && node --check app/web/app.js`. For real WebSocket traffic run `python tests/socket_network_smoke.py`. For email OTP, connect an actual verified sender first and test a new account. For AI, supply provider keys to Railway, verify that `/api/config` reports enabled providers, and test with small prompts while monitoring credits. The tests mock provider calls; they **do not** establish that unconfigured external services deliver messages or generate images.


### Provider setup checklist (owner action needed before launch)

| Integration | Required Railway variables | Verification | Cost control |
|---|---|---|---|
| Google login | `GOOGLE_CLIENT_ID` | OAuth client with the exact Huddle URL as an authorized JS origin, Google Identity Services popup verified | Google login itself does not need a paid API |
| Email OTP | `BREVO_API_KEY`, `MAIL_FROM` | Verified sender in Brevo, real test email delivered, code accepted | Free tier and send quotas; watch activity |
| AI tutor | `GEMINI_API_KEY` | Generate an API key in Google AI Studio, test one prompt, inspect rate limits | Confirm project on free tier, do not enable paid billing |
| AI images | `HF_TOKEN`, `AI_IMAGES_ENABLED=1` | Credit availability and working inference model | Keep disabled until sufficient free credits are confirmed |

Do not set placeholders for API keys: `google_login`, `email_otp` and `ai_chat` in `/api/config` are **availability flags based on variables**, not evidence that external credentials are valid. A real sign-in, OTP delivery and AI test are required before public claims. Existing accounts, messages and database content are retained when deploying code updates.
