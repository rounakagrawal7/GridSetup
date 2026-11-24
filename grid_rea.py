"""Authorized web reverse-engineering teardowns for GRID.

This module is deliberately passive: it fetches public assets, captures a page
with REA's Playwright scenario when available, and writes a standard report. It
does not exploit, bypass authentication, or call discovered APIs.

Authorization must come from one of:
  * an explicit ``authorized <url>`` prefix,
  * ``security.authorized_targets`` in config.json,
  * a private/lab host (localhost, .local, .test, RFC1918).

The optional REA backend is the MIT-licensed ``rea-agents`` package:
https://github.com/morluto/rea
"""

from __future__ import annotations

import base64
import ipaddress
import json
import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

HERE = Path(__file__).resolve().parent
REFS_DIR = HERE / "refs" / "rea"
DEFAULT_REA_VERSION = "6.10.1"
USER_AGENT = "GRID-REA/1.0 (authorized passive teardown)"
MAX_PAGE_BYTES = 3_000_000
MAX_SCRIPT_BYTES = 600_000
MAX_SCRIPTS = 10
MAX_ENDPOINTS = 200

SECURITY_HEADERS = [
    "content-security-policy",
    "strict-transport-security",
    "x-frame-options",
    "x-content-type-options",
    "referrer-policy",
    "permissions-policy",
    "cross-origin-opener-policy",
    "cross-origin-resource-policy",
]

