"""Entry point listed in the build spec. Same as ``python -m smc_robot``."""

from smc_robot.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
