# Home Server Migration Checklist

Migrate prodbot from the GCE Ubuntu VM to the home Ubuntu server (same box that hosts mdnssv-portfolio). Mirrors the portfolio's `docs/archive/infra_checklist` + `webhook_deploy` patterns where they apply, with bot-specific adjustments (no Cloudflare Tunnel — Discord is outbound-only; Python instead of Node; SQLite writable data dir).

End state: pushing to `master` triggers a deploy automatically; bot runs as an unprivileged system user; secrets live outside the repo; DB files survive deploys.

## Pre-flight

0. [Complete: N] **Rotate exposed credentials.**
   The current `.env` (untracked but present locally) and `private-keys.json` were visible during planning. Before cutover:
   - Discord Developer Portal → Bot → Reset Token (`DISCORD_TOKEN`)
   - Anthropic Console → API Keys → revoke and regenerate (`ANTHROPIC_API_KEY`)
   - Google Cloud Console → IAM & Admin → Service Accounts → key whose contents are in `private-keys.json` → delete + create new
   Use the *new* values in step 5 below — never paste the old ones onto the home server.

## Server prep

1. [Complete: Y] **Install Python 3.**
   Portfolio install already gave us a working Ubuntu box. Just add Python:
   ```
   sudo apt update
   sudo apt install -y python3 python3-venv python3-pip
   python3 --version
   ```

2. [Complete: Y] **Create deploy directory and runtime user.**
   Mirrors portfolio step 6. Admin user owns `/srv/prodbot` so it can rsync/deploy without sudo; an unprivileged system user `prodbot` runs the systemd service:
   ```
   sudo mkdir -p /srv/prodbot
   sudo chown $USER:$USER /srv/prodbot
   sudo useradd --system --no-create-home --shell /usr/sbin/nologin prodbot
   id prodbot   # verify: system UID, no login shell
   ```

3. [Complete: Y] **Create writable data directory for SQLite.**
   Bot writes `bot.db` and `jobs.db` at runtime. Keeping them under `/srv/prodbot` would force `ReadWritePaths=` to include the code dir, which weakens `ProtectSystem=strict`. Put DBs in their own dir owned by the runtime user:
   ```
   sudo install -d -o prodbot -g prodbot -m 700 /var/lib/prodbot
   ```

## Code on server

4. [Complete: Y] **Add a GitHub deploy key and clone.**
   Portfolio step 7, same flow but separate key (one repo per key keeps blast radius small). On the home server as the admin user:
   ```
   ssh-keygen -t ed25519 -f ~/.ssh/github_prodbot -N "" -C "homeserver-prodbot-deploy"
   cat ~/.ssh/github_prodbot.pub
   ```
   GitHub: prodbot repo → Settings → Deploy keys → Add deploy key → paste, name `homeserver`, **read-only** (no write access).

   Tell SSH to use this key for *this* repo. The portfolio's `~/.ssh/config` already claims `Host github.com` for its key, so use a host alias:
   ```
   cat >> ~/.ssh/config <<'EOF'
   Host github-prodbot
     HostName github.com
     User git
     IdentityFile ~/.ssh/github_prodbot
     IdentitiesOnly yes
   EOF
   chmod 600 ~/.ssh/config
   ```
   Clone via the alias and pin to `master` (the deploy branch):
   ```
   git clone git@github-prodbot:MrBruh/prodbot.git /srv/prodbot
   cd /srv/prodbot
   git checkout master
   git remote set-url origin git@github-prodbot:MrBruh/prodbot.git
   ```
   The `set-url` ensures future `git fetch origin` calls (in the deploy script) use the alias too.

5. [Complete: Y] **Create venv and install deps.**
   ```
   cd /srv/prodbot
   python3 -m venv venv
   ./venv/bin/pip install --upgrade pip
   ./venv/bin/pip install -r requirements.txt
   ```

## Configuration

