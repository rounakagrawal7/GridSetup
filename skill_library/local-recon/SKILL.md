---
name: local-recon
description: Inventory the local machine and its own network safely. Use for system health, open ports, local services, DNS and connectivity checks on hardware the user owns.
license: MIT
metadata:
  author: GRID
  version: "1.0"
---
# Local Recon

Only inspect the machine and network the user owns or is authorized to test.

## Steps

1. `system_info` for OS, CPU, memory, disk and LAN address.
2. `netstat` for listening ports and active connections.
3. `dns_lookup` against the local resolver and a public resolver; compare.
4. `ping` the gateway and one public host to separate LAN from WAN problems.
5. `nmap_scan` only against the local subnet or an explicit authorized target.
   Start with a fast scan; do not use `-A`, `-O` or scripts unless asked.
6. If a port is unexpected, identify the process with `process_manager list`
   before suggesting any change.
7. Do not change firewall, DNS, routes or services without explicit approval.

## Output

- Host summary and LAN address
- Listening services with process names when known
- Reachability: LAN, DNS, internet
- Unexpected or risky exposure
- One recommended next step, with the exact command if safe

Keep it factual. Do not describe a port as vulnerable without evidence.
