# Python AI Robots

A modular Python framework for building intelligent virtual robots. Create explorers, guards, and chatbots with rule-based AI or optional LLM-powered brains.

## Features

- **Grid simulation environment** — walls, goals, hazards, multi-robot support
- **Hybrid AI brain** — rule-based navigation plus optional OpenAI LLM decisions
- **Three robot types**:
  - **Explorer** — maps unknown areas and finds goals
  - **Guard** — patrols waypoints and raises alerts
  - **ChatRobot** — conversational agent with personalities
- **Runnable demos** — see robots in action immediately

## Quick Start

```bash
# No install required for rule-based mode (stdlib only)
python examples/run_explorer.py
python examples/run_guard.py

# Optional: LLM-powered decisions and chat
pip install -r requirements.txt
export OPENAI_API_KEY=your-key-here
python examples/run_chat.py
```

Or run all demos:

```bash
python main.py all
```

## Project Structure

```
ai_robots/
  core/
    environment.py   # 2D grid world simulation
    robot.py         # Base robot (sense-think-act loop)
    brain.py         # AI decision engine
  robots/
    explorer.py      # Exploration robot
    guard.py         # Patrol guard robot
    chat_robot.py    # Conversational robot
examples/
  run_explorer.py
  run_guard.py
  run_chat.py
main.py
```

## Create Your Own Robot

```python
from ai_robots.core.brain import Brain, Decision
from ai_robots.core.environment import Environment
from ai_robots.core.robot import Robot

class MyRobot(Robot):
    def __init__(self):
        brain = Brain(personality="custom")
        super().__init__(name="mybot", brain=brain)

env = Environment.from_ascii_map("mybot", """
    . . G
    . # .
    R . .
""")

robot = MyRobot()
robot.run(env, max_steps=20)
print(env.render())
```

## Chat Robot Personalities

| Personality | Style |
|-------------|-------|
| `friendly`  | Warm, encouraging companion |
| `scientist` | Logical, data-driven |
| `pirate`    | Nautical, adventurous |
| `coach`     | Motivational fitness coach |

## Environment Map Legend

| Symbol | Meaning |
|--------|---------|
| `.`    | Empty cell |
| `#`    | Wall |
| `G`    | Goal |
| `X`    | Hazard |
| `R/S`  | Robot start position |

## License

MIT
