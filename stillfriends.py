#!/usr/bin/env python3
"""StillFriends - who followed you, who left, and who never followed back.

Drives your own browser profile with Playwright (Edge or Chrome: same cookies,
same session, no re-login), reads the JSON the sites already load instead of
scraping the DOM, and keeps a full revision history of every pass.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tomllib
import webbrowser
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from playwright.sync_api import Error as PWError
from playwright.sync_api import Page, TimeoutError as PWTimeout, sync_playwright
from rich.box import ROUNDED
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

import report

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CONFIG = ROOT / "config.toml"

FOLLOWERS = "followers"
FOLLOWING = "following"

# Old Windows consoles default to cp1252 and choke on emoji and accents.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

console = Console()


# --------------------------------------------------------------------------- #
# Model
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Account:
    """One person on the other side of the list."""

    uid: str
    name: str = ""
    handle: str = ""
    url: str = ""
    # Solo se rellena al investigar a quien desaparecio de tus seguidos.
    status: str = ""

    @property
    def label(self) -> str:
        if self.handle and self.name:
            return f"{self.name} (@{self.handle})"
        return self.name or (f"@{self.handle}" if self.handle else self.uid)

    def as_dict(self) -> dict[str, str]:
        out = {"uid": self.uid, "name": self.name, "handle": self.handle, "url": self.url}
        if self.status:
            out["status"] = self.status
        return out

    @classmethod
    def from_dict(cls, raw: dict[str, str]) -> "Account":
        return cls(
            uid=str(raw.get("uid", "")),
            name=raw.get("name", ""),
            handle=raw.get("handle", ""),
            url=raw.get("url", ""),
            status=raw.get("status", ""),
        )


@dataclass(slots=True)
class Diff:
    added: list[Account] = field(default_factory=list)
    removed: list[Account] = field(default_factory=list)
    total: int = 0
    previous_total: int | None = None
    first_run: bool = False

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed)


def compare(previous: list[Account] | None, current: list[Account]) -> Diff:
    diff = Diff(total=len(current))
    if previous is None:
        diff.first_run = True
        return diff
    diff.previous_total = len(previous)
    before = {a.uid: a for a in previous}
    after = {a.uid: a for a in current}
    diff.added = sorted((after[k] for k in after.keys() - before.keys()), key=_sort_key)
    diff.removed = sorted((before[k] for k in before.keys() - after.keys()), key=_sort_key)
    return diff


def compare_legacy(previous: list[Account], current: list[Account]) -> Diff:
    """Compare against an imported *.txt, which stored bare names with no ids.

    Matching those strings against the new ids would mark every single person as
    gone and every single person as new, so match on the text instead: a name
    for Facebook, a username for Instagram.
    """
    diff = Diff(total=len(current), previous_total=len(previous))

    # Two different people can share a name, and these files have no ids to tell
    # them apart, so keep every entry and spend them one at a time. A plain dict
    # would collapse the repeats and report the extras as newcomers.
    pending: dict[str, list[Account]] = {}
    for account in previous:
        if account.name:
            pending.setdefault(account.name.casefold(), []).append(account)

    for account in current:
        for candidate in (account.handle, account.name):
            if candidate and pending.get(candidate.casefold()):
                pending[candidate.casefold()].pop()
                break
        else:
            diff.added.append(account)

    diff.removed = [a for group in pending.values() for a in group]
    diff.added.sort(key=_sort_key)
    diff.removed.sort(key=_sort_key)
    return diff


def not_following_back(followers: list[Account], following: list[Account]) -> list[Account]:
    """People you follow who do not follow you back."""
    follower_ids = {a.uid for a in followers}
    return sorted((a for a in following if a.uid not in follower_ids), key=_sort_key)


def _sort_key(account: Account) -> str:
    return account.label.casefold()


# --------------------------------------------------------------------------- #
# Storage: snapshot + revision history
# --------------------------------------------------------------------------- #


class Store:
    """A snapshot per list plus an append-only history of every pass."""

    def __init__(self, slug: str, kind: str = FOLLOWERS, root: Path = DATA) -> None:
        self.slug = slug
        self.kind = kind
        self.dir = root / slug
        self.snapshot = self.dir / f"{kind}.json"
        self.history = self.dir / f"{kind}_history.jsonl"

    @property
    def is_legacy(self) -> bool:
        """True when the only thing to compare against is an imported *.txt."""
        return not self.snapshot.exists() and bool(self._legacy_names())

    def load(self) -> list[Account] | None:
        if self.snapshot.exists():
            raw = json.loads(self.snapshot.read_text("utf-8"))
            return [Account.from_dict(a) for a in raw.get("accounts", [])]
        legacy = self._legacy_names()
        return [Account(uid=n, name=n) for n in legacy] if legacy else None

    def _legacy_names(self) -> list[str]:
        """Import the old FB.txt / IG.txt so the first pass is not a blank slate."""
        if self.kind != FOLLOWERS:
            return []
        # Los ficheros de la version vieja viven en archivo/, pero se siguen
        # buscando en la raiz por si alguien llega con ellos recien migrados.
        for old in (ROOT / "archivo" / "listas-v1" / f"{self.slug.upper()}.txt",
                    ROOT / f"{self.slug.upper()}.txt"):
            if old.exists():
                break
        else:
            return []
        raw = old.read_bytes()
        # The old script wrote with the Windows locale encoding, so accents come
        # as cp1252. Forcing utf-8 would turn "Andres" into "Andr?s" for good,
        # and a mangled name matches nobody: the person would show up as having
        # left and joined at the same time.
        for encoding in ("utf-8", "cp1252", "latin-1"):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            text = raw.decode("utf-8", errors="replace")
        return [line.strip() for line in text.splitlines() if line.strip()]

    def save(self, accounts: list[Account], diff: Diff, *, at: datetime) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.snapshot.write_text(
            json.dumps(
                {
                    "captured_at": at.isoformat(),
                    "kind": self.kind,
                    "count": len(accounts),
                    "accounts": [a.as_dict() for a in accounts],
                },
                ensure_ascii=False,
                indent=2,
            ),
            "utf-8",
        )
        entry = {
            "at": at.isoformat(),
            "kind": self.kind,
            "total": diff.total,
            "previous_total": diff.previous_total,
            "first_run": diff.first_run,
            "added": [a.as_dict() for a in diff.added],
            "removed": [a.as_dict() for a in diff.removed],
        }
        with self.history.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def revisions(self) -> list[dict[str, Any]]:
        if not self.history.exists():
            return []
        out = []
        for line in self.history.read_text("utf-8").splitlines():
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out


# --------------------------------------------------------------------------- #
# JSON helpers - the sites already ship us the data, we just read it
# --------------------------------------------------------------------------- #


def walk(node: Any) -> Iterator[dict]:
    """Yield every dict nested anywhere inside a JSON document, in document order."""
    queue = deque([node])
    while queue:
        item = queue.popleft()
        if isinstance(item, dict):
            yield item
            queue.extend(item.values())
        elif isinstance(item, list):
            queue.extend(item)


def loads_loose(body: str) -> list[Any]:
    """Parse JSON, NDJSON, or a response with an anti-JSON-hijack prefix."""
    body = body.lstrip()
    for prefix in ("for (;;);", "while(1);", ")]}'"):
        if body.startswith(prefix):
            body = body[len(prefix):].lstrip()
    try:
        return [json.loads(body)]
    except json.JSONDecodeError:
        pass
    docs = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            docs.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return docs


# --------------------------------------------------------------------------- #
# Platforms
# --------------------------------------------------------------------------- #


class CollectorError(RuntimeError):
    """The site said no: rate limit, logged out, endpoint moved."""


@dataclass(slots=True)
class Capture:
    """What one pass got, and whether we can trust it to be the whole list."""

    accounts: list[Account]
    expected: int | None = None     # what the site says the total is, if it tells us

    @property
    def complete(self) -> bool:
        # A short list would show everyone missing as "se fue", so treat any
        # meaningful shortfall as a failed pass rather than as real losses.
        if self.expected is None:
            return True
        return len(self.accounts) >= self.expected * 0.9


@dataclass(frozen=True)
class ListSpec:
    """How to reach one list (followers or following) on a platform."""

    noun: str                                     # "seguidores", "seguidos", "amigos"
    url_key: str = ""                             # config key holding the page URL
    matches: Callable[[str], bool] | None = None  # which responses carry people
    prepare: Callable[[Page], None] | None = None  # extra click to open the list
    # Preferred when the site has a paged API we can call directly: far more
    # exact than scrolling, and it tells us how many there should be.
    collect: Callable[..., Capture] | None = None
    # For scrolled lists: read the total off the page, so a short pass can be
    # spotted instead of being saved as a pile of people who never left.
    expected_from_page: Callable[[Page], int | None] = None


@dataclass(frozen=True)
class Platform:
    slug: str
    label: str
    emoji: str
    extract: Callable[[Any], list[Account]]       # JSON doc -> accounts
    lists: dict[str, ListSpec]
    # Averigua por que alguien desaparecio de tus seguidos.
    probe: Callable[..., list[Account]] | None = None

    def noun(self, kind: str) -> str:
        return self.lists[kind].noun

    @property
    def has_following(self) -> bool:
        return FOLLOWING in self.lists


def _ig_accounts(doc: Any) -> list[Account]:
    out = []
    for obj in walk(doc):
        username = obj.get("username")
        pk = obj.get("pk") or obj.get("pk_id") or obj.get("id")
        if not username or not pk or "full_name" not in obj:
            continue
        out.append(
            Account(
                uid=str(pk),
                name=obj.get("full_name") or "",
                handle=str(username),
                url=f"https://www.instagram.com/{username}/",
            )
        )
    return out


def _x_accounts(doc: Any) -> list[Account]:
    out = []
    for obj in walk(doc):
        if obj.get("__typename") != "User":
            continue
        rest_id = obj.get("rest_id") or obj.get("id_str")
        core = obj.get("core") or obj.get("legacy") or {}
        handle = core.get("screen_name")
        if not rest_id or not handle:
            continue
        out.append(
            Account(
                uid=str(rest_id),
                name=core.get("name", ""),
                handle=str(handle),
                url=f"https://x.com/{handle}",
            )
        )
    return out


FB_PROFILE = re.compile(r"^https?://(?:www|m|web)\.facebook\.com/(?:profile\.php\?id=(\d+)|([\w.]+))")


def _fb_accounts(doc: Any) -> list[Account]:
    out = []
    for obj in walk(doc):
        if obj.get("__typename") not in {"User", "Profile"}:
            continue
        uid, name = obj.get("id"), obj.get("name")
        if not uid or not name:
            continue
        url = obj.get("profile_url") or obj.get("url") or ""
        handle = ""
        if url and (m := FB_PROFILE.match(url)):
            handle = m.group(2) or ""
        out.append(Account(uid=str(uid), name=str(name), handle=handle, url=url))
    return out


# Instagram's own web app calls these endpoints with this app id. Going through
# them beats driving the UI: the profile DOM no longer even carries /followers/
# links, and the API states up front how many people there should be.
IG_APP_ID = "936619743392459"

IG_JS_PROFILE = """
async ([username, appId]) => {
  const r = await fetch(
    `/api/v1/users/web_profile_info/?username=${encodeURIComponent(username)}`,
    {headers: {'X-IG-App-ID': appId}, credentials: 'include'});
  if (!r.ok) return {error: r.status};
  const j = await r.json();
  const u = j && j.data && j.data.user;
  if (!u) return {error: 'sin-usuario'};
  return {
    id: u.id,
    followers: u.edge_followed_by ? u.edge_followed_by.count : null,
    following: u.edge_follow ? u.edge_follow.count : null,
  };
}
"""

IG_JS_PAGE = """
async ([uid, kind, maxId, appId]) => {
  const q = new URLSearchParams({count: '50'});
  if (maxId) q.set('max_id', maxId);
  const r = await fetch(`/api/v1/friendships/${uid}/${kind}/?${q}`,
    {headers: {'X-IG-App-ID': appId}, credentials: 'include'});
  if (!r.ok) return {error: r.status};
  const j = await r.json();
  return {users: j.users || [], next: j.next_max_id || null};
}
"""


# Estados de una cuenta que desaparecio de tus seguidos.
VIVA = "viva"
DESAPARECIDA = "desaparecida"

IG_JS_USER_INFO = """
async ([pk, appId]) => {
  const r = await fetch(`/api/v1/users/${pk}/info/`,
    {headers: {'X-IG-App-ID': appId}, credentials: 'include'});
  if (r.status === 404) return {estado: 'desaparecida'};
  if (!r.ok) return {estado: '', http: r.status};
  const j = await r.json();
  return (j && j.user) ? {estado: 'viva', privada: !!j.user.is_private}
                       : {estado: 'desaparecida'};
}
"""


def _ig_probe(page: Page, accounts: list[Account], cfg: "Config",
              status: Callable[[str], None]) -> list[Account]:
    """Why did these accounts fall off your following list?

    Instagram answers 404 the same way whether the account was deleted, went
    inactive, or blocked you - from this side those three are indistinguishable,
    so they get reported together rather than guessed apart.
    """
    out = []
    for i, account in enumerate(accounts, 1):
        status(f"investigando {i} de {len(accounts)}")
        try:
            res = page.evaluate(IG_JS_USER_INFO, [account.uid, IG_APP_ID])
        except PWError:
            out.append(account)
            continue
        out.append(replace(account, status=res.get("estado", "")))
        page.wait_for_timeout(max(cfg.scroll_pause_ms // 2, 400))
    return out


def _ig_complain(code: Any) -> str:
    if code == 429:
        return ("Instagram esta limitando las peticiones (429).\n\n"
                "Espera unos minutos y reintenta. Si pasa a menudo, sube\n"
                "scroll_pause_ms en [tuning].")
    if code in (401, 403):
        return ("Instagram respondio 'no autorizado'. Vuelve a iniciar sesion:\n\n"
                "    python stillfriends.py login -p ig")
    return f"Instagram respondio con un error inesperado: {code}"


def _ig_username(cfg: "Config") -> str:
    return cfg.urls.get("instagram_profile_url", "").rstrip("/").rsplit("/", 1)[-1]


def _ig_collect(kind: str) -> Callable[..., Capture]:
    def collect(page: Page, cfg: "Config", status: Callable[[str], None]) -> Capture:
        status("abriendo Instagram")
        page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(1500)

        # Your own id is sitting in the session cookie. Asking the profile
        # endpoint for it would be silly, and that endpoint is the first one
        # Instagram rate-limits.
        uid = next(
            (c["value"] for c in page.context.cookies() if c["name"] == "ds_user_id"),
            None,
        )
        if not uid:
            raise CollectorError(
                "No hay sesion de Instagram en el perfil de StillFriends.\n\n"
                "    python stillfriends.py login -p ig"
            )

        # Only for the "how many should there be" check. It gets rate-limited
        # far more eagerly than the lists themselves, so it must not be fatal.
        expected = None
        username = _ig_username(cfg)
        if username:
            info = page.evaluate(IG_JS_PROFILE, [username, IG_APP_ID])
            if "error" in info:
                status("sin total de referencia (Instagram limito esa consulta)")
            else:
                expected = info.get(kind)

        found: dict[str, Account] = {}
        next_id = None
        while True:
            res = page.evaluate(IG_JS_PAGE, [uid, kind, next_id, IG_APP_ID])
            if "error" in res:
                if not found:
                    raise CollectorError(_ig_complain(res["error"]))
                break  # partial: the completeness check decides what that means
            for account in _ig_accounts({"users": res["users"]}):
                found.setdefault(account.uid, account)
            status(f"{len(found)}" + (f" de {expected}" if expected else ""))
            next_id = res["next"]
            if not next_id:
                break
            page.wait_for_timeout(cfg.scroll_pause_ms)

        return Capture(sorted(found.values(), key=_sort_key), expected)

    return collect


def _x_matches(operation: str) -> Callable[[str], bool]:
    def matches(url: str) -> bool:
        return "/i/api/graphql/" in url and operation in url

    return matches


# The profile header reads "62 amigos" / "62 friends". Taking that as the target
# is what turns a half-scrolled pass into a warning instead of 43 fake losses.
FB_COUNT = re.compile(r"([\d][\d.,  ]*)\s*(?:amigos?|friends?)\b", re.IGNORECASE)


def _fb_expected(page: Page) -> int | None:
    try:
        text = page.evaluate("document.body.innerText.slice(0, 4000)")
    except PWError:
        return None
    match = FB_COUNT.search(text or "")
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(1))
    return int(digits) if digits else None


PLATFORMS: dict[str, Platform] = {
    "fb": Platform(
        slug="fb",
        label="Facebook",
        emoji="\U0001f465",
        extract=_fb_accounts,
        lists={
            # On Facebook friendship is mutual, so there is no "following" list.
            FOLLOWERS: ListSpec(
                url_key="facebook_friends_url",
                matches=lambda u: "/api/graphql" in u,
                noun="amigos",
                expected_from_page=_fb_expected,
            ),
        },
    ),
    "ig": Platform(
        slug="ig",
        label="Instagram",
        emoji="\U0001f4f8",
        extract=_ig_accounts,
        probe=_ig_probe,
        lists={
            FOLLOWERS: ListSpec(noun="seguidores", collect=_ig_collect(FOLLOWERS)),
            FOLLOWING: ListSpec(noun="seguidos", collect=_ig_collect(FOLLOWING)),
        },
    ),
    "x": Platform(
        slug="x",
        label="X / Twitter",
        emoji="\U0001f426",
        extract=_x_accounts,
        lists={
            FOLLOWERS: ListSpec(
                url_key="x_followers_url",
                matches=_x_matches("Followers"),
                noun="seguidores",
            ),
            FOLLOWING: ListSpec(
                url_key="x_following_url",
                matches=_x_matches("Following"),
                noun="seguidos",
            ),
        },
    ),
}


# --------------------------------------------------------------------------- #
# Browser
# --------------------------------------------------------------------------- #


# Every Chromium-based browser Playwright can drive, with where each one keeps
# its profiles and what its executable is called (for the CDP hint).
@dataclass(frozen=True)
class BrowserFlavour:
    label: str
    exe: str
    dirs: dict[str, str]                      # platform -> default "User Data" folder
    exe_paths: dict[str, tuple[str, ...]]     # platform -> where the binary lives


BROWSERS: dict[str, BrowserFlavour] = {
    "msedge": BrowserFlavour(
        "Microsoft Edge", "msedge.exe",
        {
            "win32": r"%LOCALAPPDATA%\Microsoft\Edge\User Data",
            "darwin": "~/Library/Application Support/Microsoft Edge",
            "linux": "~/.config/microsoft-edge",
        },
        {
            "win32": (
                r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe",
                r"%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe",
            ),
            "darwin": ("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",),
            "linux": ("/usr/bin/microsoft-edge", "/usr/bin/microsoft-edge-stable"),
        },
    ),
    "chrome": BrowserFlavour(
        "Google Chrome", "chrome.exe",
        {
            "win32": r"%LOCALAPPDATA%\Google\Chrome\User Data",
            "darwin": "~/Library/Application Support/Google/Chrome",
            "linux": "~/.config/google-chrome",
        },
        {
            "win32": (
                r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe",
                r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe",
                r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
            ),
            "darwin": ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",),
            "linux": ("/usr/bin/google-chrome", "/usr/bin/google-chrome-stable"),
        },
    ),
    "chrome-beta": BrowserFlavour(
        "Chrome Beta", "chrome.exe",
        {
            "win32": r"%LOCALAPPDATA%\Google\Chrome Beta\User Data",
            "darwin": "~/Library/Application Support/Google/Chrome Beta",
            "linux": "~/.config/google-chrome-beta",
        },
        {
            "win32": (r"%PROGRAMFILES%\Google\Chrome Beta\Application\chrome.exe",),
            "darwin": ("/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta",),
            "linux": ("/usr/bin/google-chrome-beta",),
        },
    ),
    "msedge-beta": BrowserFlavour(
        "Edge Beta", "msedge.exe",
        {
            "win32": r"%LOCALAPPDATA%\Microsoft\Edge Beta\User Data",
            "darwin": "~/Library/Application Support/Microsoft Edge Beta",
            "linux": "~/.config/microsoft-edge-beta",
        },
        {
            "win32": (r"%PROGRAMFILES(X86)%\Microsoft\Edge Beta\Application\msedge.exe",),
            "darwin": ("/Applications/Microsoft Edge Beta.app/Contents/MacOS/Microsoft Edge Beta",),
            "linux": ("/usr/bin/microsoft-edge-beta",),
        },
    ),
}

DEFAULT_CHANNEL = "msedge"


DEFAULT_CDP_URL = "http://localhost:9222"


def default_profile_dir(channel: str) -> Path:
    """Where StillFriends keeps its own browser profile.

    Deliberately outside the project folder: this repo often lives in OneDrive,
    and syncing a live browser profile would be a bad time.
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", "~/AppData/Local"))
    elif sys.platform == "darwin":
        base = Path("~/Library/Application Support")
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", "~/.local/share"))
    return (base / "StillFriends" / f"{channel}-profile").expanduser()


