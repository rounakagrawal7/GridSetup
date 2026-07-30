import os
import subprocess
import time
import zipfile
from pathlib import Path

import requests as _requests


class PocketBaseManager:
    SUPERUSER_COLLECTION = "_superusers"

    def __init__(self, base_url="http://127.0.0.1:8090"):
        self.base_url = base_url.rstrip("/")
        self.process = None
        self.token = None
        self.ready = False
        self.admin_email = "admin@example.com"
        self.admin_password = "change-me-password"

    def is_running(self):
        try:
            r = _requests.get(f"{self.base_url}/api/health", timeout=2)
            return r.status_code == 200
        except Exception:
            return False

    def start(self, pb_path=None):
        if self.is_running():
            self._post_init()
            return True
        if not pb_path:
            pb_path = self._find_binary()
        if not pb_path:
            return False
        return self._start_process(pb_path)

    def _find_binary(self):
        for name in ["pocketbase.exe", "pocketbase"]:
            p = Path(name)
            if p.exists():
                return str(p.absolute())
        for dir_entry in os.environ.get("PATH", "").split(os.pathsep):
            if not dir_entry.strip():
                continue
            for name in ["pocketbase.exe", "pocketbase"]:
                full = os.path.join(dir_entry.strip(), name)
                if os.path.exists(full):
                    return full
        return None

    def _get_binary_path(self):
        return self._find_binary() or "pocketbase.exe"

    def download(self):
        try:
            r = _requests.get(
                "https://api.github.com/repos/pocketbase/pocketbase/releases/latest",
                timeout=10,
            )
            r.raise_for_status()
            tag = r.json()["tag_name"]
            zip_name = f"pocketbase_{tag[1:]}_windows_amd64.zip"
            dl_url = f"https://github.com/pocketbase/pocketbase/releases/download/{tag}/{zip_name}"
            r2 = _requests.get(dl_url, stream=True, timeout=120)
            r2.raise_for_status()
            zip_path = Path("pocketbase_windows_amd64.zip")
            with open(zip_path, "wb") as f:
                for chunk in r2.iter_content(8192):
                    f.write(chunk)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(".")
            zip_path.unlink()
            return True
        except Exception:
            return False

    def _start_process(self, pb_path):
        try:
            self.process = subprocess.Popen(
                [pb_path, "serve", "--http=127.0.0.1:8090"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            for _ in range(20):
                time.sleep(0.5)
                if self.is_running():
                    self._post_init()
                    self.ready = True
                    return True
            self.stop()
            return False
        except Exception:
            return False

    def _post_init(self):
        if self._admin_auth():
            self._ensure_collections()

    def _admin_auth(self):
        endpoint = f"{self.base_url}/api/collections/{self.SUPERUSER_COLLECTION}/auth-with-password"
        for _ in range(3):
            try:
                r = _requests.post(
                    endpoint,
                    json={"identity": self.admin_email, "password": self.admin_password},
                    timeout=5,
                )
                if r.status_code == 200:
                    data = r.json()
                    self.token = data["token"]
                    return True
            except Exception:
                pass
            time.sleep(1)

        pb_bin = os.path.abspath(self._get_binary_path())
        try:
            result = subprocess.run(
                [pb_bin, "superuser", "upsert", self.admin_email, self.admin_password],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                for _ in range(5):
                    time.sleep(1)
                    try:
                        r = _requests.post(
                            endpoint,
                            json={"identity": self.admin_email, "password": self.admin_password},
                            timeout=5,
                        )
                        if r.status_code == 200:
                            data = r.json()
                            self.token = data["token"]
                            return True
                    except Exception:
                        pass
        except Exception:
            pass
        return False

    def _make_field(self, name, field_type, required=False, **kw):
        field = {"name": name, "type": field_type, "required": required, "system": False}
        field.update(kw)
        return field

    def _get_collection(self, name):
        try:
            r = _requests.get(
                f"{self.base_url}/api/collections/{name}",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=5,
            )
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return None

    def _ensure_collections(self):
        collections_defs = [
            {
                "name": "conversations",
                "type": "base",
                "fields": [
                    self._make_field("role", "text", True),
                    self._make_field("content", "text", True),
                    self._make_field("session_id", "text", True),
                    self._make_field("timestamp", "text"),
                ],
                "listRule": "",
                "viewRule": "",
                "createRule": "",
            },
            {
                "name": "artifacts",
                "type": "base",
                "fields": [
                    self._make_field("file", "file", True, maxSize=0, maxSelect=1, mimeTypes=[], thumbs=[]),
                    self._make_field("label", "text"),
                    self._make_field("session_id", "text"),
                ],
                "listRule": "",
                "viewRule": "",
                "createRule": "",
            },
            {
                "name": "settings",
                "type": "base",
                "fields": [
                    self._make_field("key", "text", True),
                    self._make_field("value", "text"),
                ],
                "listRule": "",
                "viewRule": "",
                "createRule": "",
            },
        ]
        try:
            existing = self._list_collections()
            for col in collections_defs:
                if col["name"] in existing:
                    cur = self._get_collection(col["name"])
                    if cur:
                        cur_names = {f["name"] for f in cur.get("fields", [])}
                        want_names = {f["name"] for f in col["fields"]}
                        if not want_names.issubset(cur_names):
                            _requests.delete(
                                f"{self.base_url}/api/collections/{col['name']}",
                                headers={"Authorization": f"Bearer {self.token}"},
                                timeout=5,
                            )
                            time.sleep(0.2)
                            _requests.post(
                                f"{self.base_url}/api/collections",
                                headers={"Authorization": f"Bearer {self.token}"},
                                json=col,
                                timeout=5,
                            )
                else:
                    _requests.post(
                        f"{self.base_url}/api/collections",
                        headers={"Authorization": f"Bearer {self.token}"},
                        json=col,
                        timeout=5,
                    )
        except Exception:
            pass

    def _list_collections(self):
        try:
            r = _requests.get(
                f"{self.base_url}/api/collections",
                headers={"Authorization": f"Bearer {self.token}"},
                params={"perPage": 50},
                timeout=5,
            )
            if r.status_code == 200:
                return [c["name"] for c in r.json()["items"]]
        except Exception:
            pass
        return []

    def sync_conversation(self, role, content, session_id):
        if not self.token:
            return
        try:
            _requests.post(
                f"{self.base_url}/api/collections/conversations/records",
                headers={"Authorization": f"Bearer {self.token}"},
                json={
                    "role": role,
                    "content": content,
                    "session_id": session_id,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                },
                timeout=5,
            )
        except Exception:
            pass

    def sync_memory(self, history, session_id):
        for entry in history[-10:]:
            self.sync_conversation(entry["role"], entry["content"][:500], session_id)

    def upload_artifact(self, filepath, label="", session_id=""):
        if not self.token:
            return False
        try:
            with open(filepath, "rb") as f:
                r = _requests.post(
                    f"{self.base_url}/api/collections/artifacts/records",
                    headers={"Authorization": f"Bearer {self.token}"},
                    files={
                        "file": (os.path.basename(filepath), f, "application/octet-stream"),
                        "label": (None, label),
                        "session_id": (None, session_id),
                    },
                    timeout=30,
                )
            return r.status_code in (200, 201)
        except Exception:
            return False

    def status_text(self):
        if not self.is_running():
            return "PocketBase: NOT RUNNING"
        lines = ["PocketBase: RUNNING"]
        lines.append(f"  Admin UI: {self.base_url}/_/")
        if self.token:
            lines.append(f"  Auth:     {self.admin_email}")
        else:
            lines.append("  Auth:     NOT authenticated")
        if self.process:
            lines.append(f"  PID:      {self.process.pid}")
        try:
            cols = self._list_collections()
            if cols:
                lines.append(f"  Collections: {', '.join(cols)}")
        except Exception:
            pass
        return "\n".join(lines)

    def stop(self):
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None
        self.ready = False