SECRET_PATTERNS = [
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("stripe_secret", re.compile(r"\bsk_(?:live|test)_[0-9A-Za-z]{16,}\b")),
    ("github_token", re.compile(r"\bghp_[0-9A-Za-z]{30,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{20,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
]

ENDPOINT_PATTERNS = [
    re.compile(r"""fetch\(\s*["']([^"']+)["']"""),
    re.compile(r"""axios\.(?:get|post|put|patch|delete)\(\s*["']([^"']+)["']"""),
    re.compile(r"""["'](/(?:api|v\d+|graphql|rest|auth|login|search|users?)/[^"'\s<>]*)["']"""),
    re.compile(r"""["'](https?://[^"'\s<>]+)["']"""),
]


@dataclass
class Target:
    url: str
    host: str
    explicit: bool
    raw: str


@dataclass
class PageData:
    url: str = ""
    final_url: str = ""
    status: int = 0
    title: str = ""
    generator: str = ""
    html: str = ""
    headers: Dict[str, str] = field(default_factory=dict)
    cookies: List[Dict[str, Any]] = field(default_factory=list)
    scripts: List[str] = field(default_factory=list)
    styles: List[str] = field(default_factory=list)
    forms: List[Dict[str, str]] = field(default_factory=list)
    links: List[str] = field(default_factory=list)
    meta: Dict[str, str] = field(default_factory=dict)
    error: str = ""


@dataclass
class NetworkEntry:
    method: str
    url: str
    status: int = 0
    resource_type: str = ""
    failure: str = ""


@dataclass
class Teardown:
    target: Target
    authorization: str
    backend: str
    page: PageData
    network: List[NetworkEntry] = field(default_factory=list)
    endpoints: List[str] = field(default_factory=list)
    third_party: List[str] = field(default_factory=list)
    stack: List[str] = field(default_factory=list)
    missing_headers: List[str] = field(default_factory=list)
    secrets: List[str] = field(default_factory=list)
    console_errors: List[str] = field(default_factory=list)
    page_errors: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    screenshot_path: str = ""
    artifacts: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def parse_target(raw: str) -> Target:
    text = (raw or "").strip()
    if not text:
        raise ValueError("Target URL is required.")
    explicit = False
    if text.lower().startswith("authorized "):
        explicit = True
        text = text[len("authorized "):].strip()
    if not text:
        raise ValueError("Target URL is required after 'authorized'.")
    if "://" not in text:
        host = text.split("/", 1)[0].split(":", 1)[0].lower()
        scheme = "http" if _is_private_host(host) else "https"
        text = f"{scheme}://{text}"
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Only http:// and https:// targets are supported.")
    if parsed.username or parsed.password:
        raise ValueError("Target URLs must not contain credentials.")
    return Target(
        url=urlunparse(parsed._replace(fragment="")),
        host=parsed.hostname.lower().rstrip("."),
        explicit=explicit,
        raw=text,
    )


def _is_private_host(host: str) -> bool:
    host = (host or "").lower().strip("[]")
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    if host.endswith((".localhost", ".local", ".test", ".internal")):
        return True
    try:
        address = ipaddress.ip_address(host)
        return address.is_private or address.is_loopback or address.is_link_local
    except ValueError:
        return False


def _allowlist(security: Dict[str, Any]) -> List[str]:
    entries = security.get("authorized_targets") or []
    result = []
    for entry in entries:
        value = str(entry).strip().lower()
        if "://" in value:
            value = urlparse(value).hostname or value
        value = value.strip(". ")
        if value:
            result.append(value)
    return result


def authorize(target: Target, security: Dict[str, Any]) -> Tuple[bool, str]:
    if target.explicit:
        return True, "explicit 'authorized' prefix"
    if _is_private_host(target.host):
        return True, "private/lab target"
    for entry in _allowlist(security):
        if entry.startswith("*."):
            base = entry[2:]
            if target.host == base or target.host.endswith("." + base):
                return True, f"allowlist {entry}"
        elif target.host == entry or target.host.endswith("." + entry):
            return True, f"allowlist {entry}"
    return False, "not authorized"


def _rea_config(security: Dict[str, Any]) -> Dict[str, Any]:
    return security.get("rea") or {}


def _find_browser(rea_cfg: Dict[str, Any]) -> Optional[str]:
    configured = (rea_cfg.get("browser") or os.environ.get("GRID_REA_BROWSER") or "").strip()
    if configured and Path(configured).exists():
        return configured
    candidates = [
        os.path.join(os.environ.get("ProgramFiles", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(os.environ.get("ProgramFiles", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    for path in candidates:
        if path and Path(path).exists():
            return path
    return None


def _rea_command(rea_cfg: Dict[str, Any]) -> Optional[List[str]]:
    configured = rea_cfg.get("command")
    if configured:
        if isinstance(configured, str):
            return shlex.split(configured)
        return [str(part) for part in configured]
    found = shutil.which("rea")
    if found:
        return [found]
    # Downloading and executing a package is opt-in. Without it, use the native
    # fallback instead of silently running code from npm.
    if rea_cfg.get("allow_npx"):
        npx = shutil.which("npx")
        if npx:
            return [npx, "-y", f"rea-agents@{DEFAULT_REA_VERSION}"]
    return None


def build_scenario(target: Target, browser: str, scroll_steps: int = 4) -> Dict[str, Any]:
    try:
        steps = max(0, min(int(scroll_steps), 12))
    except (TypeError, ValueError):
        steps = 4
    actions: List[Dict[str, Any]] = [
        {"step_id": "settle", "action": "wait_for_timeout", "duration_ms": 1200}
    ]
    for index in range(steps):
        actions.append(
            {
                "step_id": f"scroll-{index + 1}",
                "action": "press",
                "locator": {"kind": "css", "selector": "body"},
                "key": "PageDown",
            }
        )
        actions.append(
            {
                "step_id": f"scroll-wait-{index + 1}",
                "action": "wait_for_timeout",
                "duration_ms": 600,
            }
        )
    if steps:
        actions.append(
            {
                "step_id": "scroll-top",
                "action": "press",
                "locator": {"kind": "css", "selector": "body"},
                "key": "Home",
            }
        )
        actions.append(
            {"step_id": "scroll-top-wait", "action": "wait_for_timeout", "duration_ms": 500}
        )
    return {
        "browser": {
            "mode": "launch",
            "executable_path": browser,
            "headless": True,
        },
        "start_url": {"url": target.url},
        "actions": actions,
        "environment": {
            "viewport": {"width": 1280, "height": 720, "device_scale_factor": 1},
            "locale": "en-US",
            "timezone": "UTC",
            "color_scheme": "light",
            "reduced_motion": "reduce",
            "service_workers": "block",
        },
        "capture": {
            "at_end": ["dom", "screenshot", "url", "history", "storage"],
            "events": ["console", "page-errors", "network"],
            "network": {
                "request_body": False,
                "response_body": False,
                "header_values": False,
            },
        },
        "command_timeout_ms": 30000,
    }


def _run_rea(
    target: Target,
    report_dir: Path,
    rea_cfg: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], str]:
    browser = _find_browser(rea_cfg)
    command = _rea_command(rea_cfg)
    if not browser:
        return None, "REA browser not found (set security.rea.browser)."
    if not command:
        return None, (
            "REA CLI not found (install rea-agents and put rea on PATH, "
            "set security.rea.command, or set security.rea.allow_npx=true)."
        )
    scenario_path = report_dir / "scenario.json"
    scenario_path.write_text(
        json.dumps(
            build_scenario(target, browser, rea_cfg.get("scroll_steps", 4)),
            indent=2,
        ),
        encoding="utf-8",
    )
    timeout = int(rea_cfg.get("timeout_seconds", 300) or 300)
    try:
        proc = subprocess.run(
            command + ["capture-browser-scenario", str(scenario_path), "--json"],
            cwd=str(report_dir),
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as exc:
        return None, f"REA launch failed: {exc}"
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[:1200]
        return None, f"REA exited {proc.returncode}: {detail}"
    raw = (proc.stdout or "").strip().lstrip("\ufeff")
    if not raw:
        return None, "REA returned no output."
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"REA JSON parse failed: {exc}"
    (report_dir / "rea.json").write_text(raw, encoding="utf-8")
    return data, ""


def _fetch(url: str, timeout: int = 15) -> Optional[requests.Response]:
    try:
        response = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        )
        return response
    except requests.RequestException:
        return None


def _script_urls(html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    urls = []
    for tag in soup.find_all("script", src=True):
        src = (tag.get("src") or "").strip()
        if not src:
            continue
        absolute = urljoin(base_url, src)
        if absolute.startswith(("http://", "https://")):
            urls.append(absolute)
    return _dedupe(urls)


def _extract_scripts(urls: Iterable[str], base_url: str) -> List[str]:
    base_host = urlparse(base_url).hostname
    texts = []
    for index, url in enumerate(urls):
        if index >= MAX_SCRIPTS:
            break
        if urlparse(url).hostname != base_host:
            continue
        response = _fetch(url, timeout=10)
        if response is None or response.status_code >= 400:
            continue
        texts.append(response.content[:MAX_SCRIPT_BYTES].decode("utf-8", "replace"))
    return texts


def _extract_endpoints(html: str, scripts: List[str], base_url: str) -> List[str]:
    sources = [html or ""] + scripts
    endpoints = []
    base = urlparse(base_url)
    for source in sources:
        for pattern in ENDPOINT_PATTERNS:
            for match in pattern.findall(source):
                value = (match or "").strip()
                if not value:
                    continue
                absolute = urljoin(base_url, value)
                parsed = urlparse(absolute)
                if parsed.scheme not in ("http", "https"):
                    continue
                if parsed.hostname != base.hostname:
                    continue
                endpoints.append(urlunparse(parsed))
    return _dedupe(endpoints)[:MAX_ENDPOINTS]


def _third_party(html: str, scripts: List[str], base_url: str) -> List[str]:
    base_host = urlparse(base_url).hostname
    hosts = set()
    soup = BeautifulSoup(html or "", "html.parser")
    urls = []
    for tag in soup.find_all(["script", "link", "img", "iframe", "form"]):
        value = tag.get("src") or tag.get("href") or tag.get("action")
        if value:
            urls.append(urljoin(base_url, value))
    for script in scripts:
        for match in re.findall(r"""https?://[^\s"'<>]+""", script):
            urls.append(match)
    for url in urls:
        host = urlparse(url).hostname
        if host and host != base_host:
            hosts.add(host)
    return sorted(hosts)


def _find_secrets(scripts: List[str]) -> List[str]:
    findings = []
    seen = set()
    for script in scripts:
        for label, pattern in SECRET_PATTERNS:
            for match in pattern.findall(script):
                if match in seen:
                    continue
                seen.add(match)
                findings.append(f"{label}: {match[:4]}…{match[-4:]}")
    return findings


def _stack_signals(page: PageData, scripts: List[str]) -> List[str]:
    haystack = " ".join(
        [
            page.html,
            page.generator,
            " ".join(page.scripts),
            " ".join(page.headers.values()),
            " ".join(scripts),
        ]
    ).lower()
    signals = []
    checks = [
        ("next.js", ("_next/", "__next_data__")),
        ("react", ("react", "data-reactroot")),
        ("vue", ("vue.js", "__vue__", "data-v-")),
        ("angular", ("ng-version", "angular")),
        ("svelte", ("svelte", "__svelte")),
        ("wordpress", ("wp-content", "wp-includes")),
        ("shopify", ("shopify", "cdn.shopify")),
        ("cloudflare", ("cloudflare", "cf-ray")),
        ("webpack", ("webpack", "chunk.js")),
    ]
    for name, needles in checks:
        if any(needle in haystack for needle in needles):
            signals.append(name)
    if page.generator:
        signals.append(f"generator: {page.generator}")
    return _dedupe(signals)


def _missing_headers(headers: Dict[str, str]) -> List[str]:
    lowered = {key.lower() for key in headers}
    return [name for name in SECURITY_HEADERS if name not in lowered]


def _parse_static(target: Target) -> Tuple[PageData, List[str], List[str]]:
    response = _fetch(target.url)
    if response is None:
        return PageData(url=target.url, final_url=target.url, error="request failed"), [], []
    content = response.content[:MAX_PAGE_BYTES]
    html = content.decode(response.encoding or "utf-8", "replace")
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    generator = ""
    meta = {}
    for tag in soup.find_all("meta"):
        name = (tag.get("name") or tag.get("property") or "").strip()
        value = (tag.get("content") or "").strip()
        if name:
            meta[name] = value
            if name.lower() == "generator":
                generator = value
    forms = []
    for form in soup.find_all("form"):
        forms.append(
            {
                "action": urljoin(target.url, form.get("action") or ""),
                "method": (form.get("method") or "get").upper(),
                "inputs": ",".join(
                    input_tag.get("name", "")
                    for input_tag in form.find_all(["input", "textarea", "select"])
                    if input_tag.get("name")
                ),
            }
        )
    links = _dedupe(
        urljoin(target.url, a.get("href", ""))
        for a in soup.find_all("a", href=True)
        if a.get("href")
    )
    page = PageData(
        url=target.url,
        final_url=response.url,
        status=response.status_code,
        title=title,
        generator=generator,
        html=html,
        headers={key: value for key, value in response.headers.items()},
        cookies=[
            {
                "name": cookie.name,
                "secure": bool(cookie.secure),
                "http_only": bool(cookie.has_nonstandard_attr("HttpOnly")),
                "same_site": cookie.get_nonstandard_attr("SameSite") or "",
            }
            for cookie in response.cookies
        ],
        scripts=_script_urls(html, response.url),
        styles=_dedupe(
            urljoin(response.url, tag.get("href", ""))
            for tag in soup.find_all("link", href=True)
            if "stylesheet" in (tag.get("rel") or [])
        ),
        forms=forms,
        links=links,
        meta=meta,
    )
    same_origin_scripts = [
        url for url in page.scripts if urlparse(url).hostname == urlparse(response.url).hostname
    ]
    script_texts = _extract_scripts(same_origin_scripts, response.url)
    return page, same_origin_scripts, script_texts


def _parse_rea(data: Dict[str, Any], target: Target, report_dir: Path) -> Tuple[PageData, List[NetworkEntry], List[str], List[str], str, List[str]]:
    normalized = data.get("normalized_result") or data
    steps = normalized.get("steps") or []
    html = ""
    final_url = target.url
    screenshot_path = ""
    for step in steps:
        artifacts = step.get("artifacts") or {}
        dom = artifacts.get("dom") or {}
        if dom.get("state") == "captured":
            html = (dom.get("value") or {}).get("text") or html
        url_value = artifacts.get("url") or {}
        if url_value.get("state") == "captured":
            final_url = (url_value.get("value") or {}).get("url") or final_url
        screenshot = artifacts.get("screenshot") or {}
        if screenshot.get("state") == "captured" and not screenshot_path:
            encoded = (screenshot.get("value") or {}).get("data_base64")
            if encoded:
                try:
                    path = report_dir / "screenshot.png"
                    path.write_bytes(base64.b64decode(encoded))
                    screenshot_path = str(path)
                except Exception:
                    pass

    page = PageData(url=target.url, final_url=final_url, html=html)
    if html:
        soup = BeautifulSoup(html, "html.parser")
        page.title = soup.title.get_text(" ", strip=True) if soup.title else ""
        page.generator = ""
        for tag in soup.find_all("meta"):
            name = (tag.get("name") or tag.get("property") or "").strip()
            value = (tag.get("content") or "").strip()
            if name:
                page.meta[name] = value
                if name.lower() == "generator":
                    page.generator = value
        page.scripts = _script_urls(html, final_url)
        page.styles = _dedupe(
            urljoin(final_url, tag.get("href", ""))
            for tag in soup.find_all("link", href=True)
            if "stylesheet" in (tag.get("rel") or [])
        )
        page.links = _dedupe(
            urljoin(final_url, a.get("href", ""))
            for a in soup.find_all("a", href=True)
            if a.get("href")
        )
        page.forms = [
            {
                "action": urljoin(final_url, form.get("action") or ""),
                "method": (form.get("method") or "get").upper(),
                "inputs": ",".join(
                    input_tag.get("name", "")
                    for input_tag in form.find_all(["input", "textarea", "select"])
                    if input_tag.get("name")
                ),
            }
            for form in soup.find_all("form")
        ]

    events = normalized.get("events") or {}
    network = []
    console_errors = []
    page_errors = []
    for item in events.get("items") or []:
        kind = item.get("kind")
        if kind == "request":
            network.append(
                NetworkEntry(
                    method=str(item.get("method") or ""),
                    url=str((item.get("url") or {}).get("url") or ""),
                    resource_type=str(item.get("resource_type") or ""),
                )
            )
        elif kind == "response":
            url = str((item.get("url") or {}).get("url") or "")
            for entry in reversed(network):
                if entry.url == url and not entry.status:
                    entry.status = int(item.get("status") or 0)
                    break
        elif kind == "request-failed":
            url = str((item.get("url") or {}).get("url") or "")
            for entry in reversed(network):
                if entry.url == url and not entry.failure:
                    entry.failure = str(item.get("failure") or "failed")
                    break
        elif kind == "console" and str(item.get("level")) == "error":
            console_errors.append(str(item.get("text") or ""))
        elif kind == "page-error":
            page_errors.append(str(item.get("message") or ""))

    limitations = [str(item) for item in (normalized.get("limitations") or data.get("limitations") or [])]
    browser = normalized.get("browser") or {}
    if browser:
        limitations.append(
            f"Captured with {browser.get('product', 'browser')} "
            f"{browser.get('version', '')} (headless)."
        )
    return page, network, console_errors, page_errors, screenshot_path, limitations


def build_report(teardown: Teardown, manifest: Dict[str, Any]) -> str:
    page = teardown.page
    lines = [
        f"# REA Teardown — {teardown.target.host}",
        "",
        f"- **Target:** {teardown.target.url}",
        f"- **Final URL:** {page.final_url or page.url}",
        f"- **Generated:** {manifest.get('generated_at', '')}",
        f"- **Authorization:** {teardown.authorization}",
        f"- **Backend:** {teardown.backend}",
        "- **Scope:** passive public assets only; no exploitation, fuzzing or authenticated requests.",
        f"- **Evidence:** `{manifest.get('evidence_dir', '')}`",
        "",
        "## Summary",
        "",
        f"- Title: **{page.title or '(none)'}**",
        f"- HTTP status: `{page.status or 'unknown'}`",
        f"- Scripts: `{len(page.scripts)}` · network requests: `{len(teardown.network)}` · "
        f"endpoints: `{len(teardown.endpoints)}` · third-party origins: `{len(teardown.third_party)}`",
    ]
    if teardown.stack:
        lines.append(f"- Stack signals: {', '.join(teardown.stack)}")
    if teardown.missing_headers:
        lines.append(f"- Missing security headers: {', '.join(teardown.missing_headers)}")
    if teardown.secrets:
        lines.append(f"- Potential secrets (redacted): `{len(teardown.secrets)}`")
    if page.error:
        lines.append(f"- Fetch error: {page.error}")
    lines += ["", "## Stack & fingerprints", ""]
    lines += [f"- {item}" for item in teardown.stack] or ["- No strong fingerprints observed."]
    lines += ["", "## Page metadata", ""]
    if page.meta:
        for key in sorted(page.meta)[:30]:
            lines.append(f"- `{key}`: {page.meta[key][:300]}")
    else:
        lines.append("- No meta tags observed.")
    lines += ["", "## Scripts & assets", ""]
    lines += [f"- {url}" for url in page.scripts[:40]] or ["- No script tags observed."]
    if page.styles:
        lines += ["", "### Stylesheets", ""]
        lines += [f"- {url}" for url in page.styles[:20]]
    if page.forms:
        lines += ["", "## Forms", ""]
        for form in page.forms[:20]:
            lines.append(f"- `{form['method']} {form['action']}` inputs: {form['inputs'] or '(none)'}")
    lines += ["", "## Network / API endpoints", ""]
    if teardown.network:
        lines += ["| Method | Status | Type | URL |", "|---|---|---|---|"]
        for entry in teardown.network[:100]:
            status = str(entry.status) if entry.status else (entry.failure or "")
            lines.append(f"| {entry.method} | {status} | {entry.resource_type} | `{entry.url}` |")
    else:
        lines.append("- No network events captured.")
    lines += ["", "### Inferred endpoints", ""]
    lines += [f"- `{url}`" for url in teardown.endpoints[:100]] or ["- No endpoint strings found."]
    lines += ["", "## Third-party origins", ""]
    lines += [f"- `{host}`" for host in teardown.third_party] or ["- None observed."]
    lines += ["", "## Security headers", ""]
    if page.headers:
        for name in SECURITY_HEADERS:
            value = next((v for k, v in page.headers.items() if k.lower() == name), "")
            lines.append(f"- **{name}**: {value or 'MISSING'}")
    else:
        lines.append("- Headers unavailable (REA captures names only).")
    lines += ["", "## Cookies", ""]
    lines += [
        f"- `{cookie['name']}` secure={cookie['secure']} http_only={cookie['http_only']} "
        f"same_site={cookie['same_site'] or 'unset'}"
        for cookie in page.cookies
    ] or ["- No cookies observed."]
    lines += ["", "## Potential secrets (redacted)", ""]
    lines += [f"- {item}" for item in teardown.secrets] or ["- None detected in downloaded scripts."]
    lines += ["", "## Console and page errors", ""]
    lines += [f"- console: {item[:300]}" for item in teardown.console_errors[:30]]
    lines += [f"- page: {item[:300]}" for item in teardown.page_errors[:30]]
    if not teardown.console_errors and not teardown.page_errors:
        lines.append("- None observed.")
    lines += ["", "## Limitations", ""]
    lines += [f"- {item}" for item in teardown.limitations] or ["- None recorded."]
    lines += ["", "## Evidence", ""]
    for item in _dedupe(list(teardown.artifacts) + ([teardown.screenshot_path] if teardown.screenshot_path else [])):
        lines.append(f"- `{item}`")
    lines += ["", "---", "_Generated by GRID REA. Use only on assets you own or are authorized to test._", ""]
    return "\n".join(lines)


def _slug(host: str) -> str:
    value = re.sub(r"[^A-Za-z0-9.-]+", "-", host).strip("-.")
    return value[:80] or "target"


def run_teardown(input_text: str, security: Optional[Dict[str, Any]] = None) -> str:
    """Run an authorized passive teardown and return a chat-ready summary."""
    security = security or {}
    try:
        target = parse_target(input_text)
    except ValueError as exc:
        return f"REA error: {exc}"
    allowed, reason = authorize(target, security)
    if not allowed:
        return (
            f"REA refused: `{target.host}` is not authorized.\n"
            f"Use `rea authorized {target.url}` for a one-off, or add the host to "
            "`security.authorized_targets` in config.json."
        )

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_dir = REFS_DIR / f"{_slug(target.host)}-{stamp}"
    report_dir.mkdir(parents=True, exist_ok=True)
    artifacts: List[str] = []
    limitations: List[str] = []
    notes: List[str] = []
    backend = "native"

    rea_data = None
    rea_error = ""
    rea_cfg = _rea_config(security)
    if rea_cfg.get("enabled", True):
        rea_data, rea_error = _run_rea(target, report_dir, rea_cfg)
        if rea_data:
            backend = "rea"

    if rea_data:
        page, network, console_errors, page_errors, screenshot_path, rea_limits = _parse_rea(
            rea_data, target, report_dir
        )
        limitations.extend(rea_limits)
        artifacts.append(str(report_dir / "rea.json"))
        if screenshot_path:
            artifacts.append(screenshot_path)
    else:
        page, _, script_texts = _parse_static(target)
        network = []
        console_errors = []
        page_errors = []
        screenshot_path = ""
        if rea_error:
            notes.append(f"REA backend unavailable: {rea_error}")
            limitations.append("Used the native static fallback; JavaScript-rendered content may be incomplete.")
        artifacts.append(str(report_dir / "page.html"))
        (report_dir / "page.html").write_text(page.html, encoding="utf-8")

    # A native header fetch gives real header values even when REA captured the DOM.
    if backend == "rea":
        header_response = _fetch(page.final_url or target.url)
        if header_response is not None:
            page.status = header_response.status_code
            page.headers = {key: value for key, value in header_response.headers.items()}
            page.cookies = [
                {
                    "name": cookie.name,
                    "secure": bool(cookie.secure),
                    "http_only": bool(cookie.has_nonstandard_attr("HttpOnly")),
                    "same_site": cookie.get_nonstandard_attr("SameSite") or "",
                }
                for cookie in header_response.cookies
            ]

    base_url = page.final_url or target.url
    base_host = urlparse(base_url).hostname or target.host
    if base_host != target.host:
        limitations.append(
            f"Target redirected from {target.host} to {base_host}; "
            "only public GET requests were made."
        )
    script_texts = _extract_scripts(
        [url for url in page.scripts if urlparse(url).hostname == base_host],
        base_url,
    )
    endpoints = _extract_endpoints(page.html, script_texts, base_url)
    endpoints = _dedupe(endpoints + [entry.url for entry in network if entry.resource_type in {"fetch", "xhr"}])
    third_party = _third_party(page.html, script_texts, base_url)
    stack = _stack_signals(page, script_texts)
    missing = _missing_headers(page.headers)
    secrets = _find_secrets(script_texts + [page.html])

    teardown = Teardown(
        target=target,
        authorization=reason,
        backend=backend,
        page=page,
        network=network,
        endpoints=endpoints,
        third_party=third_party,
        stack=stack,
        missing_headers=missing,
        secrets=secrets,
        console_errors=console_errors,
        page_errors=page_errors,
        limitations=limitations,
        screenshot_path=screenshot_path,
        artifacts=artifacts,
        notes=notes,
    )

    manifest = {
        "target": target.url,
        "host": target.host,
        "final_url": page.final_url,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "authorization": reason,
        "backend": backend,
        "evidence_dir": str(report_dir),
        "counts": {
            "scripts": len(page.scripts),
            "network": len(teardown.network),
            "endpoints": len(teardown.endpoints),
            "third_party": len(teardown.third_party),
            "secrets": len(teardown.secrets),
        },
        "files": [],
        "notes": notes,
    }
    if rea_data:
        manifest["rea_evidence_id"] = rea_data.get("evidence_id")
    (report_dir / "network.json").write_text(
        json.dumps([entry.__dict__ for entry in teardown.network], indent=2),
        encoding="utf-8",
    )
    (report_dir / "headers.json").write_text(
        json.dumps(page.headers, indent=2), encoding="utf-8"
    )
    report = build_report(teardown, manifest)
    report_path = report_dir / "report.md"
    report_path.write_text(report, encoding="utf-8")
    manifest["files"] = sorted(str(path) for path in report_dir.iterdir()) + [
        str(report_dir / "manifest.json")
    ]
    (report_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    summary = [
        f"REA complete for {target.url}",
        f"Authorization: {reason}",
        f"Backend: {backend}",
        f"Page: {page.title or '(no title)'} [{page.status or 'unknown'}]",
        f"Findings: {len(page.scripts)} scripts · {len(teardown.endpoints)} endpoints · "
        f"{len(teardown.third_party)} third-party origins · "
        f"{len(missing)} missing security headers",
        f"Report: {report_path}",
    ]
    if notes:
        summary.append(notes[0])
    return "\n".join(summary)


def authorize_host(security: Dict[str, Any], host: str) -> Tuple[Dict[str, Any], str]:
    host = (host or "").strip().lower()
    if host.startswith("http://") or host.startswith("https://"):
        host = urlparse(host).hostname or host
    host = host.strip(". ")
    if not host:
        return security, "Error: host is required."
    entries = list(security.get("authorized_targets") or [])
    if host in [str(entry).lower() for entry in entries]:
        return security, f"Already authorized: {host}"
    entries.append(host)
    security = dict(security)
    security["authorized_targets"] = entries
    return security, f"Authorized: {host}"


def revoke_host(security: Dict[str, Any], host: str) -> Tuple[Dict[str, Any], str]:
    host = (host or "").strip().lower()
    if host.startswith("http://") or host.startswith("https://"):
        host = urlparse(host).hostname or host
    entries = [str(entry) for entry in (security.get("authorized_targets") or [])]
    kept = [entry for entry in entries if entry.lower() != host]
    security = dict(security)
    security["authorized_targets"] = kept
    if len(kept) == len(entries):
        return security, f"Not in allowlist: {host}"
    return security, f"Revoked: {host}"


def list_allowlist(security: Dict[str, Any]) -> str:
    entries = _allowlist(security)
    if not entries:
        return "No authorized targets. Use `/rea authorize <host>` or `rea authorized <url>`."
    return "Authorized targets:\n" + "\n".join(f"- {entry}" for entry in entries)


def _dedupe(values: Iterable[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        value = (value or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
