"""Código público del QR: aleatorio, opaco e inmutable (R009, plan D1)."""

import secrets

# Crockford base32: sin I, L, O ni U, para que no se confundan al leerlos.
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
LENGTH = 10  # 32**10 ≈ 2**50 combinaciones


def generate_public_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))


def is_public_code(value: str) -> bool:
    """Forma válida de un código: 10 símbolos del alfabeto, tal cual (R013)."""
    return len(value) == LENGTH and all(symbol in ALPHABET for symbol in value)
