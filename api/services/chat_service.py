from api.agent.classifier import IntentClassifier
from api.agent.modification_agent.agent import ModificationAgent
from api.agent.insight_agent.agent import InsightAgent
from api.utils.logger import get_logger
from typing import Dict, Any, Optional

logger = get_logger("chat_service")

class ChatService:
    def __init__(self):
        self.classifier = IntentClassifier()
        self.modification_agent = ModificationAgent()
        self.insight_agent = InsightAgent()
    
    async def process_message(
        self, 
        message: str, 
        roster_id: Optional[str] = None, 
    ) -> Dict[str, Any]:
        """
        Process chat message through the complete flow:
        Service → Classifier → Agent (Orchestrator)
        """
        try:
            logger.info(f"Processing message: {message[:100]}")
            
            # Step 1: Classify intent
            intent_result = await self.classifier.classify(message)
            logger.info(f"Intent classified as: {intent_result['intent']} (confidence: {intent_result['confidence']})")

            intent = intent_result.get('intent', "")
            
            # Route to appropriate tool based on intent
            if intent == "modification":
                return await self.modification_agent.process_modification(message, roster_id)
            elif intent == "insight":
                return await self.insight_agent.process_request(message, roster_id)
            else:  # other
                return {
                    "response": "I can help with roster modifications or insights. Try asking me about shift changes or coverage gaps.",
                    "widget_data": {},
                }

            
        except Exception as e:
            logger.error(f"Chat service error: {e}")
            return {
                "response": "I apologize, but I encountered an error processing your request. Please try again.",
                "widget_data": {}
            }