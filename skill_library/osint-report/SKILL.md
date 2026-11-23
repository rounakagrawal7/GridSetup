---
name: osint-report
description: Produce a sourced, confidence-rated OSINT report from domains, IPs, emails, usernames or public pages. Use for authorized reconnaissance, due diligence, exposure review or investigation notes.
license: MIT
metadata:
  author: GRID
  version: "1.0"
---
# OSINT Report

Use only for authorized, lawful research. Stop if the target is private,
credentials are involved, or the request would require unauthorized access.

## Collection

1. Confirm the target type: domain, IP, email, username, URL or organization.
2. Use `osint` for the first pass.
3. Add `dns_lookup`, `web_search`, `web_fetch` or `dork` only when they answer a
   specific question.
4. Record the source URL and the time of collection for every claim.
5. Prefer primary sources. Treat social profiles and scraped pages as
   unverified until corroborated.
6. Never attempt login, exploitation, credential use or private-data access.

## Analysis

- Separate **facts**, **inferences** and **unknowns**.
- Rate confidence: high (primary source), medium (two independent sources), low
  (single indirect source).
- Note contradictions instead of resolving them silently.
- Keep personal data to what is necessary for the stated purpose.

## Output

1. **Scope and authorization**
2. **Summary** (5 lines maximum)
3. **Findings** with source and confidence for each
4. **Exposure / risk notes**
5. **Gaps and next steps**
6. **Collection log** (source, timestamp, tool)

Never present a guess as a finding. If no reliable result is found, say so.
