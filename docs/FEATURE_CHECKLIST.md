# Huddle — First Commit Problem Statement Checklist

This checklist follows the user-provided screenshot in its original order.
The document itself explicitly calls these **optional extensions** and **examples**, not mandatory features.

## Core functionality
- [x] **Authentication:** Account registration, login, secure sessions and optional Google identity.
- [x] **Initiate conversation with another user:** Search registered users by name/handle; create one-to-one room.
- [x] **Messages delivered in real time:** WebSocket fan-out with HTTP fallback and reconnect.
- [x] **Messages associated with appropriate users and conversations:** User/room IDs, foreign keys and membership-based authorization.

## Optional extensions (section 03)
- [x] **Group Conversations:** Named Circles, multiple members, admins and additional member invitations.
- [x] **Persistent Database:** SQLite WAL with users, conversations, messages, groups, memberships and timestamps on a Railway persistent volume.
- [x] **Chat Encryption:** Transport HTTPS/WSS plus optional Fernet server-side encryption at rest. Railway production now configures the required stable HUDDLE_MESSAGE_KEY. This is **NOT** end-to-end encryption; a server holding the key can decrypt messages.
- [x] **Multimedia Messaging — Images:** JPEG, PNG, WebP files, private image previews and download.
- [x] **Multimedia Messaging — Voice notes:** Browser MediaRecorder recording, upload and inline playback. Requires user microphone permission and a compatible browser.
- [x] **Multimedia Messaging — File sharing:** DOCX, PDF and plain-text files with user-only access; maximum 6 MB.
- [~] **File Safety:** Strict file extension and media type matching, file signature checks, Pillow image parsing, DOCX zip checks and PDF active-script checks. These are partial protections, **not full antivirus scanning**; a dedicated malware scanner is still required for unrestricted file hosting.
- [x] **LLM-Powered Conversations:** ChatGPT-style study assistant via browser-hosted small open-source model, with optional enhanced model. Does not automatically ingest other participants' chat messages.
- [x] **Context-Aware AI:** An explicit checkbox opts in to sharing recently opened conversation highlights with the user's local AI. Not automatic; only available to a participant.
- [x] **Message reactions:** Emojis.
- [x] **Typing indicators:** Live WebSocket events.
- [x] **Read receipts:** Seen states per user and conversation.
- [x] **Online/offline status:** Connected user status.
- [x] **Message search:** Search only user's permitted conversations; supports encrypted storage.
- [x] **Message editing/deletion:** Sender-only edit and delete actions.
- [~] **Notifications:** Opt-in browser notifications while Huddle's page is open. Background push when the browser is fully closed is not implemented.
- [x] **User profiles:** Display names, bio and usernames.
- [x] **Media previews:** Images and audio preview; documents download as attachments.
- [~] **Chat moderation:** Users can report messages, Circle admins can review/dismiss reports and remove non-admin Circle members. Platform-wide human moderation and automated content detection are not implemented.

## Technical considerations (section 04)
- [x] **WebSockets:** Persistent WebSocket connection for real-time messages, typing and presence.
- [x] **Reliable mandatory multiuser one-to-one chat:** Membership checks, message nonce deduplication and REST fallback; covered by integration tests.
- [x] **Authentication and session management:** Secure tokens, HttpOnly/SameSite cookies, session revocation and Argon2id passwords.
- [x] **Persistent database:** SQLite on a Railway volume. Horizontal scaling beyond one worker needs a shared pub/sub system and scalable SQL backend; not presently built.
- [x] **Frontend-backend architecture:** HTML/CSS/JavaScript front end, FastAPI back end, SQL data.
- [x] **Suitable choice of languages/frameworks/hosting:** Open Python/FastAPI/SQLite/JavaScript stack deployed to Railway.
- [x] **Third-party APIs/libraries and pretrained models may be used:** Firebase or Google login and optional browser-hosted Transformers AI model; external AI providers remain optional.

## Critical honesty notes
No voice/video calling or end-to-end encrypted messages. File validation does not equal an antivirus scan. Photorealistic image generation remains unavailable without an image provider; Huddle Poster Studio produces designed graphic PNGs. The local LLM can hallucinate, and the upgraded model may require more browser storage/memory. Browser alerts only work when Huddle is open. Admin reports are reviewed within Circles; there is no professional platform-wide moderation operations team.