@dataclass
class Config:
    channel: str
    profile_dir: Path
    cdp_url: str | None
    urls: dict[str, str]
    platforms: list[str] = field(default_factory=list)
    scroll_pause_ms: int = 900
    idle_rounds: int = 4
    max_scrolls: int = 600

    @property
    def flavour(self) -> BrowserFlavour:
        return BROWSERS[self.channel]

    @classmethod
    def load(cls, path: Path = CONFIG) -> "Config":
        if not path.exists():
            raise SystemExit(
                f"Falta {path.name}. Copia config.example.toml a config.toml y rellena tus datos."
            )
        raw = tomllib.loads(path.read_text("utf-8"))
        browser = raw.get("browser", {})
        tuning = raw.get("tuning", {})

        channel = browser.get("channel", DEFAULT_CHANNEL)
        if channel not in BROWSERS:
            raise SystemExit(
                f'channel = "{channel}" no vale. Opciones: {", ".join(sorted(BROWSERS))}.'
            )
        raw_dir = browser.get("profile_dir", "")
        profile_dir = (
            Path(os.path.expandvars(raw_dir)).expanduser() if raw_dir
            else default_profile_dir(channel)
        )

        return cls(
            channel=channel,
            profile_dir=profile_dir,
            cdp_url=browser.get("cdp_url") or None,
            urls=raw.get("urls", {}),
            platforms=[p for p in raw.get("platforms", []) if p in PLATFORMS],
            scroll_pause_ms=tuning.get("scroll_pause_ms", 900),
            idle_rounds=tuning.get("idle_rounds", 4),
            max_scrolls=tuning.get("max_scrolls", 600),
        )


