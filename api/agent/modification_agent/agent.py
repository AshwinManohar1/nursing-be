from typing import Dict, Any
import json

from api.agent.modification_agent.tool_definition import MODIFICATION_TOOLS
from api.agent.modification_agent.tool_implementation import ModificationToolImplementation
from api.agent.modification_agent.prompts import MODIFICATION_AGENT_SYSTEM_PROMPT, MODIFICATION_USER_PROMPT
from api.utils.openai_client import chat_with_gpt
from api.utils.logger import get_logger

logger = get_logger("modification_agent")


class ModificationAgent:
    def __init__(self):
        self.tools = ModificationToolImplementation()
        self.tool_definitions = MODIFICATION_TOOLS

    async def process_modification(self, message: str, roster_id: str) -> Dict[str, Any]:
        try:
            messages = [
                {"role": "system", "content": MODIFICATION_AGENT_SYSTEM_PROMPT},
                {"role": "user", "content": MODIFICATION_USER_PROMPT.format(query=message)},
            ]

            llm = await chat_with_gpt(
                messages,
                model="gpt-4o-mini",
                tools=self.tool_definitions,
                tool_choice="auto",
            )

            if not llm.success:
                return {"response": "LLM call failed", "widget_data": {}}

            response_data = llm.data
                        # Extract tool calls directly
            tool_calls = response_data.get("tool_calls", [])
            
            if not tool_calls:
                return {
                    "response": response_data.get("content", "No tool selected"),
                    "widget_data": {}
                }

            # Process the first tool call
            tool_call = tool_calls[0]
            tool_name = tool_call["function"]["name"]
            tool_args = json.loads(tool_call["function"]["arguments"])
            
            # Add roster_id to tool args
            tool_args["roster_id"] = roster_id
            print(tool_name, "tool_name")
            print(tool_args, "tool_args")
            # Execute the tool
            if hasattr(self.tools, tool_name):
                result = await getattr(self.tools, tool_name)(**tool_args)
                return result
            else:
                return {"response": f"Tool {tool_name} not found", "widget_data": {}}

        except Exception as e:
            logger.error(f"Agent error: {e}")
            return {"response": "Error processing request", "widget_data": {}}