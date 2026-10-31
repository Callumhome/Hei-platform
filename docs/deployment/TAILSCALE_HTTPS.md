# HEI private HTTPS with Tailscale Serve

## Purpose

Provide HTTPS access to the HEI web application for devices in the user's
Tailscale tailnet. This is private access, not a public internet endpoint.
Do not use Tailscale Funnel.

The HEI Docker Compose frontend remains on host port 3000. Nginx inside the
frontend container continues to proxy `/api/` and `/health` to the API,
so browser requests remain same-origin. PostgreSQL, Redis and the API do not
need public exposure.

## Deployment topology

```text
Phone / tablet (Tailscale)
        |
        | HTTPS, Tailscale-managed certificate
        v
hei-server LXC (Tailscale Serve)
        |
        | HTTP to 127.0.0.1:3000 (inside the LXC)
        v
HEI frontend Nginx container
        |
        | private Docker network
        v
HEI API :8000 -> PostgreSQL / Redis
```

Install Tailscale in the `hei-server` LXC itself, rather than changing the
existing Proxmox subnet-router configuration. This gives HEI its own
MagicDNS name and avoids changing the existing Proxmox routes or other
Tailscale services.

## Preconditions

- Tailscale is installed and authenticated in the `hei-server` LXC.
- The LXC can reach the existing HEI frontend at `127.0.0.1:3000`.
- HTTPS certificates are enabled for the tailnet. The first Serve command
  may provide a web approval link to enable them.
- The device used to open HEI is signed into the same tailnet and permitted
  by the tailnet access-control policy.

## Enable HTTPS

Run inside the `hei-server` LXC:

```bash
sudo tailscale serve --bg 3000
```

Tailscale prints the private HTTPS URL, normally in the form
`https://hei-server.<tailnet>.ts.net`. Use the exact URL printed by Tailscale;
do not guess the tailnet domain.

Verify the active configuration:

```bash
sudo tailscale serve status
```

Verify the local frontend first:

```bash
curl -I http://127.0.0.1:3000
```

Then open the printed HTTPS URL on a phone or tablet that is connected to
Tailscale. Confirm sign-in, dashboard loading, and API-backed household data.

## Important security boundaries

- Use Tailscale Serve, never Funnel, for this private HEI deployment.
- Do not expose ports 3000 or 8000 to the public internet.
- Do not change OPNsense LAN separation, Proxmox subnet routes, or existing
  Proxmox Tailscale Serve configuration as part of this setup.
- Keep the API behind the frontend Nginx same-origin proxy.
- Do not enter Octopus API credentials until the HTTPS URL has been tested
  successfully from the device that will be used for account linking.
- Tailscale Serve terminates HTTPS at the LXC. Its local upstream connection
  to the frontend is HTTP over loopback; it does not leave the LXC.
- Tailnet membership and access-control rules determine who can reach this
  private URL. HTTPS alone does not grant access to HEI accounts; HEI login
  and household authorization remain required.

## Disable HTTPS serving

Run inside the `hei-server` LXC:

```bash
sudo tailscale serve --https=443 off
```

This disables the HTTPS Serve endpoint on this LXC. It does not stop Docker,
change the HEI LAN URL, or modify the Proxmox subnet router.

## Troubleshooting

- If `tailscale serve` asks for approval, open the exact approval URL it
  prints and enable HTTPS certificates for the tailnet.
- If the local curl check fails, do not enable Serve yet; first restore the
  HEI frontend container on port 3000.
- If the HTTPS URL works on the LXC but not on a phone, check that the phone
  is connected to Tailscale and that tailnet access controls permit the LXC.
- Check the printed MagicDNS URL and `tailscale serve status`; do not use an
  IP address in place of the HTTPS hostname.
