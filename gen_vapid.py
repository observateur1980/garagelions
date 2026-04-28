"""Generate a fresh VAPID keypair for Web Push.

Run with the project's venv:
    /var/www/garagelions/venv/bin/python gen_vapid.py

Prints two .env lines you can paste into your environment file.
"""
import base64
from py_vapid import Vapid
from cryptography.hazmat.primitives import serialization

v = Vapid()
v.generate_keys()

pub = v.public_key.public_bytes(
    encoding=serialization.Encoding.X962,
    format=serialization.PublicFormat.UncompressedPoint,
)
priv = v.private_key.private_numbers().private_value.to_bytes(32, "big")

print("VAPID_PUBLIC_KEY=" + base64.urlsafe_b64encode(pub).rstrip(b"=").decode())
print("VAPID_PRIVATE_KEY=" + base64.urlsafe_b64encode(priv).rstrip(b"=").decode())
