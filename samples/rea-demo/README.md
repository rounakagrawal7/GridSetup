# GRID REA demo

A tiny local site for manual reverse-engineering tests. It intentionally has
missing security headers, a login form, a few endpoints and a lazy section that
loads only after scrolling.

From the repository root:

```powershell
python -m http.server 8765 --bind 127.0.0.1 --directory samples/rea-demo
```

Then run an authorized teardown from GRID:

```text
rea authorized http://127.0.0.1:8765/
```

Reports are written to `refs/rea/<host>-<timestamp>/`.
