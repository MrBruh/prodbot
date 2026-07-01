"""Self-service Gmail OAuth: consent-link generation and the callback server.

Flow: a member runs `!email register`; the bot DMs them a Google consent URL
carrying a one-shot ``state`` token bound to their Discord id. After they
approve, Google redirects to ``/oauth/callback`` on the small aiohttp server
started here (reached from the internet via the existing Cloudflare Tunnel).
The callback exchanges the code for a refresh token and stores it keyed by
Discord id, so no per-user secret is ever hard-coded. See deploy/GMAIL_SETUP.md.
"""

import asyncio
import logging
import secrets
import time
from typing import Dict, Optional, Tuple

from aiohttp import web

from config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    OAUTH_REDIRECT_URI,
    OAUTH_SERVER_HOST,
    OAUTH_SERVER_PORT,
)
from services.gmail_service import SCOPES, gmail_configured, store_account

logger = logging.getLogger(__name__)

# Pending consent requests: state token -> (discord_user_id, expiry monotonic).
# In-memory and one-shot; a bot restart mid-registration just means the user
# re-runs `!email register`.
_PENDING: Dict[str, Tuple[int, float]] = {}
_STATE_TTL_SECONDS = 600  # 10 minutes


def _client_config() -> dict:
    return {
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [OAUTH_REDIRECT_URI],
        }
    }


def _build_flow(state: Optional[str] = None):
    from google_auth_oauthlib.flow import Flow

    return Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        redirect_uri=OAUTH_REDIRECT_URI,
        state=state,
    )


def _prune_expired(now: float) -> None:
    for state in [s for s, (_, exp) in _PENDING.items() if exp <= now]:
        _PENDING.pop(state, None)


def create_pending(discord_user_id: int) -> str:
    """Create a consent URL bound to a Discord user via a one-shot state token."""
    now = time.monotonic()
    _prune_expired(now)
    state = secrets.token_urlsafe(24)
    _PENDING[state] = (discord_user_id, now + _STATE_TTL_SECONDS)
    flow = _build_flow(state=state)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        # Force a consent screen so Google always returns a refresh token, even
        # if the user has authorized the app before.
        prompt="consent",
    )
    return auth_url


def pop_pending(state: str) -> Optional[int]:
    """Consume a pending state, returning the bound Discord user id if valid."""
    now = time.monotonic()
    _prune_expired(now)
    entry = _PENDING.pop(state, None)
    if not entry:
        return None
    discord_user_id, expires_at = entry
    if expires_at <= now:
        return None
    return discord_user_id


def _exchange_code(state: str, code: str) -> Tuple[Optional[str], Optional[str]]:
    """Blocking: exchange an auth code for tokens. Returns (email, refresh_token)."""
    flow = _build_flow(state=state)
    flow.fetch_token(code=code)
    creds = flow.credentials

    email = None
    try:
        from googleapiclient.discovery import build

        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        profile = service.users().getProfile(userId="me").execute()
        email = profile.get("emailAddress")
    except Exception:
        logger.warning("Could not fetch Gmail profile for connected account", exc_info=True)

    return email, creds.refresh_token


async def _notify_user(bot, discord_user_id: int, email: Optional[str]) -> None:
    try:
        user = bot.get_user(discord_user_id) or await bot.fetch_user(discord_user_id)
        where = f" (**{email}**)" if email else ""
        await user.send(f"✅ Your email{where} is connected. Use `!email check` anytime.")
    except Exception:
        logger.warning(
            "Could not DM user %s after connecting email", discord_user_id, exc_info=True
        )


def _page(title: str, body: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{title}</title><style>body{{font-family:system-ui,sans-serif;"
        "background:#171717;color:#e5e5e5;display:flex;min-height:100vh;"
        "align-items:center;justify-content:center;margin:0}"
        ".card{text-align:center;padding:2rem 3rem;border-radius:14px;background:#222;"
        "max-width:28rem}h1{color:#38bdf8;margin:0 0 .5rem}p{color:#a3a3a3}</style>"
        f"</head><body><div class='card'><h1>{title}</h1><p>{body}</p></div></body></html>"
    )


async def _handle_callback(request: web.Request) -> web.Response:
    bot = request.app["bot"]
    params = request.rel_url.query

    if params.get("error"):
        return web.Response(
            text=_page("Authorization cancelled", "You can close this tab."),
            content_type="text/html",
        )

    state = params.get("state", "")
    code = params.get("code", "")
    discord_user_id = pop_pending(state)
    if not discord_user_id or not code:
        return web.Response(
            text=_page("Link expired", "Run <code>!email register</code> in Discord again."),
            content_type="text/html",
            status=400,
        )

    loop = asyncio.get_event_loop()
    try:
        email, refresh_token = await loop.run_in_executor(None, _exchange_code, state, code)
    except Exception:
        logger.exception("OAuth token exchange failed")
        return web.Response(
            text=_page("Something went wrong", "Please try <code>!email register</code> again."),
            content_type="text/html",
            status=500,
        )

    if not refresh_token:
        return web.Response(
            text=_page("Couldn't finish", "No refresh token returned — try registering again."),
            content_type="text/html",
            status=400,
        )

    await store_account(discord_user_id, email, refresh_token)
    await _notify_user(bot, discord_user_id, email)
    return web.Response(
        text=_page("Email connected", "You can close this tab and head back to Discord."),
        content_type="text/html",
    )


async def _handle_health(_request: web.Request) -> web.Response:
    return web.Response(text="ok")


async def start_oauth_server(bot) -> Optional[web.AppRunner]:
    """Start the OAuth callback server, or skip if Gmail isn't configured."""
    if not gmail_configured() or not OAUTH_REDIRECT_URI:
        logger.info("Gmail OAuth not configured; skipping callback server")
        return None

    app = web.Application()
    app["bot"] = bot
    app.router.add_get("/oauth/callback", _handle_callback)
    app.router.add_get("/healthz", _handle_health)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, OAUTH_SERVER_HOST, OAUTH_SERVER_PORT)
    await site.start()
    logger.info("OAuth callback server listening on %s:%s", OAUTH_SERVER_HOST, OAUTH_SERVER_PORT)
    return runner