6. [Complete: Y] **Make DB paths configurable via env vars.**
   Currently `database.py:3` hardcodes `DB_PATH = "bot.db"` and the APScheduler URL is similarly hardcoded. Change both to read from env, defaulting to the current values for local dev:
   ```python
   # database.py
   import os
   DB_PATH = os.getenv("DATABASE_PATH", "bot.db")
   ```
   ```python
   # services/scheduler_service.py
   import os
   JOBS_URL = os.getenv("JOBS_DATABASE_URL", "sqlite:///jobs.db")
   ```
   Commit these changes before the first deploy so the production env vars (step 7) actually take effect.

7. [Complete: Y] **Configure secrets file.**
   Portfolio step 8 pattern, root-owned mode 600, loaded by systemd via `EnvironmentFile=`:
   ```
   sudo tee /etc/prodbot.env > /dev/null <<'EOF'
   DISCORD_TOKEN=<rotated value from step 0>
   ANTHROPIC_API_KEY=<rotated value from step 0>
   BOT_CHANNEL_ID=1482618260061950113
   DATABASE_PATH=/var/lib/prodbot/bot.db
   JOBS_DATABASE_URL=sqlite:////var/lib/prodbot/jobs.db
   GOOGLE_CREDENTIALS_PATH=/srv/prodbot/credentials.json
   EOF
   sudo chmod 600 /etc/prodbot.env
   ```
   Note the four slashes in `sqlite:////var/...` — three for the URL scheme, one for the absolute path's leading `/`.

8. [Complete: N] **(Skippable) Place Google OAuth credentials.**
   This step is only needed if Gmail integration is actually working on the GCE VM today. To check:
   ```
   ssh gce-vm 'ls -l /home/deploy/prodbot/credentials.json /home/deploy/prodbot/token.json 2>/dev/null'
   ```
   - **Both files exist** → continue with the transfer below.
   - **Neither file exists** → Gmail integration was never set up. Skip this step. `services/gmail_service.py` is built to fail open: missing files → logs `"Gmail not configured"` and `!email check` replies `"Gmail is not configured."`. Everything else (reminders, todos, journal, links, bucket list, mentions) works normally. Revisit when you actually want Gmail to work.
   - **Only `credentials.json` exists, no `token.json`** → consent flow has never been run. You'd need to bootstrap `token.json` (see headless gotcha below) before this is useful on the home server.

   **`private-keys.json` is not used by any code path** — grep across `services/`, `cogs/`, and root `*.py` finds zero loaders. Don't bother copying it; it's stale. If you want, delete it on the GCE VM too.

   `services/gmail_service.py:29` looks for `credentials.json` relative to the working directory. Either keep that filename or update the service to read `os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")` (preferred — matches step 7).

   **Headless gotcha:** `gmail_service.py:31` uses `flow.run_local_server(port=0)` which opens a browser at `localhost:<random>` for consent. That can't run on the headless home server. To bootstrap a fresh `token.json` later: run the consent flow on a machine with a browser (using your `credentials.json`), then transfer the resulting `token.json` to the server. Worth a TODO in the code if/when you enable Gmail.

   Transfer — pick one based on whether the VM can reach the home server directly:

   **(a) Direct VM → home server.** SSH into the VM, then scp out:
   ```
   ssh gce-vm
   # on the VM:
   scp /home/deploy/prodbot/credentials.json \
       /home/deploy/prodbot/token.json \
       /home/deploy/prodbot/private-keys.json \
       homeserver:/tmp/
   exit
   ```
   Requires the VM to have an SSH key the home server accepts. Set this up by appending the VM's `~/.ssh/id_*.pub` to the home server's `~/.ssh/authorized_keys` first.

   **(b) VM → this PC → home server** (two hops from this Windows machine — no extra SSH config needed):
   ```
   scp gce-vm:/home/deploy/prodbot/credentials.json $env:TEMP\
   scp gce-vm:/home/deploy/prodbot/token.json $env:TEMP\
   scp gce-vm:/home/deploy/prodbot/private-keys.json $env:TEMP\
   scp "$env:TEMP\credentials.json" "$env:TEMP\token.json" "$env:TEMP\private-keys.json" homeserver:/tmp/
   Remove-Item "$env:TEMP\credentials.json","$env:TEMP\token.json","$env:TEMP\private-keys.json"
   ```
   The final `Remove-Item` wipes the local copies so secrets don't linger in `%TEMP%`.

   Then on the home server, move into place and lock down:
   ```
   sudo mv /tmp/credentials.json /tmp/token.json /tmp/private-keys.json /srv/prodbot/
   sudo chown prodbot:prodbot /srv/prodbot/credentials.json /srv/prodbot/token.json /srv/prodbot/private-keys.json
   sudo chmod 600 /srv/prodbot/credentials.json /srv/prodbot/token.json /srv/prodbot/private-keys.json
   ```
   Bringing `token.json` over avoids a fresh OAuth consent flow on first run.

