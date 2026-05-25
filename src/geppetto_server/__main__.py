from __future__ import annotations

from .server import serve
from .settings import load_settings


def main() -> None:
    serve(load_settings())


if __name__ == "__main__":
    main()
