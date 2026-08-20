"""Main entry point — run all robot demos."""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="Python AI Robots")
    parser.add_argument(
        "demo",
        choices=["explorer", "guard", "chat", "all"],
        nargs="?",
        default="all",
        help="Which demo to run",
    )
    args = parser.parse_args()

    demos = {
        "explorer": "examples.run_explorer",
        "guard": "examples.run_guard",
        "chat": "examples.run_chat",
    }

    if args.demo == "all":
        for module_name in demos.values():
            module = __import__(module_name, fromlist=["main"])
            module.main()
            print()
    else:
        module = __import__(demos[args.demo], fromlist=["main"])
        if args.demo == "chat":
            module.main()
        else:
            module.main()


if __name__ == "__main__":
    main()
