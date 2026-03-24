import os
import urllib.request


def main() -> None:
    port = os.environ.get("HEALTHCHECK_PORT", "8081")
    urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=5)


if __name__ == "__main__":
    main()
