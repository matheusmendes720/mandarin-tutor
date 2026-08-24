"""CLI entrypoint for Lingua platform."""
import argparse

from src.lingua.ui.app import build_app
from src.lingua.core.config import AppConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="Lingua — Pronunciation & Vocabulary Tutor")
    parser.add_argument(
        "--port",
        type=int,
        default=7860,
        help="Port to run the server on (default: 7860)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind the server to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable Gradio's reload mode for development",
    )
    args = parser.parse_args()

    config = AppConfig(port=args.port, host=args.host, reload=args.reload)
    app = build_app(config={"title": "Lingua"})

    app.launch(
        server_port=config.port,
        server_name=config.host,
        reload=config.reload,
    )


if __name__ == "__main__":
    main()
