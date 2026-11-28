"""Inicialização local do Fullguete sem alterar a configuração do Streamlit."""

import argparse
import os
import socket

FRONTEND_HOST = "127.0.0.1"
FRONTEND_PORT = 3001
API_PORT = 8001
API_HOSTS = ("127.0.0.1", "127.0.0.2")


def api_host() -> str:
    host = os.environ.get("FULLGUETE_API_HOST", FRONTEND_HOST)
    if host not in API_HOSTS:
        raise SystemExit("FULLGUETE_API_HOST deve ser 127.0.0.1 ou 127.0.0.2.")
    return host


def check_ports(host: str) -> None:
    errors = []
    for address, port in ((FRONTEND_HOST, FRONTEND_PORT), (host, API_PORT)):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                listener.bind((address, port))
            except OSError as exc:
                errors.append(f"{address}:{port} indisponível ({exc.strerror})")
    if errors:
        raise SystemExit("Fullguete não iniciado. " + "; ".join(errors) + ".")
    print(f"Portas disponíveis: {FRONTEND_HOST}:{FRONTEND_PORT} e {host}:{API_PORT}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Apenas verificar as duas portas.")
    args = parser.parse_args()
    host = api_host()
    if args.check:
        check_ports(host)
        return
    import uvicorn

    uvicorn.run("portal_api.app:create_app", factory=True, host=host, port=API_PORT, proxy_headers=False)


if __name__ == "__main__":
    main()
