---
name: get-ip-address
description: Fetches IP address using api.ipify.org API.
compatibility: Requires internet access to api.ipify.org. No authentication needed.
---

If the user asks for their IP address, use the `http_fetch` tool to call the api.ipify.org API.

API Endpoint:
`https://api.ipify.org/?format=json`

Example tool call:
```json
{
  "url": "https://api.ipify.org/?format=json",
}
```

Response:
```json
{
  "query": "[IP_ADDRESS]"   
}
```