import base64
import os
import uuid

import httpx
from dotenv import load_dotenv


load_dotenv(override=True)


def get_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def build_auth_key() -> str:
    for env_name in ("GIGACHAT_AUTH_KEY", "GIGACHAT_CREDENTIALS", "OPENROUTER_API_KEY"):
        value = os.getenv(env_name)
        if value:
            return value.strip()

    client_id = os.getenv("CLIENT_ID")
    client_secret = os.getenv("CLIENT_SECRET")
    if client_id and client_secret:
        raw = f"{client_id}:{client_secret}".encode("utf-8")
        return base64.b64encode(raw).decode("ascii")

    raise RuntimeError("Не найдены GigaChat credentials в .env")


def main() -> None:
    auth_url = os.getenv("GIGACHAT_AUTH_URL", "https://ngw.devices.sberbank.ru:9443/api/v2/oauth")
    scope = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
    if not get_bool_env("GIGACHAT_VERIFY_SSL", True):
        verify = False
    else:
        verify = (
            os.getenv("GIGACHAT_CA_BUNDLE")
            or os.getenv("SSL_CERT_FILE")
            or os.getenv("REQUESTS_CA_BUNDLE")
            or os.getenv("CURL_CA_BUNDLE")
            or True
        )

    response = httpx.post(
        auth_url,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
            "Authorization": f"Basic {build_auth_key()}",
        },
        data={"scope": scope},
        verify=verify,
        timeout=30,
    )
    response.raise_for_status()
    print(response.text)


if __name__ == "__main__":
    main()
