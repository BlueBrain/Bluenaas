import secrets
import string


def generate_id(size: int = 10) -> str:
    alphabet = string.ascii_letters + string.digits + "-_"
    return "".join(secrets.choice(alphabet) for _ in range(size))
