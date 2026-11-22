"""
Hash de contraseñas con PBKDF2-SHA256 + salt aleatorio (biblioteca estándar).

Formato guardado en usuario.contrasena (87 caracteres, cabe en VARCHAR(100)):
    pbkdf2_sha256$<iteraciones>$<salt base64>$<hash base64>

Se eligió hashlib en lugar de passlib[bcrypt] porque passlib 1.7.4 ya no funciona
con bcrypt >= 4.1 / Python 3.13+.
"""
import base64
import hashlib
import hmac
import secrets

ESQUEMA = "pbkdf2_sha256"
ITERACIONES = 600_000


def _b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).rstrip(b"=").decode("ascii")


def _de_b64(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def hashear(contrasena: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", contrasena.encode("utf-8"), salt, ITERACIONES)
    return f"{ESQUEMA}${ITERACIONES}${_b64(salt)}${_b64(digest)}"


def es_hash(guardada: str) -> bool:
    return (guardada or "").startswith(ESQUEMA + "$")


def verificar(contrasena: str, guardada: str) -> bool:
    """True si coincide. Acepta contraseñas antiguas en texto plano (para migrarlas)."""
    if not guardada or contrasena is None:
        return False
    if not es_hash(guardada):
        return hmac.compare_digest(contrasena.encode("utf-8"), guardada.encode("utf-8"))
    try:
        _, iteraciones, salt, digest = guardada.split("$")
        calculado = hashlib.pbkdf2_hmac("sha256", contrasena.encode("utf-8"), _de_b64(salt), int(iteraciones))
        return hmac.compare_digest(calculado, _de_b64(digest))
    except (ValueError, TypeError):
        return False


def necesita_rehash(guardada: str) -> bool:
    if not es_hash(guardada):
        return True
    try:
        return int(guardada.split("$")[1]) < ITERACIONES
    except (IndexError, ValueError):
        return True


# Política de contraseñas (RF 1.1): la usan el alta/edición de usuarios y la recuperación
MENSAJE_POLITICA = "La contraseña debe ser alfanumérica (letras y números) y tener al menos 8 caracteres."


def cumple_politica(contrasena: str) -> bool:
    pwd = contrasena or ""
    return len(pwd) >= 8 and any(c.isalpha() for c in pwd) and any(c.isdigit() for c in pwd)
