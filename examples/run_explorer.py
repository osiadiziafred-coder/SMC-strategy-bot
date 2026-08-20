"""Run the Explorer robot demo."""

from ai_robots.core.environment import Environment
from ai_robots.robots.explorer import ExplorerRobot


def main():
    print("=" * 50)
    print("  EXPLORER ROBOT DEMO")
    print("=" * 50)

    env = Environment.from_ascii_map("explorer", ExplorerRobot.demo_map())
    robot = ExplorerRobot(name="explorer")

    print("\nInitial state:")
    print(env.render())
    print()

    decisions = robot.run(env, max_steps=30)

    print("\nFinal state:")
    print(env.render(highlight=robot.state.value))
    print()

    report = robot.exploration_report()
    print("Exploration Report:")
    for key, value in report.items():
        print(f"  {key}: {value}")

    print("\nLast 5 actions:")
    for entry in robot.action_log[-5:]:
        print(f"  • {entry}")


if __name__ == "__main__":
    main()
