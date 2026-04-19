from datetime import datetime
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI
from api.config import OPEN_API_KEY
from api.types.responses import ApiResponse

openai_client = AsyncOpenAI(api_key=OPEN_API_KEY or "placeholder")

async def chat_with_gpt(
    messages: List[Dict[str, str]],
    model: str = "gpt-4o-mini",
    max_tokens: Optional[int] = None,
    top_p: Optional[float] = None,
    frequency_penalty: Optional[float] = None,
    presence_penalty: Optional[float] = None,
    stream: bool = False,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[str] = None,
    verbosity: Optional[str] = None,
    reasoning_effort: Optional[str] = None,
    **kwargs: Any
) -> ApiResponse:
    try:
        request_params = {
            "model": model,
            "messages": messages,
            "stream": stream,
            **kwargs
        }

        # only add params if not None
        if max_tokens is not None:
            request_params["max_tokens"] = max_tokens
        if top_p is not None:
            request_params["top_p"] = top_p
        if frequency_penalty is not None:
            request_params["frequency_penalty"] = frequency_penalty
        if presence_penalty is not None:
            request_params["presence_penalty"] = presence_penalty
        if tools is not None:
            request_params["tools"] = tools
        if tool_choice is not None:
            request_params["tool_choice"] = tool_choice
        if verbosity is not None:
            request_params["verbosity"] = verbosity
        if reasoning_effort is not None:
            request_params["reasoning_effort"] = reasoning_effort

        response = await openai_client.chat.completions.create(**request_params)

        if stream:
            return ApiResponse(success=True, message="Streaming not handled here", data=None)

        message = response.choices[0].message
        
        # Generic response data - includes everything the LLM returns
        response_data = {
            "role": message.role,
            "content": message.content,
            "tool_calls": None,  # Will be populated if present
        }
        
        # Handle tool_calls (new function calling format)
        if hasattr(message, 'tool_calls') and message.tool_calls:
            response_data["tool_calls"] = [
                {
                    "id": tool_call.id,
                    "type": tool_call.type,
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments
                    }
                }
                for tool_call in message.tool_calls
            ]

        return ApiResponse(
            success=True,
            message="OpenAI response generated",
            data=response_data,
            timestamp=datetime.utcnow().isoformat()
        )

    except Exception as e:
        return ApiResponse(
            success=False,
            message=f"OpenAI request failed: {e}",
            data={},
            timestamp=datetime.utcnow().isoformat()
        )