# --------------------------------------------------------------------------- #
# Browser session
# --------------------------------------------------------------------------- #
#
# Why a profile of our own, and not the one you browse with every day:
#
# Since Chrome 136 / Edge 136 (a 2025 anti-malware change), the browser SILENTLY
# IGNORES --remote-debugging-port whenever --user-data-dir points at the default
# profile. No error, the port simply never opens. So driving the browser you
# already have open is not something the script can arrange any more.
#
# The way out is better anyway: StillFriends keeps its own profile, logged into
# the three sites once and for good. Your everyday browser is never touched, so
# it can stay open while a check runs.


def cdp_alive(url: str, timeout: float = 1.5) -> bool:
    """Is something already listening on the debugging port?"""
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/json/version", timeout=timeout) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


@contextmanager
def open_browser(cfg: Config, headless: bool = False):
    """Open StillFriends' own browser profile, with its sessions already live."""
    flavour = cfg.flavour
    with sync_playwright() as pw:
        # Advanced: attach to a browser you started yourself with the port open.
        if cfg.cdp_url:
            if not cdp_alive(cfg.cdp_url):
                raise SystemExit(
                    f"Nada escucha en {cfg.cdp_url}.\n\n"
                    "Arranca el navegador con --remote-debugging-port y un\n"
                    "--user-data-dir que NO sea tu perfil normal (con el perfil\n"
                    "por defecto el puerto no abre nunca), o quita cdp_url de\n"
                    "config.toml para que StillFriends use su propio perfil."
                )
            browser = pw.chromium.connect_over_cdp(cfg.cdp_url)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            try:
                yield context
            finally:
                pass  # only drop the connection; the browser is not ours to close
            return

        cfg.profile_dir.mkdir(parents=True, exist_ok=True)
        try:
            context = pw.chromium.launch_persistent_context(
                user_data_dir=str(cfg.profile_dir),
                channel=cfg.channel,
                headless=headless,
                args=["--disable-blink-features=AutomationControlled", "--no-first-run"],
                viewport={"width": 1280, "height": 900},
            )
        except PWError as exc:
            raise SystemExit(
                f"No se pudo abrir {flavour.label}.\n\n"
                f'Comprueba que esta instalado y que channel = "{cfg.channel}"\n'
                "es el correcto en config.toml.\n\n"
                f"Detalle: {exc}"
            ) from exc
        try:
            yield context
        finally:
            context.close()


