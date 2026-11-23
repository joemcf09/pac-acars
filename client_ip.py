"""The visitor's own address, for limits that must apply per person (wrong-password lockouts, usage counts).

pac-va.com sits behind Cloudflare and then Caddy, so request.remote_addr is a Cloudflare server, shared by
everyone who happens to reach the site through it: a per-address limit there locks out unrelated pilots together
and barely slows a guesser who moves between Cloudflare servers. Cloudflare puts the visitor's own address in the
CF-Connecting-IP header. Anyone can send that header, though, so it's believed only when the request really came
from Cloudflare (its published address ranges); a request straight to the server's IP keeps its own address."""
import ipaddress

from flask import request

# https://www.cloudflare.com/ips/ (unchanged for years; if Cloudflare adds a range, requests from it simply fall
# back to the Cloudflare address, as before this file existed)
CLOUDFLARE = [ipaddress.ip_network(n) for n in (
    "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22", "141.101.64.0/18", "108.162.192.0/18",
    "190.93.240.0/20", "188.114.96.0/20", "197.234.240.0/22", "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13",
    "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
    "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32", "2405:b500::/32", "2405:8100::/32", "2a06:98c0::/29",
    "2c0f:f248::/32")]


def from_cloudflare(addr):
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return any(ip in net for net in CLOUDFLARE if net.version == ip.version)


def client_ip():
    peer = request.remote_addr or ""
    given = (request.headers.get("CF-Connecting-IP") or "").strip()
    if given and from_cloudflare(peer):
        try:
            return str(ipaddress.ip_address(given))
        except ValueError:
            pass
    return peer or "?"
