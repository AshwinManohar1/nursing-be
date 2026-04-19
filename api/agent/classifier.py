from api.agent.prompts import CLASSIFIER_PROMPT, CLASSIFIER_USER_PROMPT
from api.utils.openai_client import chat_with_gpt
from api.utils.logger import get_logger
import json

logger = get_logger("intent_classifier")

class IntentClassifier:
    async def classify(self, message: str) -> dict:
        """Classify user message intent"""
        try:
            messages = [
                {"role": "system", "content": CLASSIFIER_PROMPT},
                {"role": "user", "content": CLASSIFIER_USER_PROMPT.format(message=message)}
            ]
            

            response = await chat_with_gpt(messages, model="gpt-4o-mini")
            
            if not response.success:
                logger.error(f"Intent classification failed: {response.message}")
                return {
                    "intent": "other",
                    "confidence": 0.0,
                    "reasoning": "Classification failed, defaulting to OTHER"
                }
            
            # Parse the JSON response
            content = response.data["content"]
            try:
                result = json.loads(content)
                return {
                    "intent": result["intent"],
                    "confidence": result["confidence"],
                    "reasoning": result["reasoning"]
                }
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.error(f"Failed to parse intent classification: {e}")
                return {
                    "intent": "other",
                    "confidence": 0.0,
                    "reasoning": "Failed to parse classification result"
                }
                
        except Exception as e:
            logger.error(f"Intent classification error: {e}")
            return {
                "intent": "other",
                "confidence": 0.0,
                "reasoning": f"Classification error: {str(e)}"
            }