# Scrolls the innermost scrollable container (the followers modal) when there is
# one, and the window itself otherwise.
SCROLL_JS = """
() => {
  const candidates = [...document.querySelectorAll('div, ul, section')].filter(el => {
    const s = getComputedStyle(el);
    return /(auto|scroll)/.test(s.overflowY)
        && el.scrollHeight > el.clientHeight + 100
        && el.clientHeight > 150;
  });
  const target = candidates.at(-1);
  if (target) { target.scrollTop = target.scrollHeight; }
  window.scrollTo(0, document.body.scrollHeight);
}
"""


def harvest(
    context,
    platform: Platform,
    kind: str,
    cfg: Config,
    *,
    live: Live | None = None,
) -> Capture:
    """Get one list, either through the site's own API or by scrolling it."""
    spec = platform.lists[kind]
    found: dict[str, Account] = {}
    page = context.new_page()

    def on_response(response) -> None:
        if spec.matches is None or not spec.matches(response.url):
            return
        try:
            body = response.text()
        except PWError:
            return  # response already gone, or not text
        for doc in loads_loose(body):
            for account in platform.extract(doc):
                found.setdefault(account.uid, account)

    if spec.matches is not None:
        page.on("response", on_response)

    def status(note: str) -> None:
        if live is None:
            return
        live.update(
            Panel(
                Text.assemble(
                    (f"{platform.emoji}  {platform.label}", "bold"),
                    ("  |  ", "dim"),
                    (str(len(found)), "bold cyan"),
                    (f" {spec.noun}", "cyan"),
                    ("  |  ", "dim"),
                    (note, "dim"),
                ),
                box=ROUNDED,
                border_style="cyan",
                padding=(0, 1),
            )
        )

    try:
        if spec.collect is not None:
            return spec.collect(page, cfg, status)

        url = cfg.urls.get(spec.url_key, "")
        if not url:
            raise SystemExit(f"Falta '{spec.url_key}' en la seccion [urls] de config.toml.")

        status("abriendo la pagina")
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(2500)

        if spec.prepare:
            status(f"abriendo la lista de {spec.noun}")
            spec.prepare(page)
            page.wait_for_timeout(2000)

        expected = spec.expected_from_page(page) if spec.expected_from_page else None

        idle = 0
        for i in range(cfg.max_scrolls):
            before = len(found)
            try:
                page.evaluate(SCROLL_JS)
            except PWError:
                break
            page.wait_for_timeout(cfg.scroll_pause_ms)
            if len(found) == before:
                idle += 1
                status(f"esperando mas resultados ({idle}/{cfg.idle_rounds})")
                if idle >= cfg.idle_rounds:
                    break
            else:
                idle = 0
                status(f"scroll {i + 1}" + (f" - {len(found)} de {expected}" if expected else ""))
            if expected and len(found) >= expected:
                break

        status("listo")
    finally:
        page.close()

    return Capture(sorted(found.values(), key=_sort_key), expected)


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #


