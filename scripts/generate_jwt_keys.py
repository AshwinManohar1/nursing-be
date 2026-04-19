#!/usr/bin/env python3
"""Generate RSA key pair for JWT RS256. Run and add output to .env."""
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
public_key = private_key.public_key()

private_pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption()
).decode()

public_pem = public_key.public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo
).decode()

# For .env: use single-line format (replace newlines with \n)
private_oneline = private_pem.replace("\n", "\\n")
public_oneline = public_pem.replace("\n", "\\n")

print("Add these to your .env file:\n")
print("# Optional (defaults: 15 min access, 7 days refresh):")
print("# JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15")
print("# JWT_REFRESH_TOKEN_EXPIRE_DAYS=7")
print()
print("# Private key (single line, escaped newlines):")
print(f'JWT_PRIVATE_KEY="{private_oneline}"')
print()
print("# Public key (single line, escaped newlines):")
print(f'JWT_PUBLIC_KEY="{public_oneline}"')
