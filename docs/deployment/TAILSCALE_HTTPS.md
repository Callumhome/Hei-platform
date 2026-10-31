# HEI HTTPS deployment with DuckDNS and NGINX Home Assistant SSL Proxy

## Existing deployment

HEI is served privately through the existing DuckDNS hostname and the NGINX
Home Assistant SSL Proxy add-on. Do not introduce Tailscale, Cloudflare, or
another public proxy for this deployment.

- Public hostname: `https://hei-smart-homelab1.duckdns.org`
- HEI frontend upstream: `http://192.168.10.120:3000`
- HEI API remains behind the frontend container's NGINX same-origin proxy.
- Home Assistant remote access and its existing NGINX proxy routes must remain
  unchanged.
- The DuckDNS add-on and NGINX SSL Proxy run as Home Assistant add-ons.

The NGINX add-on's custom HEI route is maintained at
`/share/nginx_proxy/hei.conf`, with the active custom server configuration
enabled. Preserve the existing forwarded headers and Let's Encrypt certificate
paths (`fullchain.pem` and `privkey.pem`).

## Request path

```text
Phone / browser
      |
      | HTTPS, DuckDNS hostname, Let's Encrypt certificate
      v
NGINX Home Assistant SSL Proxy add-on
      |
      | HTTP upstream
      v
192.168.10.120:3000 (HEI frontend NGINX)
      |
      | /api/ and /health proxied internally
      v
HEI API :8000 -> PostgreSQL / Redis
```

## Security boundaries

- Do not change or remove existing Home Assistant proxy routes.
- Do not change OPNsense LAN separation or the Proxmox subnet-router setup.
- Do not expose the HEI API port 8000 directly to the internet.
- Keep the frontend's same-origin API proxy in place.
- Octopus account credentials must only be submitted using the HTTPS DuckDNS
  hostname. The frontend blocks credential submission over plain HTTP.
- The browser-to-proxy connection uses the Let's Encrypt certificate. The
  proxy-to-HEI upstream is the existing LAN connection to 192.168.10.120.
- HEI authentication and household authorization remain required in addition
  to HTTPS.

## Verification before entering supplier credentials

1. Open `https://hei-smart-homelab1.duckdns.org` on the device being used.
2. Confirm the browser shows a valid secure connection.
3. Sign in and verify that the dashboard and API-backed household sections load.
4. Only then use the Octopus connection form.

The existing LAN address may remain available for ordinary local access, but
never use its plain HTTP form to submit Octopus credentials.