def banner() -> Panel:
    return Panel(
        Text("StillFriends", style="bold magenta", justify="center"),
        subtitle=Text("quien se queda, quien se va, quien no te sigue", style="dim"),
        box=ROUNDED,
        border_style="magenta",
    )


MOTIVOS = {
    DESAPARECIDA: ("cuenta borrada, inactiva o te bloqueo", "yellow"),
    VIVA: ("la cuenta sigue ahi: la dejaste de seguir", "dim"),
}


def people_table(title: str, accounts: list[Account], style: str, mark: str) -> Table:
    table = Table(box=ROUNDED, border_style=style, title=title or None,
                  title_style=f"bold {style}", min_width=min(48, len(title) + 8))
    table.add_column(mark, style=style, width=2, justify="center")
    table.add_column("Nombre", style="white", overflow="fold")
    table.add_column("Usuario", style="dim", overflow="fold")
    con_motivo = any(a.status in MOTIVOS for a in accounts)
    if con_motivo:
        table.add_column("Que paso", overflow="fold")
    for account in accounts:
        fila = [mark, account.name or "-", f"@{account.handle}" if account.handle else "-"]
        if con_motivo:
            texto, color = MOTIVOS.get(account.status, ("?", "dim"))
            fila.append(Text(texto, style=color))
        table.add_row(*fila)
    return table