## Migrate data from GCE VM

9. [Complete: Y] **Copy SQLite databases off the old VM.**
   Stop the old service first so the DBs are quiesced, then transfer:
   ```
   # on the GCE VM
   sudo systemctl stop prodbot
   # on your laptop (or directly between hosts if you have ssh-agent forwarding)
   scp gce-vm:/home/deploy/prodbot/bot.db /tmp/
   scp gce-vm:/home/deploy/prodbot/jobs.db /tmp/
   scp /tmp/bot.db /tmp/jobs.db homeserver:/tmp/
   # on the home server
   sudo mv /tmp/bot.db /tmp/jobs.db /var/lib/prodbot/
   sudo chown prodbot:prodbot /var/lib/prodbot/bot.db /var/lib/prodbot/jobs.db
   sudo chmod 600 /var/lib/prodbot/bot.db /var/lib/prodbot/jobs.db
   ```
   Skip this step if you're fine starting with empty reminders/journals/todos.

## systemd

10. [Complete: Y] **Update `deploy/prodbot.service` for the home server.**
    Edit in the repo (and commit), then install. Required diffs from the current file:
    - `User=deploy` → `User=prodbot`
    - `WorkingDirectory=/home/deploy/prodbot` → `WorkingDirectory=/srv/prodbot`
    - `ExecStart=/home/deploy/prodbot/venv/bin/python bot.py` → `ExecStart=/srv/prodbot/venv/bin/python bot.py`
    - `EnvironmentFile=/home/deploy/prodbot/.env` → `EnvironmentFile=/etc/prodbot.env`
    - `ReadWritePaths=/home/deploy/prodbot` → `ReadWritePaths=/var/lib/prodbot`
      (Code dir stays read-only at runtime — DBs live in `/var/lib/prodbot` per step 3.)

11. [Complete: N] **Install and start the service.**
    ```
    sudo cp /srv/prodbot/deploy/prodbot.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now prodbot
    sudo systemctl status prodbot --no-pager
    sudo journalctl -u prodbot -f   # confirm Discord login + slash command sync
    ```
    If startup fails on `ProtectSystem=strict`, the bot is trying to write somewhere outside `ReadWritePaths=`. Fix the path, don't widen the rule.

