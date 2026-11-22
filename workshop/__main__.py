"""Allow running the workshop with ``python3 -m workshop``."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
