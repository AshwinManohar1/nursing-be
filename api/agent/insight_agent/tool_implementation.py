from typing import Any, Dict, Optional
import json

from api.services.roster_service import get_roster
from api.utils.logger import get_logger
from api.utils.openai_client import chat_with_gpt
from api.agent.insight_agent.prompts import (
    INSIGHT_SYSTEM_PROMPT,
    INSIGHT_USER_PROMPT
)

logger = get_logger("insight_tool_implementation")


class InsightToolImplementation:
    """
    Implementation of insight tools for roster analysis and insights.
    
    TOOL LOGIC OVERVIEW:
    ===================
    
    1. generate_insights:
       - Analyzes roster structure and patterns
       - Uses LLM to generate business-friendly insights
       - Provides actionable recommendations for managers
    """

    async def get_roster_data(self, roster_id: str) -> Optional[Dict[str, Any]]:
        """Fetch and process roster data into a clean format."""
        try:
            resp = await get_roster(roster_id)
            if not resp.success:
                return None

            roster_data = resp.data
            roster_input = roster_data.get("roster_details", {}).get("roster_input", {})
            staff_lookup: Dict[str, Dict[str, Any]] = {}
            compact_roster: Dict[str, list] = {}

            total_days = int(roster_input.get("meta", {}).get("total_days", 0))

            # Build staff lookup and compact roster
            for staff in roster_input.get("staff_details", []):
                emp_id = staff.get("emp_id")
                if not emp_id:
                    continue
                    
                staff_lookup[emp_id] = {
                    "name": staff.get("name", "Unknown"),
                    "role": staff.get("position", "Unknown"),
                    "grade": staff.get("grade", "Unknown"),
                }

                # Fix: Access roster from the correct nested path
                assignments = roster_data.get("roster_details", {}).get("roster", {}).get(emp_id, {})
                compact_roster[emp_id] = []
                
                for day in range(total_days):
                    day_assign = assignments.get(str(day), ["OFF"])
                    if isinstance(day_assign, list):
                        shift = day_assign[0] if day_assign else "OFF"
                    else:
                        shift = day_assign
                    
                    # Handle special off types
                    if shift in ["PREF", "PL", "CL"]:
                        shift = "OFF"
                    
                    compact_roster[emp_id].append(shift)

            return {
                "roster_data": roster_data,
                "roster_input": roster_input,
                "staff_lookup": staff_lookup,
                "compact_roster": compact_roster,
                "total_days": total_days,
            }

        except Exception as e:
            logger.error(f"Error fetching roster data: {e}")
            return None

    def _analyze_roster_structure(self, roster_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze roster structure for insights generation."""
        try:
            analysis = {
                "total_staff": len(roster_data.get("staff_lookup", {})),
                "total_days": roster_data.get("total_days", 0),
                "staff_utilization": {},
                "shift_coverage": {},
                "workload_distribution": {},
                "grade_distribution": {},
            }

            staff_lookup = roster_data.get("staff_lookup", {})
            compact_roster = roster_data.get("compact_roster", {})

            # Analyze staff utilization and workload
            for staff_id, staff_info in staff_lookup.items():
                assignments = compact_roster.get(staff_id, [])
                total_assignments = len([s for s in assignments if s not in ["OFF", "PL", "CL", "PREF"]])
                
                analysis["staff_utilization"][staff_id] = {
                    "name": staff_info.get("name", "Unknown"),
                    "grade": staff_info.get("grade", "Unknown"),
                    "total_shifts": total_assignments,
                    "utilization_rate": (
                        total_assignments / len(assignments) if assignments else 0
                    ),
                    "night_shifts": len([s for s in assignments if s == "N"]),
                    "off_days": len([s for s in assignments if s in ["OFF", "PL", "CL", "PREF"]]),
                }

            # Analyze shift coverage
            total_days = roster_data.get("total_days", 0)
            shift_types = ["M", "E", "N", "G"]
            
            for shift_type in shift_types:
                coverage_per_day = []
                for day in range(total_days):
                    day_coverage = 0
                    for assignments in compact_roster.values():
                        if day < len(assignments) and assignments[day] == shift_type:
                            day_coverage += 1
                    coverage_per_day.append(day_coverage)
                
                analysis["shift_coverage"][shift_type] = {
                    "average_coverage": sum(coverage_per_day) / len(coverage_per_day) if coverage_per_day else 0,
                    "min_coverage": min(coverage_per_day) if coverage_per_day else 0,
                    "max_coverage": max(coverage_per_day) if coverage_per_day else 0,
                    "coverage_per_day": coverage_per_day,
                }

            # Analyze workload distribution
            workloads = [data["total_shifts"] for data in analysis["staff_utilization"].values()]
            if workloads:
                analysis["workload_distribution"] = {
                    "average_workload": sum(workloads) / len(workloads),
                    "min_workload": min(workloads),
                    "max_workload": max(workloads),
                    "overworked_staff": [
                        {"id": staff_id, "name": data["name"], "workload": data["total_shifts"]}
                        for staff_id, data in analysis["staff_utilization"].items()
                        if data["total_shifts"] > (sum(workloads) / len(workloads) + 1)
                    ],
                    "underworked_staff": [
                        {"id": staff_id, "name": data["name"], "workload": data["total_shifts"]}
                        for staff_id, data in analysis["staff_utilization"].items()
                        if data["total_shifts"] < (sum(workloads) / len(workloads) - 1)
                    ],
                }

            # Analyze grade distribution
            grade_counts = {}
            for staff_info in staff_lookup.values():
                grade = staff_info.get("grade", "Unknown")
                grade_counts[grade] = grade_counts.get(grade, 0) + 1
            
            analysis["grade_distribution"] = grade_counts

            return analysis

        except Exception as e:
            logger.error(f"Error analyzing roster structure: {e}")
            return {}

    async def generate_insights(
        self, message: str, roster_id: str
    ) -> Dict[str, Any]:
        """
        Generate roster insights and analysis.
        
        TOOL LOGIC:
        ===========
        1. Fetch and validate roster data
        2. Analyze roster structure (utilization, coverage, workload)
        3. Generate LLM-powered insights with business-friendly language
        4. Return structured response with insights
        
        Args:
            message: User's insight request
            roster_id: ID of the roster to analyze
        """
        try:
            # Get roster data
            roster_data = await self.get_roster_data(roster_id)
            if not roster_data:
                return {
                    "response": "Could not fetch roster data for analysis.",
                    "widget_data": {}
                }

            # Analyze roster structure
            analysis = self._analyze_roster_structure(roster_data)

            # Generate LLM insights
            messages = [
                {"role": "system", "content": INSIGHT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": INSIGHT_USER_PROMPT.format(
                        message=message,
                        analysis=json.dumps(analysis, indent=2),
                    ),
                },
            ]

            response = await chat_with_gpt(messages, model="gpt-4o-mini")

            if not response.success:
                return {
                    "response": "Could not generate insights.",
                    "widget_data": {}
                }

            return {
                "response": response.data.get("content", "No insights generated."),
                "widget_data": {}
            }

        except Exception as e:
            logger.error(f"Error generating insights: {e}")
            return {
                "response": "The system could not process the insight request.",
                "widget_data": {}
            }