def _labels(platform: Platform, kind: str) -> tuple[str, str]:
    """Que significa un alta y una baja en cada lista."""
    if kind == FOLLOWING:
        return "Empezaste a seguir", "Dejaste de seguir"
    if platform.slug == "fb":
        return "Nuevos amigos", "Ya no son amigos"
    return "Nuevos seguidores", "Se fueron"


def _headline(platform: Platform, kind: str, diff: Diff, at: datetime) -> Text:
    head = Text()
    head.append(f"{platform.emoji}  {platform.label}", style="bold")
    head.append(f"   {diff.total} {platform.noun(kind)}", style="bold cyan")
    if diff.previous_total is not None:
        delta = diff.total - diff.previous_total
        head.append(f"  ({delta:+d})", style="green" if delta >= 0 else "red")
    head.append(f"   {at.astimezone().strftime('%Y-%m-%d %H:%M')}", style="dim")
    return head


def render_pass(
    platform: Platform,
    diffs: dict[str, Diff],
    unrequited: list[Account] | None,
    *,
    at: datetime,
) -> Panel:
    """One panel per platform: what changed, plus who never followed back."""
    parts: list[Any] = []
    changed = False

    for kind in (FOLLOWERS, FOLLOWING):
        diff = diffs.get(kind)
        if diff is None:
            continue
        if parts:
            parts.append(Text())
        parts.append(_headline(platform, kind, diff, at))
        if diff.first_run:
            parts.append(Text("Primera pasada: guardada como punto de partida.", style="yellow"))
        elif not diff.changed:
            parts.append(Text("Sin cambios.", style="dim green"))
        else:
            changed = True
            alta, baja = _labels(platform, kind)
            if diff.added:
                parts.append(people_table(f"{alta} ({len(diff.added)})", diff.added, "green", "+"))
            if diff.removed:
                parts.append(people_table(f"{baja} ({len(diff.removed)})", diff.removed, "red", "-"))

    if unrequited is not None:
        parts.append(Text())
        if unrequited:
            parts.append(
                people_table(
                    f"No te siguen de vuelta ({len(unrequited)})", unrequited, "yellow", "!"
                )
            )
        else:
            parts.append(Text("Todos los que sigues te siguen de vuelta.", style="dim green"))

    first = any(d.first_run for d in diffs.values())
    border = "yellow" if first else ("magenta" if changed else "green")
    return Panel(Group(*parts), box=ROUNDED, border_style=border, padding=(1, 2))


def render_history(platform: Platform, kind: str, revisions: list[dict], limit: int, detail: bool) -> Panel:
    title = f"{platform.emoji}  {platform.label} - historial de {platform.noun(kind)}"
    if not revisions:
        return Panel(
            Text("Sin historial todavia.", style="dim"),
            title=title,
            title_align="left",
            box=ROUNDED,
            border_style="dim",
        )

    table = Table(box=ROUNDED, border_style="blue")
    table.add_column("Fecha", style="cyan", no_wrap=True)
    table.add_column("Total", justify="right", style="bold")
    table.add_column("Cambio", justify="right")
    table.add_column("Nuevos", justify="right", style="green")
    table.add_column("Se fueron", justify="right", style="red")
    if detail:
        table.add_column("Detalle", style="dim", overflow="fold")

    for rev in revisions[-limit:]:
        at = datetime.fromisoformat(rev["at"]).astimezone().strftime("%Y-%m-%d %H:%M")
        added, removed = rev.get("added", []), rev.get("removed", [])
        prev = rev.get("previous_total")
        delta = "-" if prev is None else f"{rev['total'] - prev:+d}"
        row: list[Any] = [at, str(rev["total"]), delta, str(len(added)), str(len(removed))]
        if detail:
            names = Text()
            for raw in added:
                names.append(f"+{Account.from_dict(raw).label}  ", style="green")
            for raw in removed:
                names.append(f"-{Account.from_dict(raw).label}  ", style="red")
            row.append(names if names.plain else Text("-", style="dim"))
        table.add_row(*row)

    return Panel(table, title=title, title_align="left", box=ROUNDED, border_style="blue", padding=(0, 1))


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #


def _warn(platform: Platform, kind: str, message: str) -> None:
    console.print(
        Panel(
            Text(message, style="yellow"),
            title=f"{platform.emoji}  {platform.label} - {platform.noun(kind)}",
            title_align="left",
            box=ROUNDED,
            border_style="yellow",
            padding=(1, 2),
        )
    )


def _warn_empty(platform: Platform, kind: str) -> None:
    _warn(
        platform, kind,
        f"No se capturo ningun dato de {platform.noun(kind)}.\n\n"
        "Lo mas probable es que el perfil de StillFriends no tenga la\n"
        "sesion iniciada. Corre esto una vez:\n\n"
        f"    python stillfriends.py login -p {platform.slug}\n\n"
        "Si ya la iniciaste, revisa la URL en config.toml.",
    )


