"""Run the Guard robot patrol demo."""

from ai_robots.core.environment import Environment
from ai_robots.robots.guard import GuardRobot


def main():
    print("=" * 50)
    print("  GUARD ROBOT DEMO")
    print("=" * 50)

    env = Environment.from_ascii_map("guard", GuardRobot.demo_map())
    waypoints = [(0, 0), (4, 0), (4, 4), (0, 4)]
    robot = GuardRobot(name="guard", waypoints=waypoints)

    print("\nInitial state (S = guard start):")
    print(env.render())
    print(f"Patrol waypoints: {waypoints}")
    print()

    decisions = robot.run(env, max_steps=40)

    print("\nFinal state:")
    print(env.render(highlight=robot.state.value))
    print()

    report = robot.patrol_report()
    print("Patrol Report:")
    for key, value in report.items():
        print(f"  {key}: {value}")

    alerts = [log for log in robot.action_log if "ALERT" in log or "Says:" in log]
    if alerts:
        print("\nAlerts & messages:")
        for entry in alerts[:5]:
            print(f"  • {entry}")


if __name__ == "__main__":
    main()
