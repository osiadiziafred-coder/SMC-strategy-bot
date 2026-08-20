"""Tests for the AI robots framework."""

import pytest

from ai_robots.core.brain import Brain, Decision
from ai_robots.core.environment import Environment
from ai_robots.robots.explorer import ExplorerRobot
from ai_robots.robots.guard import GuardRobot
from ai_robots.robots.chat_robot import ChatRobot


def test_environment_creation():
    env = Environment(width=5, height=5)
    env.place_robot("bot", 0, 0)
    assert env.robot_positions["bot"] == (0, 0)


def test_environment_movement():
    env = Environment(width=5, height=5)
    env.place_robot("bot", 1, 1)
    assert env.move_robot("bot", "east")
    assert env.robot_positions["bot"] == (2, 1)
    assert env.move_robot("bot", "west")
    assert env.robot_positions["bot"] == (1, 1)
    assert env.move_robot("bot", "south")
    assert env.robot_positions["bot"] == (1, 2)


def test_environment_walls():
    env = Environment(width=3, height=3, walls={(1, 0)})
    env.place_robot("bot", 0, 0)
    assert not env.move_robot("bot", "east")  # wall blocks east
    assert env.move_robot("bot", "south")
    assert env.robot_positions["bot"] == (0, 1)


def test_from_ascii_map():
    env = Environment.from_ascii_map("explorer", ExplorerRobot.demo_map())
    assert env.robot_positions["explorer"] is not None
    assert len(env.walls) > 0


def test_brain_decision():
    brain = Brain()
    context = {
        "readings": {
            "position": (0, 0),
            "open_directions": ["east", "south"],
            "goals": [(2, 0)],
            "hazards": [],
        },
        "memory": {},
        "energy": 100,
    }
    decision = brain.decide(context)
    assert decision.action in ("move", "wait", "speak", "complete")


def test_explorer_runs():
    env = Environment.from_ascii_map("explorer", ExplorerRobot.demo_map())
    robot = ExplorerRobot()
    decisions = robot.run(env, max_steps=15)
    assert len(decisions) > 0
    report = robot.exploration_report()
    assert report["visited_cells"] > 0


def test_guard_patrol():
    env = Environment.from_ascii_map("guard", GuardRobot.demo_map())
    robot = GuardRobot(waypoints=[(0, 0), (4, 0)])
    decisions = robot.run(env, max_steps=10)
    assert len(decisions) > 0


def test_chat_robot_greeting():
    robot = ChatRobot(personality="friendly")
    response = robot.chat("Hello!")
    assert "Hello" in response or "robot" in response.lower()


def test_chat_robot_pirate():
    robot = ChatRobot(personality="pirate")
    response = robot.chat("hi")
    assert "Ahoy" in response or "matey" in response.lower()
