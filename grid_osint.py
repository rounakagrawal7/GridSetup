import json
import os
import re
import socket
import ssl
import time
import warnings
warnings.filterwarnings("ignore", message="This package.*renamed")
from datetime import datetime
from email.utils import parseaddr
from pathlib import Path

PICDATA_DIR = Path(__file__).parent / "picdata"
PICDATA_DIR.mkdir(exist_ok=True)

KNOWN_TLDS = {
    'com','org','net','edu','gov','mil','int',
    'io','co','ai','app','dev','me','info',
    'uk','us','ca','de','fr','jp','au','cn','in','ru','br','it','es',
    'nl','se','no','dk','fi','pl','ch','at','be','pt','gr','ie',
    'nz','hk','sg','my','ph','th','tw','kr','za','mx','ar','cl',
    'tv','to','cc','ws','bz','pro','name','mobi','biz','xxx',
    'online','site','tech','shop','blog','xyz','top','club','world',
    'live','today','news','life','cloud','work','media','email',
    'design','studio','agency','guru','global','link','click',
    'cool','zone','network','systems','group','team','press',
    'digital','software','events','energy','solutions','support',
    'training','photos','social','directory','finance','health',
    'careers','education','legal','wiki','zone',
}


class OSINT:
    def __init__(self):
        self.results = {}
        self.session_dir = None

    def _init_session(self):
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.session_dir = PICDATA_DIR / ts
        self.session_dir.mkdir(parents=True, exist_ok=True)
        return self.session_dir

    def _save_to_duckdb(self, table, data_dict):
        try:
            from grid_db import GridDB
            db = GridDB()
            cols = ", ".join(data_dict.keys())
            placeholders = ", ".join(["?"] * len(data_dict))
            vals = list(data_dict.values())
            db.conn.execute(
                f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({placeholders})",
                vals,
            )
        except Exception:
            pass

    def _upload_to_pocketbase(self, filepath, label, session_tag):
        try:
            from grid_pb import PocketBaseManager
            pb = PocketBaseManager()
            if pb.is_running():
                pb._post_init()
                pb.upload_artifact(str(filepath), label=label, session_id=session_tag)
        except Exception:
            pass

    def _dns_query(self, domain, record_type="A"):
        try:
            results = []
            try:
                addrs = socket.getaddrinfo(domain, 0, socket.AF_UNSPEC, socket.SOCK_STREAM)
                seen = set()
                for addr in addrs:
                    ip = addr[4][0]
                    if ip not in seen:
                        seen.add(ip)
                        family = "IPv4" if addr[0] == socket.AF_INET else "IPv6"
                        results.append(f"{family}: {ip}")
            except socket.gaierror as e:
                return {"error": str(e)}
            return results
        except Exception as e:
            return {"error": str(e)}

    def _get_cert_info(self, hostname, port=443):
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with socket.create_connection((hostname, port), timeout=5) as sock:
                with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()
                    info = {
                        "subject": dict(cert.get("subject", [])[0]) if cert.get("subject") else {},
                        "issuer": dict(cert.get("issuer", [])[0]) if cert.get("issuer") else {},
                        "sans": cert.get("subjectAltName", []),
                        "not_before": cert.get("notBefore", ""),
                        "not_after": cert.get("notAfter", ""),
                        "serial": hex(cert.get("serialNumber", 0)),
                    }
                    return info
        except Exception:
            return {}

    def _crt_sh_subdomains(self, domain):
        try:
            import requests
            r = requests.get(f"https://crt.sh/?q=%25.{domain}&output=json", timeout=15,
                             headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                return []
            data = r.json()
            subs = set()
            for entry in data:
                name = entry.get("name_value", "")
                for n in name.split("\n"):
                    n = n.strip().lower()
                    if n.endswith("." + domain.lower()) or n == domain.lower():
                        subs.add(n)
            return sorted(subs)[:50]
        except Exception:
            return []

    def _tech_detect(self, url):
        try:
            import requests
            r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True)
            headers = dict(r.headers)
            tech = []
            server = headers.get("Server", "")
            if server:
                tech.append(f"Server: {server}")
            powered = headers.get("X-Powered-By", "")
            if powered:
                tech.append(f"X-Powered-By: {powered}")
            if "Set-Cookie" in headers:
                for c in headers.getall("Set-Cookie", []):
                    if "session" in c.lower():
                        tech.append("Session cookie detected")
                        break
            ct = headers.get("Content-Type", "")
            if "asp" in server.lower() or "asp.net" in server.lower():
                tech.append("ASP.NET")
            if "php" in server.lower():
                tech.append("PHP")
            if "nginx" in server.lower():
                tech.append("Nginx")
            if "cloudflare" in str(headers).lower():
                tech.append("Cloudflare")
            if "wordpress" in r.text[:2000].lower():
                tech.append("WordPress")
            return tech
        except Exception:
            return []

    def _ip_geolocation(self, ip):
        try:
            import requests
            r = requests.get(f"http://ip-api.com/json/{ip}?fields=status,country,regionName,city,isp,org,as,mobile,proxy,hosting", timeout=5)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return {}

    def _check_username(self, username):
        platforms = {
            "GitHub":     f"https://github.com/{username}",
            "Twitter/X":  f"https://x.com/{username}",
            "Reddit":     f"https://reddit.com/user/{username}",
            "Instagram":  f"https://instagram.com/{username}",
            "Medium":     f"https://medium.com/@{username}",
            "Keybase":    f"https://keybase.io/{username}",
            "Telegram":   f"https://t.me/{username}",
            "PyPI":       f"https://pypi.org/user/{username}",
            "TikTok":     f"https://tiktok.com/@{username}",
            "Pinterest":  f"https://pinterest.com/{username}",
            "Snapchat":   f"https://snapchat.com/add/{username}",
            "Facebook":   f"https://facebook.com/{username}",
            "YouTube":    f"https://youtube.com/@{username}",
            "Twitch":     f"https://twitch.tv/{username}",
            "Dev.to":     f"https://dev.to/{username}",
            "BitBucket":  f"https://bitbucket.org/{username}",
            "GitLab":     f"https://gitlab.com/{username}",
            "VK":         f"https://vk.com/{username}",
            "Steam":      f"https://steamcommunity.com/id/{username}",
            "Spotify":    f"https://open.spotify.com/user/{username}",
        }
        results = []
        import requests as req
        import concurrent.futures as _cf
        def _check(pair):
            pname, purl = pair
            try:
                r = req.get(purl, timeout=1.5, allow_redirects=True)
                if r.status_code == 200:
                    return f"[URL EXISTS] {pname}: {purl}"
                elif r.status_code == 403:
                    return f"[BLOCKED] {pname}: {purl} (403)"
            except Exception:
                pass
            return None
        with _cf.ThreadPoolExecutor(max_workers=10) as ex:
            for res in ex.map(_check, platforms.items()):
                if res:
                    results.append(res)
        return results

    def _web_extract_links(self, url):
        try:
            import requests
            from bs4 import BeautifulSoup
            r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True)
            soup = BeautifulSoup(r.text, "html.parser")
            links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href and not href.startswith("#") and not href.startswith("javascript:"):
                    links.append(href[:200])
            meta_desc = ""
            m = soup.find("meta", attrs={"name": "description"})
            if m and m.get("content"):
                meta_desc = m["content"]
            title = soup.title.string.strip() if soup.title and soup.title.string else ""
            return {
                "title": title,
                "description": meta_desc,
                "links": links[:30],
                "text_length": len(soup.get_text(strip=True)),
            }
        except Exception as e:
            return {"error": str(e)}

    def _extract_phones_from_text(self, text):
        import phonenumbers
        phones = set()
        candidates = set(re.findall(r"\+?\d[\d\s\-\.\(\)]{6,}\d", text))
        for c in candidates:
            try:
                z = phonenumbers.parse(c, None)
                if phonenumbers.is_possible_number(z):
                    e164 = phonenumbers.format_number(z, phonenumbers.PhoneNumberFormat.E164)
                    phones.add(e164)
            except Exception:
                pass
        return sorted(phones)[:10]

    def _is_phone(self, s):
        s = s.strip()
        digits = re.sub(r"\D", "", s)
        if len(digits) < 7 or len(digits) > 15:
            return None
        import phonenumbers
        if s.startswith("+"):
            try:
                z = phonenumbers.parse(s, None)
                if phonenumbers.is_possible_number(z):
                    return z
            except Exception:
                pass
            raw = {"raw": s, "e164": "+" + digits, "country": "Unknown", "possible": False, "digits": digits}
            return raw
        if re.match(r"^[\d\s\-\.\(\)\+]+$", s) and any(c in s for c in ["-", "(", ")", "+", " "]):
            for country_hint in ["US", "IN", "GB", "DE", "FR", "AU", "CA", "BR", "JP", "RU"]:
                try:
                    z = phonenumbers.parse(s, country_hint)
                    if phonenumbers.is_valid_number(z):
                        return z
                except Exception:
                    pass
        return None

    def _gather_phone(self, z):
        import phonenumbers
        import re as _re
        mods = {}

        is_parsed = isinstance(z, phonenumbers.PhoneNumber)
        if is_parsed:
            country = phonenumbers.region_code_for_number(z)
            national = phonenumbers.format_number(z, phonenumbers.PhoneNumberFormat.NATIONAL)
            inter = phonenumbers.format_number(z, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
            e164 = phonenumbers.format_number(z, phonenumbers.PhoneNumberFormat.E164)
            num_type = phonenumbers.number_type(z)
            type_map = {
                phonenumbers.PhoneNumberType.MOBILE: "Mobile",
                phonenumbers.PhoneNumberType.FIXED_LINE: "Fixed Line",
                phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE: "Fixed/Mobile",
                phonenumbers.PhoneNumberType.VOIP: "VoIP",
                phonenumbers.PhoneNumberType.TOLL_FREE: "Toll-Free",
                phonenumbers.PhoneNumberType.PREMIUM_RATE: "Premium Rate",
                phonenumbers.PhoneNumberType.SHARED_COST: "Shared Cost",
                phonenumbers.PhoneNumberType.PAGER: "Pager",
                phonenumbers.PhoneNumberType.UAN: "UAN",
                phonenumbers.PhoneNumberType.UNKNOWN: "Unknown",
            }
            mods["parsed_info"] = {
                "country": country or "Unknown",
                "country_code": f"+{z.country_code}",
                "national_format": national,
                "international_format": inter,
                "e164": e164,
                "type": type_map.get(num_type, "Unknown"),
            }
            try:
                carrier = phonenumbers.carrier.name_for_number(z, "en")
                if carrier:
                    mods["parsed_info"]["carrier"] = carrier
            except Exception:
                pass
            try:
                geocode = phonenumbers.geocoder.description_for_number(z, "en")
                if geocode:
                    mods["parsed_info"]["location"] = geocode
            except Exception:
                pass
            search_term = e164
        else:
            mods["parsed_info"] = {
                "country": "Unknown",
                "country_code": "?",
                "national_format": z.get("raw", ""),
                "e164": z.get("e164", ""),
                "type": "Unknown (unverified)",
            }
            search_term = z.get("e164", z.get("raw", ""))

        import concurrent.futures as _cf
        raw_num = _re.sub(r"\D", "", search_term)
        web_q = search_term[1:] if search_term.startswith("+") else search_term

        def _do_wa():
            try:
                import requests
                r = requests.get(f"https://wa.me/{raw_num}", timeout=2, allow_redirects=True)
                if r.status_code == 200:
                    b = r.text.lower()[:1500]
                    if "whatsapp" in b and ("send" in b or "chat" in b or "message" in b):
                        return f"Likely on WhatsApp: https://wa.me/{raw_num}"
            except Exception:
                pass
            return None

        def _do_ddgs():
            try:
                from ddgs import DDGS
                snippets = []
                with DDGS() as ddgs:
                    for r in ddgs.text(web_q, max_results=6):
                        t = (r.get("title") or "") + " " + (r.get("body") or "") + " " + (r.get("href") or "")
                        snippets.append(t)
                return "\n".join(snippets) if snippets else None
            except Exception:
                return None

        def _do_html_search():
            try:
                import requests
                from urllib.parse import quote
                r = requests.get(
                    f"https://html.duckduckgo.com/html/?q={quote(web_q)}",
                    timeout=4, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
                if r.status_code in (200, 202):
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(r.text, "html.parser")
                    snippets = [a.get_text(strip=True) for a in soup.select("a.result__a, .result__snippet") if a.get_text(strip=True)]
                    return "\n".join(snippets[:10]) if snippets else None
            except Exception:
                pass
            return None

        def _do_dir_checks(n):
            results = []
            dirs = {
                "Truecaller": f"https://truecaller.com/search/in/+{n}",
                "Sync.me": f"https://sync.me/search/?number={n}",
                "Signal": f"https://signal.me/#p/+{n}",
            }
            import requests as _req
            for label, url in dirs.items():
                try:
                    r = _req.get(url, timeout=2, allow_redirects=True)
                    if r.status_code == 200:
                        b = r.text.lower()[:500]
                        if not any(x in b for x in ["not found", "doesn't exist", "no results"]):
                            results.append(f"[URL EXISTS] {label}: {url}")
                except Exception:
                    pass
            return results

        text = ""
        with _cf.ThreadPoolExecutor(max_workers=4) as ex:
            wa_fut = ex.submit(_do_wa)
            search_fut = ex.submit(_do_ddgs)
            dir_fut = ex.submit(_do_dir_checks, raw_num)

            try:
                wa_result = wa_fut.result(timeout=4)
                if wa_result:
                    mods["whatsapp"] = wa_result
            except Exception:
                pass

            try:
                ddgs_text = search_fut.result(timeout=10)
                text = ddgs_text if ddgs_text else ""
            except Exception:
                pass
            if not text:
                text = _do_html_search() or ""

            try:
                dir_results = dir_fut.result(timeout=8)
                if dir_results:
                    mods["profile_links"] = dir_results
            except Exception:
                pass

        emails = set(_re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text))
        emails -= {"example.com", "domain.com"}
        if emails:
            mods["linked_emails"] = sorted(emails)[:10]

        digits_variant = raw_num[1:] if raw_num.startswith("+") else raw_num
        try:
            digits_username_check = self._check_username(digits_variant)
            if digits_username_check:
                mods["username_check"] = digits_username_check
        except Exception:
            pass

        mods["parsed_info"]["searched"] = search_term
        self.results["modules"] = mods

    def _harvest_domain(self, domain):
        info = {}
        subs = set()
        sources = [
            (f"https://crt.sh/?q=%25.{domain}&output=json", True),
            (f"https://api.hackertarget.com/hostsearch/?q={domain}", False),
            (f"https://webarchive.subdomainfinder.c99.nl/api/query/{domain}", False),
        ]
        for url, is_json in sources:
            try:
                import requests as _req
                r = _req.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code == 200 and r.text.strip():
                    if is_json:
                        try:
                            for entry in r.json():
                                name = entry.get("name_value", "")
                                for n in name.split("\n"):
                                    n = n.strip().lower()
                                    if n.endswith(domain) and n != domain:
                                        subs.add(n)
                        except Exception:
                            pass
                    else:
                        for line in r.text.split("\n"):
                            line = line.strip().lower()
                            if "," in line:
                                line = line.split(",")[0]
                            if line.endswith(domain) and line != domain and "." in line:
                                subs.add(line)
                    if subs:
                        break
            except Exception:
                pass
        if subs:
            info["subdomains"] = sorted(subs)[:30]
        try:
            import requests as _req
            from urllib.parse import quote
            q = quote(f"@{domain} email OR contact")
            r = _req.get(f"https://html.duckduckgo.com/html/?q={q}", timeout=5,
                headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code in (200, 202):
                from bs4 import BeautifulSoup as _BS
                soup = _BS(r.text, "html.parser")
                emails = set()
                for a in soup.select("a.result__a"):
                    txt = a.get_text(strip=True) + " " + str(a.parent.get_text(strip=True))
                    found = re.findall(r"[a-zA-Z0-9._%+-]+@" + re.escape(domain), txt)
                    emails.update(found)
                if emails:
                    info["harvested_emails"] = sorted(emails)[:20]
        except Exception:
            pass
        return info

    def _cross_reference(self):
        mods = self.results.get("modules", {})
        target = self.results.get("target", "")
        refs = {}
        is_batch = self.results.get("type") == "batch"

        all_emails = set()
        all_phones = set()
        all_usernames = set()

        if is_batch:
            indiv = mods.pop("_individual_targets", [])
            for t in indiv:
                if re.match(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$", t):
                    all_emails.add(t.lower())
                elif self._is_phone(t):
                    all_phones.add(re.sub(r"\D", "", t))
                else:
                    all_usernames.add(t.lower())
        else:
            if re.match(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$", target):
                all_emails.add(target.lower())
            if self._is_phone(target):
                all_phones.add(re.sub(r"\D", "", target))
            if not self._is_phone(target) and not re.match(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$", target) and not target.startswith("http"):
                all_usernames.add(target.lower())

        for k, v in mods.items():
            if v:
                if k == "linked_emails" and isinstance(v, list):
                    for e in v:
                        if isinstance(e, str) and "@" in e:
                            all_emails.add(e.lower())
                if k == "harvested_emails" and isinstance(v, list):
                    for e in v:
                        if isinstance(e, str) and "@" in e:
                            all_emails.add(e.lower())
                if k == "linked_phones" and isinstance(v, list):
                    for p in v:
                        if isinstance(p, str):
                            all_phones.add(re.sub(r"\D", "", p))
                if k == "parsed_info" and isinstance(v, dict):
                    e164 = v.get("e164", "")
                    if e164:
                        all_phones.add(re.sub(r"\D", "", e164))
                if k == "username_check" and isinstance(v, list):
                    for entry in v:
                        if isinstance(entry, str) and "]" in entry:
                            label = entry.split("]")[0].lstrip("[")
                            if label not in ("FOUND", "URL EXISTS"):
                                continue
                            url_part = entry.split("https://", 1)
                            if len(url_part) > 1:
                                path = url_part[1].split("/", 1)
                                if len(path) > 1:
                                    user_part = path[1].split("?")[0].split("#")[0]
                                    user_part = user_part.lstrip("@").lstrip("/")
                                    user_part = re.sub(r"^(user|id|add)/", "", user_part)
                                    if user_part and not user_part.startswith(("search", "web", "explore", "settings", "about", "help", "add")):
                                        all_usernames.add(user_part.lower()[:30])
                if k == "linked_usernames" and isinstance(v, list):
                    for u in v:
                        if isinstance(u, str):
                            clean = re.sub(r"^\[.*?\]\s*", "", u).strip()
                            if "https://" in clean:
                                m = re.search(r"https://[^/\s]+/(?:user/|id/|@)?([a-zA-Z0-9._-]+)", clean)
                                if m:
                                    candidate = m.group(1).lower()[:30]
                                    if candidate not in ("add", "search", "login", "signup", "about", "help"):
                                        all_usernames.add(candidate)
                            elif clean and clean not in ("add", "search", "login", "signup"):
                                all_usernames.add(clean.lower()[:30])

        overlaps = {}
        if all_emails:
            overlaps["emails"] = sorted(all_emails)
        if all_phones:
            overlaps["phones"] = sorted(all_phones)
        if all_usernames:
            overlaps["usernames"] = sorted(all_usernames)

        common = {}
        for u in list(all_usernames):
            for p in list(all_phones):
                if u == p:
                    common.setdefault("phone_as_username", []).append(u)
            for e in list(all_emails):
                local = e.split("@")[0]
                if u == local:
                    common.setdefault("username_matches_email_local", []).append(u)
        for e in list(all_emails):
            local = e.split("@")[0]
            for p in list(all_phones):
                if local == p or re.sub(r"\D", "", local) == p:
                    common.setdefault("phone_in_email", []).append(e)

        if common:
            refs["associations"] = common
        refs["all"] = {k: v for k, v in overlaps.items() if v is not None}
        return refs if refs.get("all") else None

    def _fetch_profile_pics(self):
        mods = self.results.get("modules", {})
        seen_urls = set()
        urls_to_try = []
        for k in ("username_check", "profile_links", "platform_presence", "social_linking"):
            data = mods.get(k, [])
            if isinstance(data, list):
                for entry in data:
                    m = re.search(r"https?://[^\s]+", str(entry))
                    if m:
                        url = m.group(0).rstrip(")")
                        if url not in seen_urls:
                            seen_urls.add(url)
                            urls_to_try.append(url)

        platform_map = {
            "instagram.com": "instagram",
            "facebook.com": "facebook",
            "github.com": "github",
            "twitter.com": "twitter",
            "x.com": "x",
            "reddit.com": "reddit",
            "tiktok.com": "tiktok",
            "pinterest.com": "pinterest",
            "medium.com": "medium",
            "linkedin.com": "linkedin",
            "twitch.tv": "twitch",
            "telegram.org": "telegram",
            "t.me": "telegram",
            "youtube.com": "youtube",
        }

        target_slug = re.sub(r"[^\w]", "_", self.results.get("target", "unknown")).strip("_")[:40] or "unknown"

        import concurrent.futures as _cf

        def _fetch_one(url):
            for domain, pfx in platform_map.items():
                if domain in url.lower():
                    matched = pfx
                    break
            else:
                return None
            import requests as _req
            try:
                r = _req.get(url, timeout=4, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True)
                if r.status_code != 200:
                    return None
                from bs4 import BeautifulSoup as _BS
                soup = _BS(r.text, "html.parser")
                img_url = None
                for tag in soup.select("meta[property='og:image'], meta[name='twitter:image']"):
                    c = tag.get("content", "")
                    if c:
                        img_url = c
                        break
                if not img_url:
                    if matched == "github":
                        for img in soup.select("img.avatar-user, img.avatar"):
                            s = img.get("src", "")
                            if s:
                                img_url = s if s.startswith("http") else ("https:" + s) if s.startswith("//") else None
                                break
                if not img_url:
                    for img in soup.select("img[src*='avatar'], img[class*='avatar']"):
                        s = img.get("src", "")
                        if s:
                            img_url = s if s.startswith("http") else None
                            break
                if not img_url:
                    m = re.search(r'<img[^>]+src=["\']([^"\']+(?:avatar|profile|photo)[^"\']+)["\']', r.text, re.I)
                    if m:
                        s = m.group(1)
                        img_url = s if s.startswith("http") else None
                if not img_url:
                    return None
                if img_url.startswith("//"):
                    img_url = "https:" + img_url
                if not img_url.startswith("http"):
                    return None

                img_r = _req.get(img_url, timeout=4, headers={"User-Agent": "Mozilla/5.0"})
                if img_r.status_code != 200 or len(img_r.content) < 200:
                    return None

                ext = img_url.split("?")[0].rsplit(".", 1)[-1]
                ext = ext[:5] if ext and len(ext) <= 5 and ext.isalpha() else "jpg"
                fname = f"{target_slug}_{matched}.{ext}"
                dest = self.session_dir / fname if self.session_dir else PICDATA_DIR / fname
                with open(dest, "wb") as f:
                    f.write(img_r.content)
                return {"platform": matched, "source_url": url, "local_file": str(dest.resolve()), "size": len(img_r.content)}
            except Exception:
                return None

        pics = []
        with _cf.ThreadPoolExecutor(max_workers=5) as ex:
            for result in ex.map(_fetch_one, urls_to_try):
                if result:
                    pics.append(result)
        return pics if pics else None

    def gather_batch(self, targets):
        results = {}
        all_mods = {}
        individual_targets = []
        for t in targets:
            t = t.strip()
            if not t:
                continue
            individual_targets.append(t)
            r = self.gather(t)
            results[t] = {k: v for k, v in r.get("modules", {}).items() if k not in ("cross_reference", "profile_pics")}
            for k, v in results[t].items():
                if v:
                    if k not in all_mods:
                        all_mods[k] = v if isinstance(v, (list, dict)) else [v]
                    else:
                        if isinstance(all_mods[k], list) and isinstance(v, list):
                            all_mods[k].extend(v)
                        elif isinstance(all_mods[k], dict) and isinstance(v, dict):
                            all_mods[k].update(v)
        all_mods["_individual_targets"] = individual_targets
        batch_ref = {"type": "batch", "individual": results}
        batch_ref["modules"] = all_mods
        batch_ref["target"] = " | ".join(targets)
        batch_ref["timestamp"] = datetime.now().isoformat()
        batch_ref["session_dir"] = str(self.session_dir) if self.session_dir else ""
        self.results = batch_ref
        xr = self._cross_reference()
        if xr:
            self.results["modules"]["cross_reference"] = xr
        return self.results

    def gather(self, target):
        target = target.strip()
        self._init_session()
        self.results = {"target": target, "timestamp": datetime.now().isoformat(), "session_dir": str(self.session_dir) if self.session_dir else "", "modules": {}}

        ip_match = re.match(r"^(\d{1,3}\.){3}\d{1,3}$", target)
        domain_match = False
        raw_domain_match = re.match(r"^([a-zA-Z0-9-]+\.)+([a-zA-Z]{2,})$", target)
        if raw_domain_match:
            tld = raw_domain_match.group(2).lower()
            if tld in KNOWN_TLDS:
                domain_match = True
            else:
                try:
                    socket.getaddrinfo(target, 0, socket.AF_UNSPEC, socket.SOCK_STREAM)
                    domain_match = True
                except Exception:
                    pass
        email_match = re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", target)
        url_match = re.match(r"^https?://", target)
        phone_match = self._is_phone(target)

        if phone_match:
            self.results["type"] = "phone"
            self._gather_phone(phone_match)
        elif email_match:
            self.results["type"] = "email"
            self._gather_email(target)
            domain = target.split("@")[1] if "@" in target else ""
            if domain:
                hv = self._harvest_domain(domain)
                for k, v in hv.items():
                    if v:
                        self.results["modules"][k] = v
        elif url_match:
            self.results["type"] = "url"
            self.results["modules"]["web_analysis"] = self._web_extract_links(target)
            self.results["modules"]["tech_detect"] = self._tech_detect(target)
        elif domain_match:
            self.results["type"] = "domain"
            self._gather_domain(target)
            hv = self._harvest_domain(target)
            for k, v in hv.items():
                if v:
                    self.results["modules"][k] = v
        else:
            self.results["type"] = "username"
            self.results["modules"]["username_check"] = self._check_username(target)
            web_text = self._email_web_search(target)
            if web_text:
                combined = "\n".join(web_text)
                phone_mentions = self._extract_phones_from_text(combined)
                if phone_mentions:
                    self.results["modules"]["linked_phones"] = phone_mentions
                found_emails = set(re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", combined))
                found_emails -= {"example.com", "domain.com"}
                if found_emails:
                    self.results["modules"]["linked_emails"] = sorted(found_emails)[:10]

        self._enrich_identity()

        xr = self._cross_reference()
        if xr:
            self.results["modules"]["cross_reference"] = xr

        pics = self._fetch_profile_pics()
        if pics:
            self.results["modules"]["profile_pics"] = pics

        self._persist_results()

        return self.results

    def _enrich_identity(self):
        mods = self.results.get("modules", {})
        target = self.results.get("target", "")
        ttype = self.results.get("type", "")

        discovered_emails = set()
        discovered_phones = set()
        discovered_usernames = set()

        all_web_text = ""

        if ttype == "email":
            local = target.split("@")[0]
            discovered_usernames.add(local)
            discover_username_on_platforms = self._check_username(local)
            if discover_username_on_platforms:
                existing = mods.get("linked_usernames", [])
                mods["linked_usernames"] = list(dict.fromkeys(existing + discover_username_on_platforms))
            wr = self._email_web_search(local)
            if wr:
                all_web_text = "\n".join(wr)
        elif ttype == "phone":
            digits = re.sub(r"\D", "", target)
            digits = digits[1:] if digits.startswith("+") else digits
            discovered_usernames.add(digits)
        elif ttype == "username":
            wr = self._email_web_search(target)
            if wr:
                all_web_text = "\n".join(wr)

        if all_web_text:
            found_emails = set(re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", all_web_text))
            found_emails -= {"example.com", "domain.com"}
            if found_emails:
                key = "linked_emails"
                mods[key] = list(dict.fromkeys(mods.get(key, []) + sorted(found_emails)[:8]))
            found_phones = self._extract_phones_from_text(all_web_text)
            if found_phones:
                key = "linked_phones"
                mods[key] = list(dict.fromkeys(mods.get(key, []) + found_phones))
            exclude_set = {target.lower()}
            if ttype == "phone":
                exclude_set.add(re.sub(r"\D", "", target))
            elif ttype == "email":
                exclude_set.add(target.split("@")[0].lower())
            found_extra = set(re.findall(r'(?:instagram\.com/|x\.com/|twitter\.com/|github\.com/|t\.me/|reddit\.com/user/|facebook\.com/)([a-zA-Z][a-zA-Z0-9._]{3,40})', all_web_text.lower()))
            found_extra -= exclude_set
            found_extra = {u for u in found_extra if len(u) > 3 and u != target.lower()}
            if found_extra:
                mods["linked_usernames"] = list(dict.fromkeys(mods.get("linked_usernames", []) +
                    sorted(f"[CROSS] {u}" for u in found_extra)[:8]))

        for k, v in mods.items():
            if k == "linked_emails" and isinstance(v, list):
                for e in v:
                    if isinstance(e, str) and "@" in e:
                        discovered_emails.add(e.lower())
            if k == "linked_phones" and isinstance(v, list):
                for p in v:
                    if isinstance(p, str):
                        discovered_phones.add(re.sub(r"\D", "", p))
            if k == "username_check" and isinstance(v, list):
                for entry in v:
                    if isinstance(entry, str) and "]" in entry:
                        parts = entry.split("https://", 1)
                        if len(parts) > 1:
                            path = parts[1].split("/", 1)
                            if len(path) > 1:
                                u = path[1].split("?")[0].lstrip("@").lstrip("/")
                                if u and len(u) > 2:
                                    discovered_usernames.add(u.lower()[:30])

        self.results["enriched"] = {
            "emails": sorted(discovered_emails)[:10] if discovered_emails else None,
            "phones": sorted(discovered_phones)[:10] if discovered_phones else None,
            "usernames": sorted(discovered_usernames)[:15] if discovered_usernames else None,
        }
        self.results["modules"] = mods

    def _persist_results(self):
        target = self.results.get("target", "")
        target_type = self.results.get("type", "unknown")
        session_tag = self.session_dir.name if self.session_dir else datetime.now().strftime("%Y%m%d_%H%M%S")

        try:
            from grid_db import GridDB
            db = GridDB()
            db.conn.execute("""
                CREATE TABLE IF NOT EXISTS picdata (
                    id INTEGER PRIMARY KEY,
                    session_id VARCHAR,
                    target VARCHAR,
                    target_type VARCHAR,
                    platform VARCHAR,
                    source_url VARCHAR,
                    local_path VARCHAR,
                    file_size INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            db.conn.execute("CREATE SEQUENCE IF NOT EXISTS seq_picdata START 1")

            pics = self.results.get("modules", {}).get("profile_pics", [])
            for p in pics:
                db.conn.execute("""
                    INSERT INTO picdata (id, session_id, target, target_type, platform, source_url, local_path, file_size)
                    VALUES (nextval('seq_picdata'), ?, ?, ?, ?, ?, ?, ?)
                """, [session_tag, target, target_type, p.get("platform",""),
                      p.get("source_url",""), p.get("local_file",""), p.get("size",0)])

            summary_text = self.summary()[:2000]
            db.conn.execute("""
                INSERT INTO tool_logs (id, session_id, tool_name, tool_input, tool_output, duration_ms, status)
                VALUES (nextval('seq_tool_logs'), ?, 'osint', ?, ?, 0, 'completed')
            """, [session_tag, target[:500], summary_text])
        except Exception:
            pass

        try:
            from grid_pb import PocketBaseManager
            pb = PocketBaseManager()
            if pb.is_running():
                pb._post_init()
                pics = self.results.get("modules", {}).get("profile_pics", [])
                for p in pics:
                    f = p.get("local_file", "")
                    if f and os.path.isfile(f):
                        pb.upload_artifact(f, label=f"osint_{p.get('platform','')}_{target[:30]}", session_id=session_tag)
        except Exception:
            pass

    def _gather_domain(self, domain):
        mods = {}

        dns = self._dns_query(domain)
        mods["dns_a"] = dns

        cert = self._get_cert_info(domain)
        if cert:
            mods["ssl_cert"] = cert

        subs = self._crt_sh_subdomains(domain)
        if subs:
            mods["subdomains"] = subs

        tech = self._tech_detect(f"https://{domain}")
        if tech:
            mods["tech_stack"] = tech

        web = self._web_extract_links(f"https://{domain}")
        if web:
            mods["web_info"] = web

        self.results["modules"] = mods

    def _gather_ip(self, ip):
        mods = {}

        geo = self._ip_geolocation(ip)
        if geo:
            mods["geolocation"] = geo

        try:
            hostname, _, _ = socket.gethostbyaddr(ip)
            mods["reverse_dns"] = hostname
        except socket.herror:
            mods["reverse_dns"] = "No PTR record"

        self.results["modules"] = mods

    def _check_gravatar(self, email):
        import hashlib
        h = hashlib.md5(email.lower().encode()).hexdigest()
        url = f"https://www.gravatar.com/{h}.json"
        try:
            import requests
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                data = r.json()
                entries = data.get("entry", [])
                if entries:
                    prof = entries[0]
                    info = {}
                    if prof.get("displayName"):
                        info["name"] = prof["displayName"]
                    if prof.get("thumbnailUrl"):
                        info["avatar"] = prof["thumbnailUrl"]
                    if prof.get("urls"):
                        info["profiles"] = [u["value"] for u in prof["urls"][:5]]
                    if prof.get("aboutMe"):
                        info["about"] = prof["aboutMe"][:200]
                    if prof.get("currentLocation"):
                        info["location"] = prof["currentLocation"]
                    return info
        except Exception:
            pass
        return None

    def _mx_lookup(self, domain):
        try:
            import subprocess
            r = subprocess.run(["nslookup", "-type=MX", domain],
                               capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                lines = r.stdout.split("\n")
                mx = [l.strip() for l in lines if "mail exchanger" in l.lower()]
                return mx if mx else None
        except Exception:
            pass
        return None

    @staticmethod
    def _filter_web_result(title, href, query_words):
        if not query_words:
            return True
        text = (title + " " + href).lower()
        return sum(1 for w in query_words if w in text) >= 1

    @staticmethod
    def _significant_words(text):
        stopwords = {
            "the","a","an","is","it","of","to","in","and","for","on","with",
            "at","by","from","as","be","are","was","were","has","have","had",
            "not","no","or","but","so","if","do","did","will","would","can",
            "could","should","may","might","all","each","every","its","this",
            "that","these","those","some","any","both","which","what","who",
            "how","when","where","why","about","into","than","then","also",
            "just","more","very","here","there","only","other","another",
            "search","query","results","site","filetype","inurl","intitle",
            "intext","ext","page","link","www","http","https","com","org",
        }
        words = re.findall(r"[a-zA-Z][a-zA-Z0-9]{2,}", text.lower())
        return [w for w in words if w not in stopwords and len(w) >= 3][:8]

    def _email_web_search(self, query):
        qwords = self._significant_words(query)
        try:
            from ddgs import DDGS
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=6):
                    title = (r.get("title") or "")[:100]
                    href = (r.get("href") or "")[:120]
                    body = (r.get("body") or "")[:100]
                    if title and href and self._filter_web_result(title, href, qwords):
                        results.append(f"{title} - {href}")
                    if len(results) >= 5:
                        break
            if results:
                return results
        except Exception:
            pass
        try:
            import requests
            from urllib.parse import quote
            q = quote(query)
            r = requests.get(
                f"https://html.duckduckgo.com/html/?q={q}",
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
                timeout=5,
            )
            if r.status_code in (200, 202):
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(r.text, "html.parser")
                results = []
                for a in soup.select("a.result__a"):
                    href = a.get("href", "")
                    text = a.get_text(strip=True)
                    if text and href and self._filter_web_result(text, href, qwords):
                        results.append(f"{text[:100]} - {href[:120]}")
                    if len(results) >= 5:
                        break
                if results:
                    return results
        except Exception:
            pass
        return None

    def _email_breach_search(self, email, domain):
        try:
            import requests
            from bs4 import BeautifulSoup
            q = f"{email} breach OR leak OR compromised OR exposed"
            from urllib.parse import quote
            r = requests.get(
                f"https://html.duckduckgo.com/html/?q={quote(q)}",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=8,
            )
            soup = BeautifulSoup(r.text, "html.parser")
            results = []
            for a in soup.select("a.result__a"):
                text = a.get_text(strip=True)
                href = a.get("href", "")
                if text and href:
                    results.append(f"{text[:100]} - {href[:120]}")
                if len(results) >= 4:
                    break
            return results if results else None
        except Exception:
            return None

    def _email_domain_breach_check(self, domain):
        try:
            import requests
            r = requests.get(f"https://haveibeenpwned.com/api/v3/breaches?domain={domain}", timeout=8)
            if r.status_code == 200:
                breaches = r.json()
                if breaches:
                    return [{"name": b["Name"], "date": b.get("BreachDate","?"), "count": b.get("PwnCount","?"),
                             "data": b.get("DataClasses",[])} for b in breaches[:8]]
        except Exception:
            pass
        return None

    def _emailrep_check(self, email):
        try:
            import requests
            r = requests.get(f"https://emailrep.io/{email}",
                             headers={"User-Agent": "Mozilla/5.0"},
                             timeout=8)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return None

    def _check_platform_profile(self, platform, url, not_found_hints=None):
        not_found_hints = not_found_hints or [
            "not found", "page not found", "doesn't exist", "this page doesn't exist",
            "sorry, this page", "couldn't find", "no user", "user not found",
            "profile not found", "this account doesn't exist", "the link you followed",
            "redirected you", "no results found", "isn't available", "something went wrong",
            "sign up", "create an account", "join facebook", "log in", "sign in",
        ]
        try:
            import requests as req
            r = req.get(url, timeout=5, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                body = r.text.lower()[:2000]
                for hint in not_found_hints:
                    if hint in body:
                        return None
                final_url = r.url.lower()
                if final_url != url.lower():
                    for hint in ["search", "login", "signup", "home", "explore", "notfound"]:
                        if hint in final_url:
                            return None
                return f"[{platform}] {url}"
        except Exception:
            pass
        return None

    def _platform_email_search(self, email, local_part):
        results = []
        import requests as req

        for variant in set([local_part, local_part.replace(".", ""), local_part.replace(".", "-")]):
            try:
                r = req.get(f"https://api.github.com/users/{variant}", timeout=5,
                            headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code == 200:
                    results.append(f"[GITHUB] user '{variant}' at https://github.com/{variant}")
                    break
            except Exception:
                pass
        try:
            r = req.get(f"https://www.reddit.com/user/{local_part.replace('.','_')}/about.json", timeout=5,
                        headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                results.append(f"[REDDIT] https://reddit.com/user/{local_part.replace('.','_')}")
        except Exception:
            pass
        try:
            r = req.get(f"https://api.github.com/search/users?q={email}", timeout=5,
                        headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                data = r.json()
                if data.get("total_count", 0) > 0:
                    for u in data["items"][:3]:
                        results.append(f"[GITHUB EMAIL] {u['login']} — https://github.com/{u['login']}")
        except Exception:
            pass
        try:
            r = req.get(f"https://haveibeenpwned.com/api/v3/breachedaccount/{email}", timeout=5)
            if r.status_code == 200:
                for b in r.json()[:5]:
                    results.append(f"[BREACH] {b['Name']} ({b.get('BreachDate','?')})")
        except Exception:
            pass

        platform_checks = {
            "Facebook":  f"https://facebook.com/{local_part}",
            "Twitter/X": f"https://x.com/{local_part}",
            "Instagram": f"https://instagram.com/{local_part}",
            "TikTok":    f"https://tiktok.com/@{local_part}",
            "Telegram":  f"https://t.me/{local_part}",
            "YouTube":   f"https://youtube.com/@{local_part}",
            "Twitch":    f"https://twitch.tv/{local_part}",
            "Medium":    f"https://medium.com/@{local_part}",
            "VK":        f"https://vk.com/{local_part}",
            "Steam":     f"https://steamcommunity.com/id/{local_part}",
        }
        for platform, url in platform_checks.items():
            result = self._check_platform_profile(platform, url)
            if result:
                results.append(result)

        return results if results else None

    def _gather_email(self, email):
        mods = {}
        _name, domain = parseaddr(email)[1].split("@", 1) if "@" in parseaddr(email)[1] else ("", "")
        if domain:
            mods["domain"] = domain
            dns = self._dns_query(domain)
            mods["domain_dns"] = dns
            mx = self._mx_lookup(domain)
            if mx:
                mods["mx_records"] = mx

        grav = self._check_gravatar(email)
        if grav:
            mods["gravatar"] = grav

        local_part = email.split("@")[0]
        mods["pattern_analysis"] = {
            "local_part": local_part,
            "length": len(local_part),
            "has_numbers": any(c.isdigit() for c in local_part),
            "has_dots": "." in local_part,
            "has_underscores": "_" in local_part,
            "likely_format": self._guess_email_format(local_part),
        }

        web_mentions = self._email_web_search(email)
        if web_mentions:
            mods["web_mentions"] = web_mentions

        domain_breaches = self._email_domain_breach_check(domain)
        if domain_breaches:
            mods["domain_breaches"] = domain_breaches

        breach_search = self._email_breach_search(email, domain)
        if breach_search:
            mods["breach_search_results"] = breach_search

        erep = self._emailrep_check(email)
        if erep:
            mods["emailrep"] = erep

        platform = self._platform_email_search(email, local_part)
        if platform:
            mods["platform_presence"] = platform

        all_text = ""
        for v in mods.values():
            if isinstance(v, str):
                all_text += v + "\n"
            elif isinstance(v, list):
                all_text += "\n".join(str(x) for x in v) + "\n"
            elif isinstance(v, dict):
                all_text += "\n".join(str(x) for x in v.values()) + "\n"
        found_phones = self._extract_phones_from_text(all_text)
        if found_phones:
            mods["linked_phones"] = found_phones

        self.results["modules"] = mods

    def _guess_email_format(self, local):
        if "." in local:
            parts = local.split(".")
            if len(parts) == 2 and all(p.isalpha() for p in parts):
                return "firstname.lastname"
        if "_" in local:
            return "firstname_lastname"
        if local.isalpha():
            return "single_name"
        if any(c.isdigit() for c in local):
            return "likely_username_with_numbers"
        return "username"

    def _table(self, headers, rows, title=""):
        def esc(v):
            return str(v).replace("|", "\\|").replace("\n", " ")[:120]
        parts = [f"| {' | '.join(esc(h) for h in headers)} |"]
        parts.append(f"| {' | '.join('---' for _ in headers)} |")
        for r in rows:
            parts.append(f"| {' | '.join(esc(c) for c in r)} |")
        return "\n".join(parts)

    def summary(self):
        t = self.results.get("type", "unknown")
        target = self.results["target"]
        mods = self.results.get("modules", {})

        if t == "batch":
            lines = [f"OSINT BATCH: {target}", ""]
            indiv = self.results.get("individual", {})
            for i_label, i_mods in indiv.items():
                summary_line = f"  {i_label}: " + ", ".join(f"{k}({len(v) if isinstance(v,list) else 1})" for k, v in i_mods.items() if v)
                lines.append(summary_line)
            lines.append("")
        else:
            lines = [f"OSINT {t.upper()}: {target}", ""]

        for mod_name, data in mods.items():
            if not data:
                continue

            if mod_name == "dns_a" or mod_name == "domain_dns":
                rows = []
                entries = data if isinstance(data, list) else [data]
                for entry in entries[:8]:
                    if isinstance(entry, dict) and "error" in entry:
                        rows.append(["Error", entry["error"]])
                    else:
                        parts = str(entry).split(": ", 1)
                        rows.append([parts[0] if len(parts) > 1 else "IP", parts[-1]])
                if rows:
                    lines.append(self._table(["Type", "Address"], rows, "DNS Records"))
                    lines.append("")
                continue

            if mod_name == "mx_records":
                rows = []
                for mx in data:
                    m = re.search(r"MX preference = (\d+), mail exchanger = (.+)", mx)
                    if m:
                        rows.append([m.group(1), m.group(2)])
                if rows:
                    lines.append(self._table(["Priority", "Mail Server"], rows, "MX Records"))
                    lines.append("")
                continue

            if mod_name == "subdomains":
                rows = [[s] for s in data]
                if rows:
                    label = f"Subdomains ({len(data)} found)"
                    lines.append(self._table(["Subdomain"], rows, label))
                    lines.append("")
                continue

            if mod_name == "tech_stack":
                rows = [[t] for t in data]
                lines.append(self._table(["Technology"], rows, "Tech Stack"))
                lines.append("")
                continue

            if mod_name == "geolocation":
                rows = [
                    ["Location", f"{data.get('city','?')}, {data.get('regionName','?')}, {data.get('country','?')}"],
                    ["ISP", data.get('isp','?')],
                    ["Organization", data.get('org','?')],
                    ["Hosting", str(data.get('hosting','?'))],
                ]
                lines.append(self._table(["Property", "Value"], rows, "Geolocation"))
                lines.append("")
                continue

            if mod_name == "ssl_cert":
                sans = data.get("sans", [])
                sans_str = ", ".join(s[1] for s in sans[:5]) if sans else "N/A"
                rows = [
                    ["Subject CN", data.get('subject', {}).get('commonName', 'N/A')],
                    ["Issuer", data.get('issuer', {}).get('organizationName', 'N/A')],
                    ["Valid From", str(data.get('not_before','')[:10])],
                    ["Valid Until", str(data.get('not_after','')[:10])],
                    ["SANs", sans_str],
                ]
                lines.append(self._table(["Property", "Value"], rows, "SSL Certificate"))
                lines.append("")
                continue

            if mod_name == "web_info":
                rows = [
                    ["Title", data.get('title','?')[:80]],
                    ["Description", data.get('description','N/A')[:80]],
                    ["Links Found", str(len(data.get('links',[])))],
                    ["Content Size", f"{data.get('text_length',0)} chars"],
                ]
                lines.append(self._table(["Property", "Value"], rows, "Web Info"))
                lines.append("")
                continue

            if mod_name == "subdomains":
                rows = [[s] for s in data]
                label = f"Discovered Subdomains ({len(data)})"
                lines.append(self._table(["Subdomain"], rows, label))
                lines.append("")
                continue

            if mod_name == "harvested_emails":
                rows = [[e] for e in data]
                lines.append(self._table(["Email"], rows, f"Harvested Emails ({len(data)})"))
                lines.append("")
                continue

            if mod_name == "linked_phones":
                rows = [[p] for p in data]
                lines.append(self._table(["Phone (E.164)"], rows, "Linked Phone Numbers"))
                lines.append("")
                continue

            if mod_name == "linked_emails":
                rows = [[e] for e in data]
                lines.append(self._table(["Email"], rows, "Linked Emails"))
                lines.append("")
                continue

            if mod_name == "linked_usernames":
                rows = [[u] for u in data]
                lines.append(self._table(["Username"], rows, "Linked Usernames"))
                lines.append("")
                continue

            if mod_name == "profile_links":
                rows = [[p] for p in data[:10]]
                lines.append(self._table(["Directory Link"], rows, "Phone Directories"))
                lines.append("")
                continue

            if mod_name == "gravatar":
                rows = [["Name", data.get('name','unknown')]]
                if data.get("location"):
                    rows.append(["Location", data["location"]])
                if data.get("about"):
                    rows.append(["About", data["about"][:120]])
                if data.get("profiles"):
                    for p in data["profiles"]:
                        rows.append(["Profile", p])
                lines.append(self._table(["Property", "Value"], rows, "Gravatar"))
                lines.append("")
                continue

            if mod_name == "pattern_analysis":
                rows = [
                    ["Local Part", data.get('local_part','')],
                    ["Format Guess", data.get('likely_format','?')],
                    ["Has Numbers", str(data.get('has_numbers',False))],
                    ["Has Dots", str(data.get('has_dots',False))],
                ]
                lines.append(self._table(["Property", "Value"], rows, "Email Pattern"))
                lines.append("")
                continue

            if mod_name == "domain_breaches":
                rows = []
                for b in data:
                    rows.append([b['name'], str(b.get('date','?')),
                                 f"{b.get('count','?'):,}", ", ".join(b.get('data',[])[:3])])
                lines.append(self._table(["Breach", "Date", "Records", "Data Exposed"], rows,
                                         f"Domain Breaches ({len(data)} found)"))
                lines.append("")
                continue

            if mod_name == "social_linking":
                rows = [[l] for l in data[:8]]
                lines.append(self._table(["Finding"], rows, "Social Links"))
                lines.append("")
                continue

            if mod_name == "web_mentions":
                rows = [[m] for m in data[:6]]
                lines.append(self._table(["Mention"], rows, "Web Mentions"))
                lines.append("")
                continue

            if mod_name == "breach_search_results":
                rows = [[m] for m in data[:4]]
                lines.append(self._table(["Result"], rows, "Breach Search"))
                lines.append("")
                continue

            if mod_name == "parsed_info":
                rows = [
                    ["Country", data.get("country", "?")],
                    ["Country Code", data.get("country_code", "?")],
                    ["National Format", data.get("national_format", "?")],
                    ["International", data.get("international_format", "?")],
                    ["E.164", data.get("e164", "?")],
                    ["Type", data.get("type", "?")],
                ]
                if data.get("carrier"):
                    rows.append(["Carrier", data["carrier"]])
                if data.get("location"):
                    rows.append(["Location", data["location"]])
                lines.append(self._table(["Property", "Value"], rows, "Phone Info"))
                lines.append("")
                continue

            if mod_name == "whatsapp":
                lines.append(self._table(["Result"], [[data]], "WhatsApp Check"))
                lines.append("")
                continue

            if mod_name == "emailrep":
                rows = []
                if data.get("email"):
                    rows.append(["Email", data["email"]])
                if data.get("reputation"):
                    rows.append(["Reputation", data["reputation"]])
                if data.get("suspicious"):
                    rows.append(["Suspicious", str(data["suspicious"])])
                if data.get("details", {}).get("credentials_leaked"):
                    rows.append(["Credentials Leaked", "YES"])
                if data.get("details", {}).get("data_breach"):
                    rows.append(["Data Breach Found", "YES"])
                if data.get("details", {}).get("spam"):
                    rows.append(["Spam Activity", str(data["details"]["spam"])])
                if data.get("details", {}).get("malicious_activity"):
                    rows.append(["Malicious Activity", str(data["details"]["malicious_activity"])])
                profiles = data.get("details", {}).get("profiles", [])
                if profiles:
                    for p in profiles[:6]:
                        rows.append(["Profile", p])
                details = data.get("details", {})
                if details.get("domain_exists"):
                    rows.append(["Domain Exists", str(details["domain_exists"])])
                if details.get("domain_reputation"):
                    rows.append(["Domain Rep", details["domain_reputation"]])
                if details.get("valid_mx"):
                    rows.append(["Valid MX", str(details["valid_mx"])])
                if details.get("deliverable"):
                    rows.append(["Deliverable", str(details["deliverable"])])
                if details.get("catch_all"):
                    rows.append(["Catch-All", str(details["catch_all"])])
                if details.get("free_provider"):
                    rows.append(["Free Provider", str(details["free_provider"])])
                if rows:
                    lines.append(self._table(["Property", "Value"], rows, "EmailRep Intelligence"))
                    lines.append("")
                continue

            if mod_name == "platform_presence":
                rows = [[p] for p in data[:15]]
                lines.append(self._table(["Platform Link"], rows, "Platform Presence"))
                lines.append("")
                continue

            if mod_name == "username_check":
                rows = [[p] for p in data[:10]]
                lines.append(self._table(["Platform"], rows, f"URL Pattern Check ({len(data)} checks — may not be real profiles)"))
                lines.append("")
                continue

            if mod_name == "cross_reference":
                enriched = self.results.get("enriched", {})
                all_data = data.get("all", {})
                assocs = data.get("associations", {})
                rows = []
                for label, items in all_data.items():
                    if items:
                        rows.append([label.replace("_", " ").title(), ", ".join(items[:8])])
                if assocs:
                    for label, items in assocs.items():
                        rows.append([f">> {label.replace('_', ' ').title()}", ", ".join(items[:6])])
                for label in ("emails", "phones", "usernames"):
                    items = enriched.get(label)
                    if items and label.replace("s", "") not in all_data and label not in all_data:
                        rows.append(["Search: " + label.title(), ", ".join(items[:8])])
                if rows:
                    lines.append(self._table(["Entity", "Values"], rows, "Identity Map"))
                    lines.append("")
                continue

            if mod_name == "profile_pics":
                rows = []
                for pic in data[:10]:
                    p = pic.get("platform", "?")
                    f = pic.get("local_file", "")
                    rows.append([p, str(f)])
                lines.append(self._table(["Platform", "Saved As"], rows, "Profile Pictures"))
                lines.append("")
                continue

            if isinstance(data, list) and len(data) > 0:
                rows = [[str(x)] for x in data[:8]]
                name = mod_name.replace("_", " ").title()
                lines.append(self._table(["Value"], rows, name))
                lines.append("")
            elif isinstance(data, dict):
                if "error" in data:
                    lines.append(f"  {mod_name}: {data['error']}")
                else:
                    rows = [[k, str(v)[:80]] for k, v in data.items()]
                    name = mod_name.replace("_", " ").title()
                    lines.append(self._table(["Key", "Value"], rows, name))
                    lines.append("")
            elif data:
                lines.append(f"  {mod_name}: {data}")

        return "\n".join(lines)

    def web_search_intel(self, query):
        """Run intelligence-gathering web searches"""
        import requests
        queries = {
            "general": query,
            "site_linkedin": f"site:linkedin.com {query}",
            "site_twitter": f"site:twitter.com {query}",
            "news": f"{query} news",
            "breaches": f"{query} breach OR leak OR compromised",
        }
        results = {}
        for label, q in queries.items():
            try:
                r = requests.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": q},
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=8,
                )
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(r.text, "html.parser")
                links = []
                for a in soup.select("a.result__a"):
                    href = a.get("href", "")
                    if "://" in href:
                        links.append(f"{a.get_text(strip=True)} - {href}")
                    if len(links) >= 5:
                        break
                results[label] = links
            except Exception:
                results[label] = []
        return results
