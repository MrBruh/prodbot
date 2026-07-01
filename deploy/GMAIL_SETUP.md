# Gmail self-service setup

Lets any member of the server connect **their own** Gmail so the bot can report
their unread mail — no per-user keys in the repo. Each person runs
`!email register`, approves a Google consent screen, and the bot stores *their*
refresh token keyed by Discord id.

There are two credentials, and only the second is per-user:

- **The OAuth client** (one client ID + secret) identifies *the bot* to Google.
  You create it once and keep it as a server secret. It grants access to nobody's
  mailbox on its own.
- **Per-user refresh tokens** are obtained through consent and stored in the
  bot's database, never hard-coded.

The bot requests only the **`gmail.metadata`** scope: it can read labels and
message headers (From / Subject) but never message bodies or attachments.

## 1. Google Cloud — one-time app setup

1. **Project + API.** In the [Google Cloud Console](https://console.cloud.google.com/):
   create (or reuse) a project → **APIs & Services → Library → Gmail API → Enable**.

2. **OAuth consent screen.** APIs & Services → OAuth consent screen:
   - User type: **External**.
   - Fill app name, support email, developer email.
   - **Scopes:** add `.../auth/gmail.metadata` (restricted). No others.
   - **Publishing status: Publish to Production.** *(Important — see the token
     lifetime note below. Leaving it in "Testing" makes every refresh token
     expire after 7 days.)* You'll click through an "unverified app" warning; for
     a small trusted server that's fine. Full verification (a paid security
     assessment) is only needed to remove the warning or exceed ~100 users.

3. **OAuth client.** APIs & Services → Credentials → **Create credentials →
   OAuth client ID**:
   - Application type: **Web application**.
   - **Authorized redirect URI:** `https://prodbot.denissov.tech/oauth/callback`
     (must match `OAUTH_REDIRECT_URI` exactly, scheme and path included).
   - Save the generated **Client ID** and **Client secret**.

## 2. Cloudflare Tunnel — expose the callback

The home server already runs a Cloudflare Tunnel (it serves
`webhook.denissov.tech`). Add one more hostname pointing at the bot's local
OAuth port:

- Cloudflare Zero Trust → Networks → Tunnels → the existing tunnel → **Public
  Hostname → Add**:
  - Subdomain `prodbot`, domain `denissov.tech`.
  - Service: `HTTP` → `127.0.0.1:8080`.

Only `/oauth/callback` and `/healthz` are served; everything else 404s. The bot
binds `127.0.0.1` only, so the tunnel is the sole path in.

## 3. Server config

Add to `/etc/prodbot.env` (root-owned, mode 600 — same file as the other
secrets):

```
GOOGLE_CLIENT_ID=<client id from step 1.3>
GOOGLE_CLIENT_SECRET=<client secret from step 1.3>
OAUTH_REDIRECT_URI=https://prodbot.denissov.tech/oauth/callback
OAUTH_SERVER_PORT=8080
```

`OAUTH_SERVER_HOST` defaults to `127.0.0.1` and needs no override. With these
unset the bot boots exactly as before and all `!email` commands reply "not set
up" — so this is safe to deploy before the Google side is ready.

No systemd changes are required: the callback server binds a loopback port
(needs no new `ReadWritePaths`), and refresh tokens live in the existing
`bot.db` under `/var/lib/prodbot`.

Restart to pick up the new env:

```
sudo systemctl restart prodbot
sudo journalctl -u prodbot -f   # look for "OAuth callback server listening on 127.0.0.1:8080"
```

Sanity-check the tunnel: `curl https://prodbot.denissov.tech/healthz` → `ok`.

## 4. Using it

- `!email register` — the bot DMs you a personal Google consent link (expires in
  10 min). Approve it; the bot confirms by DM.
- `!email check` — shows your unread mail. "check my email" in the bot channel
  works too (natural-language routing).
- `!email forget` — deletes your stored token from the bot.
- To fully revoke the bot's access to your account, also remove it at
  [myaccount.google.com/permissions](https://myaccount.google.com/permissions).

## Notes & gotchas

- **7-day token expiry in Testing mode.** External OAuth apps left in "Testing"
  expire refresh tokens after 7 days, forcing weekly re-registration. Publishing
  to Production (step 1.2) avoids this.
- **Why `labelIds=["UNREAD"]` and not a search query.** The `gmail.metadata`
  scope forbids the free-text `q` parameter, so unread mail is listed by label.
- **Security posture.** Consent links are DM'd only (never posted in a channel)
  and carry a one-shot, 10-minute `state` token bound to the requesting Discord
  id. Refresh tokens are stored in `bot.db` (mode 600, unprivileged user).
  Encrypting them at rest with an app-held key is a reasonable future hardening.
- **Scope changes.** If you later want message snippets/bodies, switch `SCOPES`
  in `services/gmail_service.py` to `gmail.readonly`, update the consent screen,
  and have everyone re-register.