12. [Complete: N] **NOPASSWD sudoers for service restart.**
    Required so the deploy script (step 14) can restart the service non-interactively:
    ```
    echo "$USER ALL=(root) NOPASSWD: /usr/bin/systemctl restart prodbot" | sudo tee /etc/sudoers.d/prodbot-restart
    sudo chmod 440 /etc/sudoers.d/prodbot-restart
    sudo visudo -c
    ```
    Verify with cleared cache (per portfolio webhook_deploy pitfall #4):
    ```
    sudo -K
    sudo -n /usr/bin/systemctl restart prodbot && echo OK
    ```

## Deploy automation

13. [Complete: N] **Decide deploy mechanism.**
    Two options — pick one:

    **(a) Webhook (recommended — reuses the portfolio's daemon).** Push to `master` → GitHub webhook → existing `webhook` daemon at `127.0.0.1:9000` → `/srv/prodbot/deploy.sh`. Continue with steps 14–17.

    **(b) Push-to-bare-repo (simpler, manual `git push`).** Skip 14–17, instead update `deploy/post-receive`'s paths and follow the existing `deploy/README.md` (with `s|/home/deploy/prodbot|/srv/prodbot|`).

14. [Complete: N] **Write `/srv/prodbot/deploy.sh`.** *(option a only)*
    ```
    cat > /srv/prodbot/deploy.sh <<'EOF'
    #!/bin/bash
    set -euo pipefail
    cd /srv/prodbot
    git fetch origin
    git checkout master
    git reset --hard origin/master
    ./venv/bin/pip install -r requirements.txt --quiet
    sudo systemctl restart prodbot
    EOF
    chmod +x /srv/prodbot/deploy.sh
    ```
    Sanity-check by running it manually before wiring up the webhook: `/srv/prodbot/deploy.sh` should exit 0 and the bot should restart cleanly.

15. [Complete: N] **Add a hook entry to the existing webhook daemon.** *(option a only)*
    Generate a fresh secret (different from the portfolio's — one per project):
    ```
    openssl rand -base64 32 > ~/.prodbot-webhook-secret
    chmod 600 ~/.prodbot-webhook-secret
    ```
    Append to `/etc/webhook/hooks.json` (it's a JSON array — add the object inside the brackets, alongside the existing `deploy-portfolio` entry):
    ```json
    {
      "id": "deploy-prodbot",
      "execute-command": "/srv/prodbot/deploy.sh",
      "command-working-directory": "/srv/prodbot",
      "trigger-rule": {
        "and": [
          {
            "match": {
              "type": "payload-hmac-sha256",
              "secret": "<paste from ~/.prodbot-webhook-secret>",
              "parameter": { "source": "header", "name": "X-Hub-Signature-256" }
            }
          },
          {
            "match": {
              "type": "value",
              "value": "refs/heads/master",
              "parameter": { "source": "payload", "name": "ref" }
            }
          }
        ]
      }
    }
    ```
    Note: `value` is `refs/heads/master`, not `refs/heads/main` — prodbot's deploy branch is `master`. Then:
    ```
    sudo systemctl restart webhook
    sudo journalctl -u webhook -f
    ```

16. [Complete: N] **Configure GitHub webhook.** *(option a only)*
    Repo → Settings → Webhooks → Add webhook:
    - Payload URL: `https://webhook.denissov.tech/hooks/deploy-prodbot`
    - Content type: `application/json`
    - Secret: paste from `~/.prodbot-webhook-secret`
    - SSL verification: enabled
    - Events: *Just the push event*
    - Active: yes

    GitHub sends a `ping` on save — Recent Deliveries should show `200 Hook rules were not satisfied.` (HMAC matched, but no `ref` in ping payload, so the branch rule rejects). That's the success signal: secret is in sync.

    No new Cloudflare Tunnel route needed — `webhook.denissov.tech` already exists and routes to `127.0.0.1:9000`. The path differentiates hooks.

17. [Complete: N] **End-to-end deploy test.** *(option a only)*
    From your laptop, push a trivial commit to `master`:
    ```
    git commit --allow-empty -m "test: home server deploy"
    git push origin master
    ```
    Within ~30–60s:
    - GitHub Recent Deliveries: `200 OK`
    - `journalctl -u webhook -f`: deploy.sh stdout
    - `journalctl -u prodbot -f`: service restart, Discord re-login

## Cutover and cleanup

18. [Complete: N] **Verify the bot is healthy on the home server.**
    In Discord, run a few commands the bot supports (a slash command, a reminder, etc.). Confirm reminders fire on schedule (APScheduler is in-memory per `5d1e522` — but `jobs.db` migration in step 9 still preserves any persisted state from older code paths).

19. [Complete: N] **Decommission the GCE VM.**
    Only after the home server has been stable for at least 24 hours and a reminder has actually fired:
    ```
    # on the GCE VM
    sudo systemctl stop prodbot
    sudo systemctl disable prodbot
    ```
    Then in GCP console: stop the VM (cheap to keep around as a fallback for a week), or delete it outright if you're confident.

20. [Complete: N] **Update `deploy/README.md`.**
    Currently it documents the GCE Ubuntu VM setup. Either replace it with a pointer to this file, or strip the GCE-specific bits and merge the home server steps into it. Pick one — having two contradictory deploy docs is the failure mode.
