# Huddle reliability and collaboration release (October 2026)

This release builds on the existing First Commit messaging app. Features are
bounded by the deployment configuration, browser permissions and service providers.
Do not describe the beta capabilities below as universally available.

## What is implemented in source

- **Per-account pin, archive and mute preferences** in persistent SQLite, independent
  of other room members. The Archived toggle restores chats.
- **Personal user blocks**, with bidirectional direct-message checks at both
  direct conversation creation and text sending (HTTP and WebSocket).
  Reporting and group moderation continue to exist independently.
- **Member-only polls and events** with single-vote switching and going/maybe
  RSVP choices. Event times are normalized to UTC; users see local times.
- **Password recovery** for accounts with verified Huddle email addresses.
  Secure single-use eight-digit codes expire after 10 minutes and invalidate
  all previous sessions when used. Requires a working configured Brevo sender.
  Google-only sign-in is not automatically converted into a password account.
- **Browser installability** via manifest, icon and conservative service worker.
  The worker caches public static app shell files only; it NEVER caches
  authenticated API responses, images, private chat history or media URLs.
- **Offline text-only queue** with per-user local-device storage and unique nonces.
  Sent on reconnection; unrecoverable failures are saved as local failed drafts.
  An unsent message is *not* delivered until the server confirms it. Attachments
  are not queued. Shared-device users should sign out to erase queued text.
- **Web Push** API, opted in through the notification setting. Push alerts use
  a generic body; message contents are never delivered in push payloads.
  Requires VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY and VAPID_CONTACT on Railway.
  Without these, existing in-app browser alerts continue working while Huddle is open.
  Push requires browser permissions, OS support and installed/eligible browsers.
- **1:1 WebRTC voice/video call beta** with explicit Accept/Decline and local media
  permission prompts. The server relays bounded offer/answer/ICE messages only
  to authenticated members of the direct conversation. Call media is peer to peer
  and is not saved to the Huddle database. Calls can fail behind restrictive
  routers because no TURN relay is currently configured; group calling is absent.
  A working cross-network production calling service needs TURN, consent UX and
  real-device interoperability checks.
- **Optional video trim and smaller WebM export** in supported desktop/mobile
  browsers using MediaRecorder and captureStream, for clips 0.5–45 seconds.
  The source is not modified, and media previews/ordinary uploads remain available
  when the browser cannot export; codec compatibility varies.
- **Encrypted offsite-backup exporter** at scripts/backup_huddle.py. This is NOT
  an active backup job until HUDDLE_BACKUP_KEY and an HTTPS private
  HUDDLE_BACKUP_UPLOAD_URL are configured and a trusted job scheduler is set up.
  The backup key must never be pushed to GitHub.

## Not yet fully complete / requires separate work

- **True end-to-end encryption (E2EE): NOT IMPLEMENTED.** HTTPS protects transport
  and Huddle's server-side encryption protects stored message bytes, but the
  server can decrypt them. Genuine E2EE needs multi-device identity keys,
  client key generation and verification, a secure ratchet and recovery protocol,
  attachment encryption, migration, threat modeling, independent security review,
  and coordinated WebSocket/HTTP changes. Turning on an unaudited substitute
  could silently lose messages or give users false privacy promises.
- **Automatic, offsite-tested backups:** the exporter exists, but the user must
  provide an external private storage destination and scheduler, and verify
  restoration. A single Railway persistent volume cannot protect itself from
  platform/volume loss.
- **Password recovery emails:** require Brevo transactional email credentials.
- **Background push delivery:** requires owner-created VAPID keys; no keys means
  subscription endpoints remain disabled.
- **Unrestricted WebRTC calls:** require TURN relay/configuration and real-device
  testing; the current implementation is a beta.
- **Always-on server-provided AI:** requires configured provider keys/credits;
  separate Puter opt-in remains a supported alternative.

## Security and operations

- Deploy exactly one worker until WebSocket connection fan-out is moved to shared
  pub/sub; SQLite also needs a durable volume or database migration.
- Never expose Google/Firebase, VAPID private, email, backup, encryption or AI
  secret keys in web assets, commits, or screenshots.
- Test new features with two signed-in accounts, two physical devices,
  network disconnection/reconnection and restricted mobile browsers.
- Do not enable backup exporter without a trusted owner-controlled offsite URL.
- Browser-generated WebM may not play in all clients; recipient should be able
  to fall back to another codec or the original video.
- Encourage users to test before relying on experimental calling.

## Files added

- app/reliability.py, app/account_recovery.py, app/push_alerts.py
- app/web/reliability-ui.js, app/web/reliability-ui.css
- app/web/manifest.webmanifest, app/web/sw.js, app/web/pwa-register.js
- app/web/push-register.js, app/web/recover-account.js, app/web/offline-text-queue.js
- app/web/webrtc-calls.js, app/web/webrtc-calls.css, app/web/video-trim.js
- scripts/backup_huddle.py, tests/test_reliability_upgrade.py

## Safe rollout checklist

1. Confirm new Python tests and browser tests pass.
2. Review PR diff and merge to main.
3. Confirm Railway health is successful on the merged main commit.
4. Independently test account recovery with a verified sender before enabling.
5. Provision VAPID keys and confirm push messages work after closing the app.
6. Configure and restore-test offsite backup from a separate storage account.
7. Test WebRTC and WebM export on at least two real phones.
8. Complete separate E2EE design/security review before making any E2EE claim.
