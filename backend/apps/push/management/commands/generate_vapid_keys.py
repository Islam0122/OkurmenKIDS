"""Print a fresh VAPID key pair for PUSH_VAPID_PUBLIC_KEY / PUSH_VAPID_PRIVATE_KEY.

Both values are base64url (no padding): the public key is the uncompressed
P-256 point the browser's PushManager.subscribe() expects as
applicationServerKey, the private key is the raw 32-byte scalar pywebpush
accepts. Generate once per environment and store the private key only in the
server's environment variables.
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.core.management.base import BaseCommand


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


class Command(BaseCommand):
    help = "Generate a VAPID key pair for Web Push (apps.push)."

    def handle(self, *args, **options):
        key = ec.generate_private_key(ec.SECP256R1())
        private = key.private_numbers().private_value.to_bytes(32, "big")
        public = key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint,
        )
        self.stdout.write(f"PUSH_VAPID_PUBLIC_KEY={_b64(public)}")
        self.stdout.write(f"PUSH_VAPID_PRIVATE_KEY={_b64(private)}")
        self.stdout.write("PUSH_VAPID_SUBJECT=mailto:<admin e-mail>")
