from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
console = Console()

CLIENT_ID = os.getenv("TWITCH_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET", "")
OUT_DIR = ROOT / os.getenv("OUTPUT_DIR", "downloads")

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
API = "https://api.twitch.tv/helix"
USER_AGENT = "Twitch-pfp/1.0 (by 4swag)"

LOGIN_RE = re.compile(r"^[A-Za-z0-9_]{1,25}$")
# Helix returns the 300x300 rendition; the CDN keeps larger ones under the same name.
SIZE_RE = re.compile(r"-(\d+)x(\d+)(\.\w+)$")
TRY_SIZES = ["600x600", "300x300"]


def parse_login(target: str) -> str | None:
    # Accept bare logins, @login, or twitch.tv URLs.
    s = target.strip().lstrip("@")
    m = re.match(r"^(?:https?://)?(?:www\.|m\.)?twitch\.tv/([^/?#]+)", s, re.I)
    if m:
        s = m.group(1)
    s = s.lower()
    return s if LOGIN_RE.match(s) else None


async def get_token(client: httpx.AsyncClient) -> str:
    resp = await client.post(
        TOKEN_URL,
        data={"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "grant_type": "client_credentials"},
    )
    if resp.status_code != 200:
        raise RuntimeError(f"token request failed ({resp.status_code}): {resp.text}")
    return resp.json()["access_token"]


async def get(client: httpx.AsyncClient, path: str, params: Any) -> dict[str, Any]:
    for attempt in range(3):
        resp = await client.get(f"{API}{path}", params=params)
        if resp.status_code == 429:
            await asyncio.sleep(2 ** attempt)
            continue
        resp.raise_for_status()
        return resp.json()
    raise httpx.HTTPError("rate limited after retries")


async def lookup(client: httpx.AsyncClient, logins: list[str]) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for i in range(0, len(logins), 100):
        data = await get(client, "/users", [("login", l) for l in logins[i : i + 100]])
        for user in data.get("data", []):
            found[user["login"].lower()] = user
    return found


def candidate_urls(url: str) -> list[str]:
    m = SIZE_RE.search(url)
    if not m:
        return [url]
    urls = [url[: m.start()] + f"-{size}{m.group(3)}" for size in TRY_SIZES]
    return urls if url in urls else urls + [url]


async def download(client: httpx.AsyncClient, user: dict[str, Any]) -> dict[str, Any]:
    result = {"user": user, "path": None, "size": "-", "bytes": 0}
    src = user.get("profile_image_url") or ""
    for url in candidate_urls(src) if src else []:
        resp = await client.get(url)
        if resp.status_code != 200 or not resp.headers.get("content-type", "").startswith("image/"):
            continue
        size = SIZE_RE.search(url)
        tag = f"_{size.group(1)}x{size.group(2)}" if size else ""
        path = OUT_DIR / f"{user['login']}{tag}{Path(url).suffix or '.png'}"
        path.write_bytes(resp.content)
        result.update(path=path, size=f"{size.group(1)}x{size.group(2)}" if size else "original", bytes=len(resp.content))
        break
    return result


def created(ts: str | None) -> str:
    if not ts:
        return "unknown"
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    years = (datetime.now(timezone.utc) - dt).days / 365.25
    return f"{dt.strftime('%Y-%m-%d')} ({years:.1f}y)"


def render(r: dict[str, Any]) -> None:
    user = r["user"]
    table = Table(show_header=False, box=None, pad_edge=False)
    table.add_column(style="bold")
    table.add_column()

    table.add_row("Display name", user.get("display_name", "-"))
    table.add_row("Login", user["login"])
    table.add_row("User ID", user.get("id", "-"))
    table.add_row("Created", created(user.get("created_at")))
    table.add_row("Type", user.get("broadcaster_type") or "regular")
    if r["path"]:
        table.add_row("Image", f"[green]{r['size']}[/green] ({r['bytes'] // 1024} KB)")
        table.add_row("Saved to", str(r["path"]))
    elif not user.get("profile_image_url"):
        table.add_row("Image", "[yellow]no profile image set[/yellow]")
    else:
        table.add_row("Image", "[red]download failed[/red]")

    console.print()
    console.print(table)


async def run(targets: list[str]) -> int:
    logins: list[str] = []
    for target in targets:
        login = parse_login(target)
        if login is None:
            console.print(f"[red]Not a valid Twitch login: {target}[/red]")
        elif login not in logins:
            logins.append(login)
    if not logins:
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    failures = len(targets) - len(logins)
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        try:
            token = await get_token(client)
        except (RuntimeError, httpx.HTTPError) as exc:
            console.print(f"[red]Auth failed: {exc}[/red]")
            return 2
        client.headers.update({"Client-Id": CLIENT_ID, "Authorization": f"Bearer {token}"})
        users = await lookup(client, logins)
        # The image CDN is public; don't send the app token to it.
        client.headers.pop("Authorization")
        client.headers.pop("Client-Id")

        found = [users[l] for l in logins if l in users]
        for login in logins:
            if login not in users:
                console.print(f"[red]User not found: {login}[/red] (banned, renamed, or never existed)")
                failures += 1
        results = await asyncio.gather(*(download(client, u) for u in found), return_exceptions=True)

    for user, r in zip(found, results):
        if isinstance(r, BaseException):
            console.print(f"[red]{user['login']}: {type(r).__name__}[/red]")
            failures += 1
            continue
        render(r)
        if not r["path"]:
            failures += 1
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download Twitch profile pictures at the largest available size.",
        epilog="Twitch-pfp by 4swag",
    )
    parser.add_argument("targets", nargs="+", help="Twitch login, @login, or twitch.tv URL")
    args = parser.parse_args()

    if not CLIENT_ID or not CLIENT_SECRET:
        console.print(
            "[red]TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET missing. "
            "Register an app at https://dev.twitch.tv/console/apps and set them in .env.[/red]"
        )
        return 2

    return asyncio.run(run(args.targets))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        console.print("\nInterrupted.")
        sys.exit(130)
