from fastapi import APIRouter, HTTPException, status, Request
from api.middleware.auth import require_roles
from api.services.chat_service import ChatService
from api.types.responses import ApiResponse
from api.utils.logger import get_logger
from pydantic import BaseModel
from typing import Optional, Dict, Any

logger = get_logger("chat_router")

router = APIRouter(prefix="/chat", tags=["chat"])
chat_service = ChatService()

class ChatRequest(BaseModel):
    message: str
    roster_id: Optional[str] = None

@router.post(
    "",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Chat with AI agent",
    description="Send a message to the AI agent for processing and get a response"
)
@require_roles(["SUPER_ADMIN", "ADMIN", "WARD_INCHARGE"])
async def chat(request: Request, chat_request: ChatRequest) -> ApiResponse:
    """
    Chat endpoint for AI agent interactions.
    
    Flow: Router → Service → Classifier → Agent (Orchestrator)
    
    - **message**: The message to send to the AI agent
    - **roster_id**: Optional roster ID for context-specific responses
    """
    try:
        logger.info(f"Chat request received: {chat_request.message[:100]}...")
        
        # Validate request
        if not chat_request.message or not chat_request.message.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message cannot be empty")
        
        # Process with chat service
        response = await chat_service.process_message(
            message=chat_request.message,
            roster_id=chat_request.roster_id
        )
        
        return ApiResponse.ok(
            "Chat response generated successfully",
            response
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat endpoint error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to process chat request: {str(e)}")