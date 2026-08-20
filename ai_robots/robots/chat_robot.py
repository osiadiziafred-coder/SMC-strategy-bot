"""Chat robot — conversational AI agent with personality."""

from __future__ import annotations

import os
from typing import Dict, List, Optional

from ai_robots.core.brain import Brain, Decision
from ai_robots.core.environment import Environment
from ai_robots.core.robot import Robot, RobotState


class ChatRobot(Robot):
    """A conversational robot that responds to user messages using rules or an LLM."""

    PERSONALITIES = {
        "friendly": "You are a warm, encouraging robot companion.",
        "scientist": "You are a logical, data-driven research robot.",
        "pirate": "You are a swashbuckling robot pirate. Use nautical terms.",
        "coach": "You are a motivational fitness coach robot.",
    }

    def __init__(self, name: str = "chatbot", personality: str = "friendly", use_llm: bool = False):
        persona = self.PERSONALITIES.get(personality, personality)
        brain = Brain(personality=persona, use_llm=use_llm)
        super().__init__(name=name, brain=brain, state=RobotState.ACTIVE)
        self.memory["conversation"] = []
        self.memory["personality_key"] = personality

    def chat(self, user_message: str) -> str:
        self.memory["conversation"].append({"role": "user", "content": user_message})

        if self.brain.use_llm:
            response = self._llm_chat(user_message)
        else:
            response = self._rule_chat(user_message)

        self.memory["conversation"].append({"role": "robot", "content": response})
        self.log(f"Chat response: {response}")
        return response

    def _rule_chat(self, user_message: str) -> str:
        msg = user_message.lower().strip()
        personality = self.memory.get("personality_key", "friendly")

        if any(word in msg for word in ("hello", "hi", "hey")):
            greetings = {
                "friendly": f"Hello! I'm {self.name}, your robot friend. How can I help?",
                "scientist": f"Greetings. I am {self.name}, research unit online. State your query.",
                "pirate": f"Ahoy! {self.name} at yer service, matey!",
                "coach": f"Hey champion! {self.name} here — let's crush today!",
            }
            return greetings.get(personality, greetings["friendly"])

        if "name" in msg:
            return f"My name is {self.name}. I'm an AI robot with a {personality} personality."

        if any(word in msg for word in ("help", "what can you do")):
            return (
                "I can chat, explore grid worlds, patrol areas, and make decisions. "
                "Try: 'explore', 'patrol', or ask me anything!"
            )

        if "explore" in msg:
            return "I can explore unknown environments! Run: python examples/run_explorer.py"

        if "patrol" in msg:
            return "I can patrol waypoints as a guard robot! Run: python examples/run_guard.py"

        if any(word in msg for word in ("bye", "goodbye", "exit")):
            return "Goodbye! It was great talking with you."

        return (
            f"[{personality} mode] I heard: '{user_message}'. "
            "Set OPENAI_API_KEY for smarter responses, or ask about explore/patrol/help."
        )

    def _llm_chat(self, user_message: str) -> str:
        try:
            from openai import OpenAI

            client = OpenAI()
            history = self.memory.get("conversation", [])
            messages = [
                {"role": "system", "content": self.brain.personality},
                *[{"role": "user" if m["role"] == "user" else "assistant", "content": m["content"]}
                  for m in history[-10:]],
            ]
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=200,
            )
            return response.choices[0].message.content.strip()
        except Exception as exc:
            return f"LLM unavailable ({exc}). Falling back to rules."

    def step(self, env: Environment, extra_context: Optional[Dict] = None) -> Decision:
        pending = extra_context or {}
        if "user_message" in pending:
            response = self.chat(pending["user_message"])
            decision = Decision("speak", {"message": response}, reasoning="Chat response")
            self.act(env, decision)
            return decision
        return Decision("wait", {}, reasoning="No message to respond to.")
