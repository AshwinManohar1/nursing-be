from typing import Any, Dict, Optional

from api.agent.insight_agent.tool_implementation import InsightToolImplementation
from api.utils.logger import get_logger

logger = get_logger("insight_agent")


class InsightAgent:
    """
    Agent for handling roster insights and analysis requests.
    
    AGENT LOGIC:
    ============
    - Routes insight requests to appropriate tools
    - Currently has one main tool: generate_insights
    - Follows the same pattern as modification_agent for consistency
    """

    def __init__(self):
        self.tool_implementation = InsightToolImplementation()

    async def process_request(
        self, message: str, roster_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process insight requests and route to appropriate tools.
        
        Args:
            message: User's insight request
            roster_id: Optional roster ID for analysis
            
        Returns:
            Dict with response and widget_data
        """
        try:
            # For now, all insight requests go to generate_insights
            # In the future, we can add more specific tools here
            
            if not roster_id:
                return {
                    "response": "Please provide a roster ID to get insights.",
                    "widget_data": {}
                }

            # Route to generate_insights tool
            result = await self.tool_implementation.generate_insights(
                message=message,
                roster_id=roster_id
            )

            return result

        except Exception as e:
            logger.error(f"Error in insight agent: {e}")
            return {
                "response": "The system could not process the insight request.",
                "widget_data": {}
            }