def cmd_check(args: argparse.Namespace) -> int:
    cfg = Config.load()
    console.print(banner())

    checked = 0
    with open_browser(cfg, headless=args.headless) as context:
        for slug in args.platforms:
            platform = PLATFORMS[slug]
            kinds = [FOLLOWERS]
            if platform.has_following and not args.no_following:
                kinds.append(FOLLOWING)

            captured: dict[str, list[Account]] = {}
            diffs: dict[str, Diff] = {}
            at = datetime.now(timezone.utc)

            for kind in kinds:
                with Live(console=console, refresh_per_second=8, transient=True) as live:
                    try:
                        capture = harvest(context, platform, kind, cfg, live=live)
                    except PWTimeout:
                        capture = Capture([])
                    except CollectorError as exc:
                        live.stop()
                        _warn(platform, kind, str(exc))
                        continue

                if not capture.accounts:
                    _warn_empty(platform, kind)
                    continue
                if not capture.complete and not args.force:
                    _warn(
                        platform, kind,
                        f"Solo se capturaron {len(capture.accounts)} de "
                        f"{capture.expected} {platform.noun(kind)}.\n\n"
                        "No lo guardo: una lista corta haria que los que faltan\n"
                        "aparecieran manana como bajas falsas. Reintenta en un\n"
                        "rato, o usa --force si de verdad quieres guardarla.",
                    )
                    continue

                store = Store(platform.slug, kind)
                previous = store.load()
                diff = (
                    compare_legacy(previous, capture.accounts)
                    if store.is_legacy and previous
                    else compare(previous, capture.accounts)
                )

                # Alguien que cae de tus seguidos no siempre es cosa tuya: la
                # cuenta puede haberse ido, o haberte bloqueado. Preguntamos.
                if kind == FOLLOWING and diff.removed and platform.probe:
                    page = context.new_page()
                    try:
                        with Live(console=console, refresh_per_second=8, transient=True) as live:
                            def nota(texto: str, _p=platform) -> None:
                                live.update(Panel(
                                    Text.assemble(
                                        (f"{_p.emoji}  {_p.label}", "bold"),
                                        ("  |  por que desaparecieron  |  ", "dim"),
                                        (texto, "dim"),
                                    ),
                                    box=ROUNDED, border_style="cyan", padding=(0, 1)))

                            page.goto("https://www.instagram.com/",
                                      wait_until="domcontentloaded", timeout=60_000)
                            page.wait_for_timeout(1500)
                            diff.removed = platform.probe(page, diff.removed, cfg, nota)
                    except PWError:
                        pass  # sin motivo es peor que nada, pero no vale romper la pasada
                    finally:
                        page.close()

                diffs[kind] = diff
                captured[kind] = capture.accounts
                if not args.dry_run:
                    store.save(capture.accounts, diffs[kind], at=at)

            if not diffs:
                continue

            unrequited = None
            if FOLLOWING in captured:
                unrequited = not_following_back(
                    captured.get(FOLLOWERS, Store(platform.slug, FOLLOWERS).load() or []),
                    captured[FOLLOWING],
                )
            console.print(render_pass(platform, diffs, unrequited, at=at))
            checked += 1

    if args.dry_run and checked:
        console.print("[yellow]--dry-run: no se guardo nada.[/]")
    elif checked:
        path = write_report()
        if path:
            console.print(f"[dim]Informe actualizado:[/] {path}")
            if args.html:
                webbrowser.open(path.as_uri())
    return 0 if checked else 1


REPORT = DATA / "informe.html"


def _report_payload() -> dict[str, Any]:
    """Everything on disk, shaped for the HTML page."""
    platforms = []
    for slug, platform in PLATFORMS.items():
        lists = []
        snapshots: dict[str, list[Account]] = {}
        for kind in (FOLLOWERS, FOLLOWING):
            if kind not in platform.lists:
                continue
            store = Store(slug, kind)
            if not store.snapshot.exists():
                continue
            accounts = store.load() or []
            snapshots[kind] = accounts
            revisions = store.revisions()
            last = revisions[-1] if revisions else {}
            lists.append({
                "kind": kind,
                "noun": platform.noun(kind),
                "total": len(accounts),
                "previous_total": last.get("previous_total"),
                "added": [Account.from_dict(a).as_dict() for a in last.get("added", [])],
                "removed": [Account.from_dict(a).as_dict() for a in last.get("removed", [])],
                "accounts": [a.as_dict() for a in accounts],
                "history": revisions,
            })
        if not lists:
            continue

        # Una pasada toca las dos listas a la vez y las sella con la misma hora,
        # asi que se juntan para contar cada revision como un solo momento.
        por_momento: dict[str, list[dict[str, Any]]] = {}
        for entry_list in lists:
            for rev in entry_list["history"]:
                por_momento.setdefault(rev["at"], []).append({
                    "kind": entry_list["kind"],
                    "noun": entry_list["noun"],
                    "total": rev.get("total", 0),
                    "previous_total": rev.get("previous_total"),
                    "added": rev.get("added", []),
                    "removed": rev.get("removed", []),
                })
        timeline = [
            {"at": at, "changes": cambios}
            for at, cambios in sorted(por_momento.items(), reverse=True)  # lo reciente primero
        ]

        entry: dict[str, Any] = {
            "slug": slug,
            "label": platform.label,
            "emoji": platform.emoji,
            "lists": lists,
            "timeline": timeline,
        }
        if FOLLOWING in snapshots and FOLLOWERS in snapshots:
            missing = not_following_back(snapshots[FOLLOWERS], snapshots[FOLLOWING])
            entry["unrequited"] = [a.as_dict() for a in missing]
            entry["following_total"] = len(snapshots[FOLLOWING])
        platforms.append(entry)

    return {"generated": datetime.now(timezone.utc).isoformat(), "platforms": platforms}


def write_report() -> Path | None:
    payload = _report_payload()
    if not payload["platforms"]:
        return None
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(report.build(payload), "utf-8")
    return REPORT


def cmd_report(args: argparse.Namespace) -> int:
    path = write_report()
    if path is None:
        console.print("[yellow]Todavia no hay datos. Corre[/] [bold]stillfriends check[/] [yellow]primero.[/]")
        return 1
    console.print(f"[green]Informe listo:[/] {path}")
    if not args.no_open:
        webbrowser.open(path.as_uri())
    return 0


