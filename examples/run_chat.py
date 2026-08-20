"""Interactive chat with a ChatRobot."""

import sys

from ai_robots.core.environment import Environment
from ai_robots.robots.chat_robot import ChatRobot


def main():
    print("=" * 50)
    print("  CHAT ROBOT — Interactive Demo")
    print("=" * 50)
    print("Choose personality: friendly, scientist, pirate, coach")
    personality = input("Personality [friendly]: ").strip() or "friendly"

    robot = ChatRobot(name="Robo", personality=personality)
    env = Environment(width=1, height=1)
    env.place_robot(robot.name, 0, 0)

    if robot.brain.use_llm:
        print(f"\n{robot.name} online (LLM mode, {personality}). Type 'quit' to exit.\n")
    else:
        print(f"\n{robot.name} online (rule-based, {personality}). Type 'quit' to exit.\n")
        print("Tip: set OPENAI_API_KEY for smarter conversations.\n")

    greeting = robot.chat("Hello!")
    print(f"{robot.name}: {greeting}\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "bye"):
            farewell = robot.chat("Goodbye!")
            print(f"{robot.name}: {farewell}")
            break

        response = robot.chat(user_input)
        print(f"{robot.name}: {response}\n")


if __name__ == "__main__":
    main()