def cmd_login(args: argparse.Namespace) -> int:
    """Open the sites in StillFriends' own profile so you can log in once."""
    cfg = Config.load()
    console.print(banner())
    console.print(
        Panel(
            Text.assemble(
                ("StillFriends usa un perfil de navegador propio, aparte del que\n"
                 "usas a diario. Por eso puedes dejar tu Edge abierto mientras\n"
                 "corre una revision.\n\n", ""),
                ("Voy a abrir una pestana por red. Inicia sesion en cada una y\n"
                 "vuelve aqui. La sesion queda guardada para siempre en:\n", ""),
                (f"{cfg.profile_dir}\n", "dim"),
            ),
            title="Iniciar sesion, una sola vez",
            title_align="left",
            box=ROUNDED,
            border_style="cyan",
            padding=(1, 2),
        )
    )

    with open_browser(cfg, headless=False) as context:
        opened = []
        for slug in args.platforms:
            platform = PLATFORMS[slug]
            url = cfg.urls.get(platform.lists[FOLLOWERS].url_key, "")
            if not url:
                continue
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            opened.append(platform.label)
        if not opened:
            console.print("[yellow]No hay URLs configuradas en [urls].[/]")
            return 1
        console.print(f"Abiertas: [bold]{', '.join(opened)}[/]\n")
        console.input("[bold cyan]Cuando hayas iniciado sesion en todas, pulsa Enter...[/] ")

    console.print("\n[green]Listo. Ya puedes correr[/] [bold]stillfriends check[/].")
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    console.print(banner())
    for slug in args.platforms:
        platform = PLATFORMS[slug]
        for kind in args.kinds:
            if kind not in platform.lists:
                continue
            console.print(
                render_history(
                    platform, kind, Store(slug, kind).revisions(), args.limit, args.detail
                )
            )
    return 0


def cmd_unrequited(args: argparse.Namespace) -> int:
    """Who you follow that does not follow you back, from the stored snapshots."""
    console.print(banner())
    shown = 0
    for slug in args.platforms:
        platform = PLATFORMS[slug]
        if not platform.has_following:
            continue
        followers = Store(slug, FOLLOWERS).load()
        following = Store(slug, FOLLOWING).load()
        if followers is None or following is None:
            console.print(
                f"[yellow]{platform.label}: faltan datos. Corre "
                f"[bold]stillfriends check -p {slug}[/] primero.[/]"
            )
            continue
        missing = not_following_back(followers, following)
        title = f"{platform.emoji}  {platform.label} - no te siguen de vuelta ({len(missing)} de {len(following)})"
        if missing:
            console.print(Panel(people_table("", missing, "yellow", "!"), title=title,
                                title_align="left", box=ROUNDED, border_style="yellow"))
        else:
            console.print(Panel(Text("Todos te siguen de vuelta.", style="green"), title=title,
                                title_align="left", box=ROUNDED, border_style="green"))
        shown += 1
    return 0 if shown else 1


def cmd_list(args: argparse.Namespace) -> int:
    for slug in args.platforms:
        platform = PLATFORMS[slug]
        for kind in args.kinds:
            if kind not in platform.lists:
                continue
            accounts = Store(slug, kind).load() or []
            table = Table(
                box=ROUNDED,
                border_style="cyan",
                title=f"{platform.emoji}  {platform.label} - {len(accounts)} {platform.noun(kind)}",
            )
            table.add_column("#", style="dim", justify="right")
            table.add_column("Nombre")
            table.add_column("Usuario", style="dim")
            for i, account in enumerate(accounts, 1):
                table.add_row(str(i), account.name or "-",
                              f"@{account.handle}" if account.handle else "-")
            console.print(table)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="stillfriends",
        description="Quien te sigue, quien te dejo de seguir y a quien sigues sin respuesta.",
    )
    sub = parser.add_subparsers(dest="command")

    def add_platforms(p: argparse.ArgumentParser) -> None:
        p.add_argument("-p", "--platform", dest="platforms", action="append",
                       choices=sorted(PLATFORMS), help="repetible; por defecto todas")

    def add_kinds(p: argparse.ArgumentParser) -> None:
        p.add_argument("-k", "--kind", dest="kinds", action="append",
                       choices=[FOLLOWERS, FOLLOWING], help="repetible; por defecto ambas")

    check = sub.add_parser("check", help="hacer una pasada y comparar (por defecto)")
    add_platforms(check)
    check.add_argument("--no-following", action="store_true",
                       help="solo seguidores; mas rapido, sin la seccion de no te siguen")
    check.add_argument("--headless", action="store_true", help="sin ventana visible")
    check.add_argument("--dry-run", action="store_true", help="mostrar sin guardar")
    check.add_argument("--force", action="store_true",
                       help="guardar aunque la lista salga incompleta")
    check.add_argument("--html", action="store_true",
                       help="abrir el informe HTML al terminar")
    check.set_defaults(func=cmd_check)

    informe = sub.add_parser("report", aliases=["html"], help="abrir el informe HTML")
    informe.add_argument("--no-open", action="store_true", help="solo generarlo")
    informe.set_defaults(func=cmd_report)

    entrar = sub.add_parser("login", help="iniciar sesion en el perfil de StillFriends")
    add_platforms(entrar)
    entrar.set_defaults(func=cmd_login)

    hist = sub.add_parser("history", help="historial de revisiones")
    add_platforms(hist)
    add_kinds(hist)
    hist.add_argument("-n", "--limit", type=int, default=20, help="ultimas N revisiones")
    hist.add_argument("-d", "--detail", action="store_true", help="incluir nombres")
    hist.set_defaults(func=cmd_history)

    unreq = sub.add_parser("unrequited", aliases=["nofollow"],
                           help="seguidos que no te siguen de vuelta")
    add_platforms(unreq)
    unreq.set_defaults(func=cmd_unrequited)

    lst = sub.add_parser("list", help="mostrar las listas guardadas")
    add_platforms(lst)
    add_kinds(lst)
    lst.set_defaults(func=cmd_list)

    args = parser.parse_args(argv)
    if args.command is None:
        args = parser.parse_args(list(argv or []) + ["check"])
    if hasattr(args, "platforms") and not args.platforms:
        try:
            args.platforms = Config.load().platforms or sorted(PLATFORMS)
        except SystemExit:
            args.platforms = sorted(PLATFORMS)
    if not getattr(args, "kinds", None):
        args.kinds = [FOLLOWERS, FOLLOWING]

    try:
        return args.func(args)
    except KeyboardInterrupt:
        console.print("\n[dim]Cancelado.[/]")
        return 130


if __name__ == "__main__":
    sys.exit(main())
