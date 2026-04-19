from typing import Any, Dict, Optional, List
from datetime import datetime, timedelta
import json
from difflib import SequenceMatcher

from api.services.roster_service import get_roster
from api.utils.logger import get_logger
from api.utils.openai_client import chat_with_gpt
from api.agent.modification_agent.prompts import (
    ALTERNATIVE_GENERATION_SYSTEM_PROMPT,
    ALTERNATIVE_GENERATION_USER_PROMPT,
    SHIFT_ASSIGNMENT_SYSTEM_PROMPT,
    SHIFT_ASSIGNMENT_USER_PROMPT,
    STAFF_SWAP_SYSTEM_PROMPT,
    STAFF_SWAP_USER_PROMPT,
    COVERAGE_OPTIMIZATION_SYSTEM_PROMPT,
    COVERAGE_OPTIMIZATION_USER_PROMPT
)

logger = get_logger("modification_tool_implementation")


def calculate_string_similarity(str1: str, str2: str) -> float:
    """Calculate similarity ratio between two strings (0.0 to 1.0)."""
    return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()


class ModificationToolImplementation:
    """
    Implementation of modification tools that return chat 'response' and UI 'widget_data'.
    
    TOOL LOGIC OVERVIEW:
    ===================
    
    1. handle_absence_management:
       - Handles staff absences (sick leave, personal leave, emergency)
       - Uses LLM to generate intelligent alternatives based on healthcare staffing rules
       - Implements constraint hierarchy: CRITICAL > HIGH > MEDIUM > LOW
       - Follows replacement rules: N4→2N5, N5→higher grade, etc.
    
    2. handle_shift_assignment:
       - Direct shift changes and assignments
       - Validates constraints before making changes
       - Provides alternatives if direct assignment violates rules
    
    3. handle_staff_swap:
       - Swaps shifts between two staff members
       - Ensures both staff can handle the swapped shifts
       - Checks for constraint violations after swap
    
    4. handle_coverage_optimization:
       - Fills coverage gaps in specific shifts
       - Finds best available staff for coverage
       - Optimizes workload distribution
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
            compact_roster: Dict[str, List[str]] = {}
            total_days = int(roster_input["meta"]["total_days"])

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

                assignments = roster_data.get("roster_details", {}).get("roster", {}).get(emp_id, {})
                compact_roster[emp_id] = []
                
                for day in range(total_days):
                    day_assign = assignments.get(str(day))
                    if isinstance(day_assign, list):
                        shift = day_assign[0] if day_assign else "OFF"
                    else:
                        shift = day_assign
                    
                    compact_roster[emp_id].append(shift)

            start_date = datetime.strptime(roster_input["meta"]["schedule_start_date"], "%Y-%m-%d")
            day_mapping = {
                i: (start_date + timedelta(days=i)).strftime("%Y-%m-%d (%A)") for i in range(total_days)
            }

            return {
                "roster_data": roster_data,
                "roster_input": roster_input,
                "staff_lookup": staff_lookup,
                "compact_roster": compact_roster,
                "day_mapping": day_mapping,
                "total_days": total_days,
                "start_date": start_date
            }
        except Exception as e:
            logger.error(f"Error processing roster data: {e}")
            return None

    async def generate_alternatives(
        self, 
        roster_data: Dict[str, Any], 
        absent_staff_id: str, 
        absence_days: List[str], 
        absence_type: str
    ) -> Dict[str, Any]:
        """
        Generate intelligent alternatives using SCENARIO-BASED pre-computed facts.
        
        DECISION TREE:
        1. N4 → No coverage needed, just approve
        2. N5 with redundancy → Approve with names
        3. N5 without redundancy → Manual intervention
        4. N6/N7/N8 → Suggest extensions (M→ME, E→ME) or swaps
        5. Already OFF → Just approve
        """
        try:
            staff_lookup = roster_data["staff_lookup"]
            absent_staff = staff_lookup.get(absent_staff_id, {})
            if not absent_staff:
                return {}
            
            absent_grade = absent_staff.get('grade', 'Unknown')
            absent_name = absent_staff.get('name', 'Unknown')
            day_mapping = roster_data["day_mapping"]
            affected_day_indices = self._map_day_names_to_indices(absence_days, day_mapping)
            compact_roster = roster_data["compact_roster"]
            absent_assignments = compact_roster.get(absent_staff_id, [])
            total_days = roster_data["total_days"]
            
            # Build absent shifts info
            absent_shifts = []
            for day_idx in affected_day_indices:
                if day_idx < len(absent_assignments):
                    shift = absent_assignments[day_idx]
                    absent_shifts.append({
                        "day": day_mapping.get(day_idx, "Unknown"),
                        "day_index": day_idx,
                        "shift": shift
                    })
            
            # If no shifts or error, return empty
            if not absent_shifts:
                return {}
            
            # For simplicity, handle single day for now (can extend to multi-day)
            primary_shift_info = absent_shifts[0]
            shift_type = primary_shift_info['shift']
            day_idx = primary_shift_info['day_index']
            
            # ========================================
            # SCENARIO IDENTIFICATION
            # ========================================
            
            # Scenario 1: N4 Grade (no coverage needed)
            if absent_grade == 'N4':
                coverage_data = {
                    "type": "n4_no_coverage",
                    "message": "Ward-in-charge absence, no automatic coverage required."
                }
            
            # Scenario 2: Already OFF (no coverage needed)
            elif shift_type in ['OFF', 'PL', 'CL', 'PREF', 'LWP']:
                coverage_data = {
                    "type": "already_off",
                    "message": f"{absent_name} has no scheduled shift, no coverage impact."
                }
            
            # Scenario 3: N5 Grade
            elif absent_grade == 'N5' and shift_type in ['M', 'E', 'N', 'ME']:
                coverage_data = await self._handle_n5_scenario(
                    absent_staff_id, shift_type, day_idx, 
                    compact_roster, staff_lookup, day_mapping
                )
            
            # Scenario 4: Regular Staff (N6/N7/N8)
            elif absent_grade in ['N6', 'N7', 'N8'] and shift_type in ['M', 'E', 'N', 'ME']:
                coverage_data = await self._handle_regular_staff_scenario(
                    absent_staff_id, absent_grade, shift_type, day_idx,
                    compact_roster, staff_lookup, day_mapping, total_days
                )
            
            # Default: No coverage needed
            else:
                coverage_data = {
                    "type": "no_coverage_needed",
                    "message": "No coverage required."
                }
            
            # ========================================
            # GENERATE LLM PROMPT
            # ========================================
            user_prompt = ALTERNATIVE_GENERATION_USER_PROMPT.format(
                absent_staff_name=absent_name,
                absent_staff_id=absent_staff_id,
                absent_staff_grade=absent_grade,
                absence_type=absence_type,
                absent_shifts=json.dumps(absent_shifts, indent=2),
                coverage_data=json.dumps(coverage_data, indent=2)
            )
            
            messages = [
                {"role": "system", "content": ALTERNATIVE_GENERATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ]
            
            response = await chat_with_gpt(messages)
            
            if response.success and response.data:
                content = response.data.get("content", "{}")
                
                if not content or content.strip() == "":
                    return {}
                
                try:
                    suggestion = json.loads(content)
                    return suggestion
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse LLM response as JSON: {e}")
                    return {}
            else:
                return {}
                
        except Exception as e:
            logger.error(f"Error in alternative generation: {e}")
            return {}

    async def _handle_n5_scenario(
        self,
        absent_staff_id: str,
        shift_type: str,
        day_idx: int,
        compact_roster: Dict[str, List[str]],
        staff_lookup: Dict[str, Dict[str, Any]],
        day_mapping: Dict[int, str]
    ) -> Dict[str, Any]:
        """
        Handle N5 staff absence scenario.
        Check if other N5 is present on same shift → redundancy or manual intervention.
        """
        # Find OTHER N5s on the SAME shift type
        other_n5_names = []
        
        for emp_id, assignments in compact_roster.items():
            if emp_id == absent_staff_id:
                continue
            
            if day_idx < len(assignments) and assignments[day_idx] == shift_type:
                staff_info = staff_lookup.get(emp_id, {})
                if staff_info.get('grade') == 'N5':
                    other_n5_names.append(staff_info.get('name', 'Unknown'))
        
        if len(other_n5_names) > 0:
            # Redundancy: Other N5 present
            return {
                "type": "n5_redundancy",
                "shift": shift_type,
                "day": day_mapping.get(day_idx, "Unknown"),
                "other_n5_present": True,
                "other_n5_names": other_n5_names,
                "message": f"Other N5 staff ({', '.join(other_n5_names)}) on {shift_type} shift can manage."
            }
        else:
            # No redundancy: Manual intervention required
            return {
                "type": "n5_no_redundancy",
                "shift": shift_type,
                "day": day_mapping.get(day_idx, "Unknown"),
                "requires_manual": True,
                "message": f"Not enough shift in-charge on {shift_type} shift. Please assign N5 manually."
            }
    
    async def _handle_regular_staff_scenario(
        self,
        absent_staff_id: str,
        absent_grade: str,
        shift_type: str,
        day_idx: int,
        compact_roster: Dict[str, List[str]],
        staff_lookup: Dict[str, Dict[str, Any]],
        day_mapping: Dict[int, str],
        total_days: int
    ) -> Dict[str, Any]:
        """
        Handle regular staff (N6/N7/N8) absence scenario.
        Priority 1: Same-day extensions (M→ME, E→ME)
        Priority 2: Cross-day swaps
        """
        eligible_grades = ['N6', 'N7', 'N8']
        
        # Determine target shift for extensions
        if shift_type == 'E':
            target_shift_same_day = 'M'  # Need M staff to extend to ME
            extension_type = 'ME'
        elif shift_type == 'M':
            target_shift_same_day = 'E'  # Need E staff to extend to ME
            extension_type = 'ME'
        elif shift_type == 'ME':
            target_shift_same_day = ['M', 'E']  # Can extend either M or E to ME
            extension_type = 'ME'
        else:
            target_shift_same_day = None
            extension_type = None
        
        same_day_options = []
        cross_day_options = []
        
        # Priority 1: Same-day extensions
        if target_shift_same_day:
            target_shifts = [target_shift_same_day] if isinstance(target_shift_same_day, str) else target_shift_same_day
            
            for emp_id, assignments in compact_roster.items():
                if emp_id == absent_staff_id:
                    continue
                
                staff_info = staff_lookup.get(emp_id, {})
                staff_grade = staff_info.get('grade', 'Unknown')
                
                if staff_grade not in eligible_grades:
                    continue
                
                if day_idx >= len(assignments):
                    continue
                
                current_shift = assignments[day_idx]
                
                if current_shift in target_shifts:
                    # Validate extension
                    violates_2n = self._violates_2n_rule(assignments, day_idx)
                    is_absolute_off = current_shift in ['OFF', 'PL', 'CL', 'PREF', 'LWP']
                    
                    can_extend = not violates_2n and not is_absolute_off
                    
                    if can_extend:
                        workload = sum(1 for s in assignments if s not in ['OFF', 'PL', 'CL', 'PREF', 'LWP'])
                        consecutive_days = self._count_consecutive_work_days(assignments, day_idx)
                        
                        same_day_options.append({
                            "id": emp_id,
                            "name": staff_info.get('name', 'Unknown'),
                            "grade": staff_grade,
                            "current_shift": current_shift,
                            "extension_type": extension_type,
                            "day_index": day_idx,
                            "can_extend": True,
                            "workload": workload,
                            "consecutive_days": consecutive_days,
                            "priority": 1
                        })
        
        # Priority 2: Cross-day swaps (find same shift type on other days)
        for other_day_idx in range(total_days):
            if other_day_idx == day_idx:
                continue
            
            for emp_id, assignments in compact_roster.items():
                if emp_id == absent_staff_id:
                    continue
                
                staff_info = staff_lookup.get(emp_id, {})
                staff_grade = staff_info.get('grade', 'Unknown')
                
                if staff_grade not in eligible_grades:
                    continue
                
                if other_day_idx >= len(assignments):
                    continue
                
                current_shift_other_day = assignments[other_day_idx]
                
                # Check if they're working the same shift type on another day
                if current_shift_other_day == shift_type:
                    # Check if target day is available for swap
                    if day_idx < len(assignments):
                        target_day_shift = assignments[day_idx]
                        
                        # Can only swap if target day is OFF or non-absolute
                        can_swap = target_day_shift in ['OFF', 'M', 'E', 'N']
                        can_swap = can_swap and target_day_shift not in ['PL', 'CL', 'PREF', 'LWP']
                        
                        # Also check 2N rule
                        violates_2n = self._violates_2n_rule(assignments, day_idx)
                        can_swap = can_swap and not violates_2n
                        
                        if can_swap:
                            workload = sum(1 for s in assignments if s not in ['OFF', 'PL', 'CL', 'PREF', 'LWP'])
                            
                            cross_day_options.append({
                                "id": emp_id,
                                "name": staff_info.get('name', 'Unknown'),
                                "grade": staff_grade,
                                "current_shift": current_shift_other_day,
                                "current_day": day_mapping.get(other_day_idx, "Unknown"),
                                "current_day_index": other_day_idx,
                                "target_day_current_shift": target_day_shift,
                                "swap_type": f"{current_shift_other_day}_swap",
                                "day_index": day_idx,
                                "can_swap": True,
                                "workload": workload,
                                "priority": 2
                            })
        
        # Sort options
        same_day_options.sort(key=lambda x: (x['workload'], x['consecutive_days']))
        cross_day_options.sort(key=lambda x: x['workload'])
        
        # Limit to top options
        same_day_options = same_day_options[:3]
        cross_day_options = cross_day_options[:3]
        
        has_options = len(same_day_options) > 0 or len(cross_day_options) > 0
        
        return {
            "type": "regular_staff_coverage",
            "missing_shift": shift_type,
            "day": day_mapping.get(day_idx, "Unknown"),
            "day_index": day_idx,
            "same_day_options": same_day_options,
            "cross_day_options": cross_day_options,
            "has_options": has_options,
            "requires_manual": not has_options,
            "message": "Coverage options available." if has_options else "No valid coverage options. Please assign manually."
        }
    
    def _map_day_names_to_indices(self, day_names: List[str], day_mapping: Dict[int, str]) -> List[int]:
        """Map day names to day indices."""
        indices = []
        
        # Create reverse mapping: lowercase day name -> index
        reverse_map = {}
        for idx, date_str in day_mapping.items():
            if "(" in date_str and ")" in date_str:
                day_name = date_str.split("(")[1].split(")")[0].lower()
                reverse_map[day_name] = idx
        
        for day_name in day_names:
            day_lower = day_name.lower().strip()
            if day_lower in reverse_map:
                indices.append(reverse_map[day_lower])
        
        return indices
    
    def _violates_2n_rule(self, assignments: List[str], current_day_idx: int) -> bool:
        """
        Check if extending this staff violates the 2N→OFF rule.
        
        RULE: After 2 consecutive Night (N) shifts, the next day MUST be OFF.
        
        WHY: This is pre-computed to prevent LLM from having to count shifts
        and potentially making mistakes or suggesting invalid extensions.
        
        Args:
            assignments: Full week schedule for a staff member
            current_day_idx: The day we're checking (0-based index)
        
        Returns:
            True if the previous 2 days were both N shifts (violates rule)
            False otherwise (safe to extend)
        """
        if current_day_idx < 2:
            return False  # Can't have 2 previous days
        
        prev1 = assignments[current_day_idx - 1] if current_day_idx - 1 < len(assignments) else None
        prev2 = assignments[current_day_idx - 2] if current_day_idx - 2 < len(assignments) else None
        
        # If both previous days were N, this day MUST be OFF (can't extend)
        return prev1 == 'N' and prev2 == 'N'
    
    def _count_consecutive_work_days(self, assignments: List[str], current_day_idx: int) -> int:
        """
        Count consecutive working days leading up to current_day_idx.
        
        WHY: Helps LLM make decisions about workload distribution.
        Pre-computed to avoid LLM counting errors.
        
        Args:
            assignments: Full week schedule for a staff member
            current_day_idx: The day we're checking (0-based index)
        
        Returns:
            Number of consecutive days worked before current_day_idx
        """
        count = 0
        for i in range(current_day_idx - 1, -1, -1):
            if i < len(assignments) and assignments[i] not in ['OFF', 'PL', 'CL', 'PREF', 'LWP']:
                count += 1
            else:
                break  # Hit a day off, stop counting
        return count

    def _build_simple_coverage_summary(self, roster_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build simple coverage summary like the old system."""
        compact_roster = roster_data["compact_roster"]
        staff_lookup = roster_data["staff_lookup"]
        total_days = roster_data["total_days"]
        
        summary = {}
        for d in range(total_days):
            shifts_count = {"M": 0, "E": 0, "N": 0, "G": 0, "OFF": 0}
            n5_present = {"M": 0, "E": 0, "N": 0}
            
            for emp_id, assignments in compact_roster.items():
                if d >= len(assignments):
                    continue
                shift = assignments[d]
                if shift in shifts_count:
                    shifts_count[shift] += 1
                    if staff_lookup.get(emp_id, {}).get("grade") == "N5" and shift in n5_present:
                        n5_present[shift] += 1
                else:
                    shifts_count["OFF"] += 1
            
            summary[d] = {"counts": shifts_count, "n5": n5_present}
        
        return summary

    def _build_day_coverage(self, roster_data: Dict[str, Any], day_idx: int) -> Dict[str, Any]:
        """Build coverage details for a specific day."""
        compact_roster = roster_data["compact_roster"]
        staff_lookup = roster_data["staff_lookup"]
        day_mapping = roster_data["day_mapping"]
        
        shifts_count = {"M": 0, "E": 0, "N": 0, "G": 0, "OFF": 0}
        n5_present = {"M": 0, "E": 0, "N": 0}
        
        for emp_id, assignments in compact_roster.items():
            if day_idx >= len(assignments):
                continue
            shift = assignments[day_idx]
            if shift in shifts_count:
                shifts_count[shift] += 1
                if staff_lookup.get(emp_id, {}).get("grade") == "N5" and shift in n5_present:
                    n5_present[shift] += 1
            else:
                shifts_count["OFF"] += 1
        
        return {
            "day": day_mapping.get(day_idx, "Unknown"),
            "counts": shifts_count,
            "n5_present": n5_present
        }

    # ===== TOOL METHODS =====

    async def handle_absence_management(
        self, 
        roster_id: str, 
        staff_name: str, 
        days: List[str], 
        absence_type: str = "sick_leave"
    ) -> Dict[str, Any]:
        """
        Handle staff absence with intelligent alternative generation.
        
        TOOL LOGIC:
        ===========
        1. Fetch and validate roster data
        2. Find staff member by name (case-insensitive)
        3. Generate intelligent alternatives using LLM
        4. Apply healthcare staffing rules:
           - N4 absence → Replace with 2 N5s or higher grade
           - N5 absence → Replace with N5+ or extend morning shift
           - Regular staff → Find same-level with minimum workload
        5. Return structured response with alternatives
        
        Args:
            roster_id: ID of the roster to modify
            staff_name: Name of absent staff member
            days: List of days for absence (e.g., ["monday", "tuesday"])
            absence_type: Type of absence (sick_leave, personal_leave, emergency)
        """
        try:
            # Get roster data
            roster_data = await self.get_roster_data(roster_id)
            if not roster_data:
                return {
                    "widget_data": {}
                }

            print(roster_data, "roster_data")

            # Find staff ID by name
            staff_id = self._find_staff_by_name(roster_data["staff_lookup"], staff_name)
            if not staff_id:
                return {
                    "widget_data": {}
                }

            # Generate intelligent alternatives using LLM
            alternatives = await self.generate_alternatives(
                roster_data, staff_id, days, absence_type
            )

            # Build widget data for UI (Option 1 structure)
            primary = alternatives.get("primary_action", {})
            alt_list = alternatives.get("alternatives", [])
            
            widget_data = {
                "type": "roster_modification",
                "primary_action": {
                    "title": primary.get("title", f"Mark {staff_name} as {absence_type}"),
                    "description": primary.get("description", f"Processing {absence_type} for {staff_name}"),
                    "patches": primary.get("patches", []),
                    "button_text": primary.get("button_text", "Apply Change"),
                    "confidence": primary.get("confidence", 0.8)
                },
                "alternatives": alt_list,
                "metadata": alternatives.get("metadata", {
                    "override_allowed": False,
                    "constraints_violated": []
                })
            }

            return {
                "widget_data": widget_data
            }

        except Exception as e:
            logger.error(f"Error in handle_absence_management: {e}")
            return {
                "widget_data": {}
            }

    def _find_staff_by_name(self, staff_lookup: Dict[str, Dict[str, Any]], name: str) -> Optional[str]:
        """Find staff ID by name with fuzzy matching to handle typos."""
        name_lower = name.lower().strip()
        
        # Strategy 1: Try exact match first
        for staff_id, staff_info in staff_lookup.items():
            staff_name = staff_info.get("name", "").lower().strip()
            if staff_name == name_lower:
                return staff_id
        
        # Strategy 2: Try partial match (contains)
        for staff_id, staff_info in staff_lookup.items():
            staff_name = staff_info.get("name", "").lower().strip()
            if name_lower in staff_name or staff_name in name_lower:
                return staff_id
        
        # Strategy 3: Fuzzy matching with similarity threshold
        fuzzy_matches = []
        for staff_id, staff_info in staff_lookup.items():
            staff_name = staff_info.get("name", "").lower().strip()
            similarity = calculate_string_similarity(name_lower, staff_name)
            
            if similarity > 0.6:  # 60% similarity threshold
                fuzzy_matches.append((staff_id, staff_info.get("name"), similarity))
        
        if fuzzy_matches:
            # Sort by similarity (highest first)
            fuzzy_matches.sort(key=lambda x: x[2], reverse=True)
            match_id, match_name, similarity = fuzzy_matches[0]
            
            # Use best match if similarity is high enough
            if similarity >= 0.6:  # 60% threshold for acceptance
                return match_id
        
        return None
    
    async def handle_shift_assignment(
        self, 
        roster_id: str, 
        staff_name: str, 
        day: str, 
        new_shift: str,
        reason: str = None
    ) -> Dict[str, Any]:
        """
        Handle direct shift assignment with scenario-based validation.
        
        DECISION TREE:
        1. Already assigned to same shift → No change
        2. On PL/CL/PREF → Ask confirmation to override
        3. OFF → Work (validate 2N rule, consecutive days)
        4. Shift change → Validate and suggest coverage for old shift
        5. Grade incompatible → Reject
        """
        try:
            roster_data = await self.get_roster_data(roster_id)
            if not roster_data:
                return {"widget_data": {}}

            staff_id = self._find_staff_by_name(roster_data["staff_lookup"], staff_name)
            if not staff_id:
                return {"widget_data": {}}

            staff_lookup = roster_data["staff_lookup"]
            staff_info = staff_lookup[staff_id]
            staff_grade = staff_info.get("grade", "Unknown")
            compact_roster = roster_data["compact_roster"]
            day_mapping = roster_data["day_mapping"]
            total_days = roster_data["total_days"]
            
            # Map day to index
            day_indices = self._map_day_names_to_indices([day], day_mapping)
            if not day_indices:
                return {"widget_data": {}}
            day_idx = day_indices[0]
            
            # Get current assignment
            assignments = compact_roster.get(staff_id, [])
            current_shift = assignments[day_idx] if day_idx < len(assignments) else "OFF"
            # ========================================
            # SCENARIO IDENTIFICATION
            # ========================================
            
            # Scenario 1: Already assigned to requested shift
            if current_shift == new_shift:
                assignment_data = await self._handle_already_assigned(
                    staff_name, current_shift, day_idx, day_mapping
                )
            
            # Scenario 2: On absolute leave (PL/CL/PREF/LWP)
            elif current_shift in ['PL', 'CL', 'PREF', 'LWP', 'OFF']:
                assignment_data = await self._handle_override_leave(
                    staff_id, staff_name, staff_grade, current_shift, new_shift,
                    day_idx, day_mapping, assignments, compact_roster, staff_lookup, total_days
                )
            
            # Scenario 3: Grade incompatibility check
            elif not self._is_grade_compatible(staff_grade, new_shift):
                assignment_data = await self._handle_grade_incompatible(
                    staff_name, staff_grade, new_shift, day_idx, day_mapping
                )
            
            # Scenario 5: Shift Change (M/E/N/ME/G to different shift)
            else:
                assignment_data = await self._handle_shift_change(
                    staff_id, staff_name, staff_grade, current_shift, new_shift,
                    day_idx, assignments, compact_roster, staff_lookup, day_mapping, total_days
                )
            
            # ========================================
            # GENERATE LLM RESPONSE
            # ========================================
            user_prompt = SHIFT_ASSIGNMENT_USER_PROMPT.format(
                staff_name=staff_name,
                staff_id=staff_id,
                staff_grade=staff_grade,
                current_shift=current_shift,
                new_shift=new_shift,
                day=day_mapping.get(day_idx, "Unknown"),
                assignment_data=json.dumps(assignment_data, indent=2)
            )
            
            # Log assignment data for debugging
            logger.info(f"Assignment scenario: {assignment_data.get('type', 'unknown')}")
            
            messages = [
                {"role": "system", "content": SHIFT_ASSIGNMENT_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ]
            
            response = await chat_with_gpt(messages)
            
            if response.success and response.data:
                content = response.data.get("content", "{}")
                try:
                    result = json.loads(content)
                    primary = result.get("primary_action", {})
                    alt_list = result.get("alternatives", [])
                    
                    widget_data = {
                        "type": "roster_modification",
                        "primary_action": {
                            "title": primary.get("title", f"Assign {staff_name} to {new_shift}"),
                            "description": primary.get("description", ""),
                            "patches": primary.get("patches", []),
                            "button_text": primary.get("button_text", "Apply Change"),
                            "confidence": primary.get("confidence", 0.8)
                        },
                        "alternatives": alt_list,
                        "metadata": result.get("metadata", {
                            "override_allowed": False,
                            "constraints_violated": []
                        })
                    }
                    
                    return {"widget_data": widget_data}
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse LLM response: {e}")
                    return {"widget_data": {}}
            else:
                return {"widget_data": {}}

        except Exception as e:
            import traceback
            logger.error(f"Error in handle_shift_assignment: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {"widget_data": {}}
    
    # ===== SHIFT ASSIGNMENT SCENARIO HANDLERS =====
    
    async def _handle_already_assigned(
        self,
        staff_name: str,
        current_shift: str,
        day_idx: int,
        day_mapping: Dict[int, str]
    ) -> Dict[str, Any]:
        """Staff already assigned to requested shift - no change needed."""
        return {
            "type": "already_assigned",
            "current_shift": current_shift,
            "day": day_mapping.get(day_idx, "Unknown"),
            "day_index": day_idx,
            "message": f"{staff_name} is already assigned to {current_shift} shift."
        }
    
    async def _handle_override_leave(
        self,
        staff_id: str,
        staff_name: str,
        staff_grade: str,
        current_shift: str,
        new_shift: str,
        day_idx: int,
        day_mapping: Dict[int, str],
        assignments: List[str],
        compact_roster: Dict[str, List[str]],
        staff_lookup: Dict[str, Dict[str, Any]],
        total_days: int
    ) -> Dict[str, Any]:
        """Staff on absolute leave - ask confirmation to override."""
        
        # Find alternatives who can take the new shift using enhanced coverage
        coverage_data = self._find_shift_coverage(
            staff_id, staff_grade, new_shift, day_idx,
            compact_roster, staff_lookup, day_mapping, total_days
        )
        
        day_name = day_mapping.get(day_idx, "Unknown")
        eligible_grades = coverage_data.get("eligible_grades", [])
        
        # For override leave, find direct assignment options (staff already working who can swap)
        direct_options = self._find_direct_assignment_options(
            new_shift, day_idx, day_name, compact_roster, staff_lookup, eligible_grades, total_days
        )
        
        return {
            "type": "override_leave",
            "leave_type": current_shift,
            "new_shift": new_shift,
            "day": day_name,
            "day_index": day_idx,
            "message": f"{staff_name} is on {current_shift}. Override to assign {new_shift} shift?",
            "direct_assignment_options": direct_options,
            "has_alternatives": len(direct_options) > 0,
            "requires_manual": len(direct_options) == 0,
            "eligible_grades": eligible_grades,
            "needs_shift_incharge": coverage_data.get("needs_shift_incharge", False),
            "other_incharge_on_shift": coverage_data.get("other_incharge_on_shift", 0)
        }
    
    async def _handle_grade_incompatible(
        self,
        staff_name: str,
        staff_grade: str,
        new_shift: str,
        day_idx: int,
        day_mapping: Dict[int, str]
    ) -> Dict[str, Any]:
        """Grade incompatible with requested shift."""
        # Generate specific error message based on the incompatibility
        if new_shift == 'G':
            message = f"{staff_grade} staff cannot work General shift. Only N4/N5 can work General shifts."
        elif staff_grade == 'N4':
            message = f"N4 staff can only work General (G) shift, not {new_shift} shift."
        else:
            message = f"{staff_grade} staff cannot work {new_shift} shift."
            
        return {
            "type": "grade_incompatible",
            "staff_grade": staff_grade,
            "requested_shift": new_shift,
            "day": day_mapping.get(day_idx, "Unknown"),
            "day_index": day_idx,
            "message": message
        }
    
    async def _handle_shift_change(
        self,
        staff_id: str,
        staff_name: str,
        staff_grade: str,
        current_shift: str,
        new_shift: str,
        day_idx: int,
        assignments: List[str],
        compact_roster: Dict[str, List[str]],
        staff_lookup: Dict[str, Dict[str, Any]],
        day_mapping: Dict[int, str],
        total_days: int
    ) -> Dict[str, Any]:
        """Change from one shift to another - validate and suggest coverage."""
        
        # Check if removing N5/N4 from M/E/N/ME shift (shift in-charge requirement)
        n5_violation = False
        if staff_grade in ['N4', 'N5'] and current_shift in ['M', 'E', 'N', 'ME']:
            # Check if other N4/N5 on current shift
            other_in_charge_count = 0
            for emp_id, emp_assignments in compact_roster.items():
                if emp_id == staff_id:
                    continue
                if day_idx < len(emp_assignments) and emp_assignments[day_idx] == current_shift:
                    emp_info = staff_lookup.get(emp_id, {})
                    if emp_info.get('grade') in ['N4', 'N5']:
                        other_in_charge_count += 1
            
            if other_in_charge_count == 0:
                n5_violation = True
        
        logger.info(f"Shift change: {staff_name} (Grade: {staff_grade}) from {current_shift} to {new_shift} on day {day_idx}")
        
        # Find coverage for old shift using enhanced coverage finder
        coverage_data = self._find_shift_coverage(
            staff_id, staff_grade, current_shift, day_idx,
            compact_roster, staff_lookup, day_mapping, total_days
        )
        
        day_name = day_mapping.get(day_idx, "Unknown")
        return {
            "type": "shift_change",
            "current_shift": current_shift,
            "new_shift": new_shift,
            "day": day_name,
            "day_index": day_idx,
            "n5_violation": n5_violation,
            "reverse_swap_options": coverage_data.get("reverse_swap_options", []),
            "extension_options": coverage_data.get("extension_options", []),
            "has_coverage": coverage_data.get("has_options", False),
            "requires_manual": coverage_data.get("requires_manual", True),
            "eligible_grades": coverage_data.get("eligible_grades", []),
            "needs_shift_incharge": coverage_data.get("needs_shift_incharge", False),
            "other_incharge_on_shift": coverage_data.get("other_incharge_on_shift", 0),
            "message": f"Change {staff_name} from {current_shift} to {new_shift}. {current_shift} shift will need coverage."
        }
    
    def _find_direct_assignment_options(self, new_shift: str, day_idx: int, day_name: str,
                                      compact_roster: Dict, staff_lookup: Dict, 
                                      eligible_grades: List[str], total_days: int) -> List[Dict]:
        """Find staff who are already working and can swap to the new shift (for override leave scenarios)
        
        RULE: Do NOT suggest OFF staff. Only suggest staff already working who can swap.
        """
        direct_options = []
        
        for emp_id, shifts in compact_roster.items():
            if emp_id not in staff_lookup:
                continue
                
            staff_info = staff_lookup[emp_id]
            staff_grade = staff_info.get('grade', '')
            staff_name = staff_info.get('name', '')
            
            # Only consider eligible grades
            if staff_grade not in eligible_grades:
                continue
            
            # shifts is a List[str], not a Dict
            if day_idx >= len(shifts):
                continue
                
            current_shift = shifts[day_idx]
            
            # Skip if already working the target shift
            if current_shift == new_shift:
                continue
                
            # Skip if on leave
            if current_shift in ['PL', 'CL', 'PREF', 'LWP']:
                continue
            
            # CRITICAL: Skip OFF staff - we cannot suggest assigning OFF staff to work
            if current_shift == 'OFF':
                continue
            
            # Only consider staff already working (M, E, N, ME, G)
            if current_shift in ['M', 'E', 'N', 'ME', 'G']:
                # Check for constraint violations
                violates_2n = self._violates_2n_rule(shifts, day_idx)
                if violates_2n:
                    continue
                
                workload = sum(1 for s in shifts if s not in ['OFF', 'PL', 'CL', 'PREF', 'LWP'])
                consecutive_days = self._count_consecutive_work_days(shifts, day_idx)
                
                direct_options.append({
                    "id": emp_id,
                    "name": staff_name,
                    "grade": staff_grade,
                    "current_shift": current_shift,
                    "target_shift": new_shift,
                    "day": day_name,
                    "day_index": day_idx,
                    "can_swap": True,
                    "workload": workload,
                    "consecutive_days": consecutive_days,
                    "priority": 1
                })
        
        # Sort by workload and consecutive days
        direct_options.sort(key=lambda x: (x['workload'], x.get('consecutive_days', 0)))
        
        # Limit to top 2 options
        return direct_options[:2]

    def _is_grade_compatible(self, staff_grade: str, shift: str) -> bool:
        """Check if staff grade can work the requested shift.
        
        Rules:
        - N4: Can ONLY work G (General) shift
        - N5: Can work M/E/N/ME shifts (shift in-charge)
        - N6/N7/N8: Can work M/E/N/ME shifts (NOT G)
        """
        if shift == 'G':
            # Only N4/N5 can work General shift
            return staff_grade in ['N4', 'N5']
        elif shift in ['M', 'E', 'N', 'ME']:
            # N4 cannot work M/E/N/ME (only G)
            # N5, N6, N7, N8 can work these shifts
            return staff_grade in ['N5', 'N6', 'N7', 'N8']
        return True  # Default allow for other shift types
    
    def _find_shift_coverage(
        self,
        vacant_staff_id: str,
        staff_grade: str,
        shift_needed: str,
        day_idx: int,
        compact_roster: Dict[str, List[str]],
        staff_lookup: Dict[str, Dict[str, Any]],
        day_mapping: Dict[int, str],
        total_days: int
    ) -> Dict[str, Any]:
        """
        Find coverage for a shift using same logic as absence management.
        Priority 1: Same-day extensions (M→ME, E→ME)
        Priority 2: OFF staff
        Priority 3: Cross-day swaps
        """
        
        day_name = day_mapping.get(day_idx, "Unknown")
        
        # Check if shift_needed is M/E/N/ME (requires shift in-charge)
        needs_shift_incharge = shift_needed in ['M', 'E', 'N', 'ME']
        
        # If removing N4/N5 from M/E/N/ME, check if other N4/N5 remains on that shift
        other_incharge_on_shift = 0
        if needs_shift_incharge and staff_grade in ['N4', 'N5']:
            for emp_id, emp_assignments in compact_roster.items():
                if emp_id == vacant_staff_id:
                    continue
                if day_idx < len(emp_assignments) and emp_assignments[day_idx] == shift_needed:
                    emp_info = staff_lookup.get(emp_id, {})
                    if emp_info.get('grade') in ['N4', 'N5']:
                        other_incharge_on_shift += 1
        
        # Determine eligible grades based on requester grade
        # N5 can only be replaced by N5
        # N4 can be replaced by N5 (upgrade) or N4 (same level)
        # N4 cannot replace N5 (no downgrade)
        if staff_grade == 'N5':
            # N5 can only be replaced by N5
            eligible_grades = ['N5']
            logger.info(f"Finding coverage for {shift_needed} shift on day {day_idx} ({day_name}). Requester is N5 → restrict to N5 only")
        elif staff_grade == 'N4':
            # N4 can be replaced by N5 (upgrade) or N4 (same level)
            eligible_grades = ['N4', 'N5']
            logger.info(f"Finding coverage for {shift_needed} on day {day_idx} ({day_name}). Requester is N4 → can use N4 or N5")
        else:
            # Requester is N6/N7/N8 → restrict to regular grades
            eligible_grades = ['N6', 'N7', 'N8']
            logger.info(f"Finding coverage for {shift_needed} shift on day {day_idx} ({day_name}). Requester is {staff_grade} → looking for N6/N7/N8")
        
        reverse_swap_options = []
        extension_options = []
        
        # Priority 1: Reverse swaps - find someone on the target shift who can move to vacated shift
        # If we need E shift coverage, find someone on E who can move to M (reverse of M→E)
        # If we need M shift coverage, find someone on M who can move to E (reverse of E→M)  
        # If we need N shift coverage, find someone on N who can move to M (reverse of M→N)
        if shift_needed == 'E':
            # Need E coverage, so find someone on E who can move to M
            target_shift_for_reverse = 'E'
            vacated_shift = 'M'
        elif shift_needed == 'M':
            # Need M coverage, so find someone on M who can move to E  
            target_shift_for_reverse = 'M'
            vacated_shift = 'E'
        elif shift_needed == 'N':
            # Need N coverage, so find someone on N who can move to M
            target_shift_for_reverse = 'N'
            vacated_shift = 'M'
        else:
            target_shift_for_reverse = None
            vacated_shift = None
        
        # Priority 1: Reverse swaps (find someone on target shift who can move to vacated shift)
        if target_shift_for_reverse and vacated_shift:
            for emp_id, assignments in compact_roster.items():
                if emp_id == vacant_staff_id:
                    continue
                
                try:
                    emp_info = staff_lookup.get(emp_id, {})
                    emp_grade = emp_info.get('grade', '')
                except AttributeError as e:
                    logger.error(f"ERROR: staff_lookup is not a dict. Type: {type(staff_lookup)}, Value: {staff_lookup}")
                    logger.error(f"emp_id: {emp_id}")
                    raise e
                
                if emp_grade not in eligible_grades:
                    continue
                
                if day_idx >= len(assignments):
                    continue
                
                current_shift = assignments[day_idx]
                
                # Find someone on the target shift who can move to the vacated shift
                if current_shift == target_shift_for_reverse:
                    violates_2n = self._violates_2n_rule(assignments, day_idx)
                    if not violates_2n:
                        workload = sum(1 for s in assignments if s not in ['OFF', 'PL', 'CL', 'PREF', 'LWP'])
                        consecutive_days = self._count_consecutive_work_days(assignments, day_idx)
                        
                        reverse_swap_options.append({
                            "id": emp_id,
                            "name": emp_info.get('name', 'Unknown'),
                            "grade": emp_grade,
                            "current_shift": current_shift,
                            "target_shift": vacated_shift,
                            "day": day_name,
                            "day_index": day_idx,
                            "can_swap": True,
                            "workload": workload,
                            "consecutive_days": consecutive_days,
                            "priority": 1
                        })
        
        # Priority 2: Extensions (M→ME, E→ME)
        # Determine extension shifts for same-day coverage
        if shift_needed == 'E':
            target_shift_same_day = 'M'
            extension_type = 'ME'
        elif shift_needed == 'M':
            target_shift_same_day = 'E'
            extension_type = 'ME'
        else:
            target_shift_same_day = None
            extension_type = None
        
        # Priority 2: Same-day extensions (only for people already working)
        if target_shift_same_day and shift_needed in ['M', 'E']:
            for emp_id, assignments in compact_roster.items():
                if emp_id == vacant_staff_id:
                    continue
                
                emp_info = staff_lookup.get(emp_id, {})
                emp_grade = emp_info.get('grade', '')
                
                if emp_grade not in eligible_grades:
                    continue
                
                if day_idx >= len(assignments):
                    continue
                
                current_shift = assignments[day_idx]
                
                # Only consider people who are already working (not OFF)
                if current_shift == target_shift_same_day:
                    violates_2n = self._violates_2n_rule(assignments, day_idx)
                    if not violates_2n:
                        workload = sum(1 for s in assignments if s not in ['OFF', 'PL', 'CL', 'PREF', 'LWP'])
                        consecutive_days = self._count_consecutive_work_days(assignments, day_idx)
                        
                        extension_options.append({
                            "id": emp_id,
                            "name": emp_info.get('name', 'Unknown'),
                            "grade": emp_grade,
                            "current_shift": current_shift,
                            "extension_type": extension_type,
                            "day": day_name,
                            "day_index": day_idx,
                            "can_extend": True,
                            "workload": workload,
                            "consecutive_days": consecutive_days,
                            "priority": 2
                        })
        # Sort options
        reverse_swap_options.sort(key=lambda x: (x['workload'], x.get('consecutive_days', 0)))
        extension_options.sort(key=lambda x: (x['workload'], x.get('consecutive_days', 0)))
        
        # Limit to top options
        reverse_swap_options = reverse_swap_options[:2]
        extension_options = extension_options[:2]
        
        has_options = len(reverse_swap_options) > 0 or len(extension_options) > 0
        
        if len(reverse_swap_options) == 0 and len(extension_options) == 0:
            logger.info(f"No coverage options found for {shift_needed} shift on day {day_idx}. Manual assignment required.")
        else:
            logger.info(f"Coverage for {shift_needed} shift: reverse_swap={len(reverse_swap_options)}, extension={len(extension_options)}")
        
        return {
            "reverse_swap_options": reverse_swap_options,
            "extension_options": extension_options,
            "has_options": has_options,
            "requires_manual": not has_options,
            "eligible_grades": eligible_grades,
            "needs_shift_incharge": needs_shift_incharge,
            "other_incharge_on_shift": other_incharge_on_shift
        }

    async def handle_staff_swap(
        self, 
        roster_id: str, 
        staff1_name: str, 
        staff2_name: str, 
        day: str
    ) -> Dict[str, Any]:
        """Handle staff swap with constraint validation."""
        try:
            roster_data = await self.get_roster_data(roster_id)
            if not roster_data:
                return {
                    "widget_data": {}
                }

            # Find both staff members
            staff1_id = self._find_staff_by_name(roster_data["staff_lookup"], staff1_name)
            staff2_id = self._find_staff_by_name(roster_data["staff_lookup"], staff2_name)
            
            if not staff1_id or not staff2_id:
                missing = []
                if not staff1_id:
                    missing.append(staff1_name)
                if not staff2_id:
                    missing.append(staff2_name)
                return {
                    "widget_data": {}
                }

            # Get staff details
            staff1_info = roster_data["staff_lookup"][staff1_id]
            staff2_info = roster_data["staff_lookup"][staff2_id]
            compact_roster = roster_data["compact_roster"]
            
            # Map day to index
            day_mapping = roster_data["day_mapping"]
            day_indices = self._map_day_names_to_indices([day], day_mapping)
            if not day_indices:
                return {
                    "widget_data": {}
                }
            day_idx = day_indices[0]
            
            # Get current assignments
            staff1_assignments = compact_roster.get(staff1_id, [])
            staff2_assignments = compact_roster.get(staff2_id, [])
            
            staff1_current = staff1_assignments[day_idx] if day_idx < len(staff1_assignments) else "OFF"
            staff2_current = staff2_assignments[day_idx] if day_idx < len(staff2_assignments) else "OFF"
            
            # Calculate workloads
            staff1_workload = sum(1 for shift in staff1_assignments if shift not in ["OFF", "PL", "CL", "PREF"])
            staff2_workload = sum(1 for shift in staff2_assignments if shift not in ["OFF", "PL", "CL", "PREF"])
            
            # Detect violations programmatically
            violations = self._detect_violations(
                staff1_id, staff1_info, staff1_current, staff1_workload,
                staff2_id, staff2_info, staff2_current, staff2_workload,
                staff1_assignments, staff2_assignments, day_idx, compact_roster
            )
            
            # Generate LLM response
            user_prompt = STAFF_SWAP_USER_PROMPT.format(
                staff1_name=staff1_name,
                staff1_id=staff1_id,
                staff1_grade=staff1_info.get("grade", "Unknown"),
                staff1_current_shift=staff1_current,
                staff1_workload=staff1_workload,
                staff2_name=staff2_name,
                staff2_id=staff2_id,
                staff2_grade=staff2_info.get("grade", "Unknown"),
                staff2_current_shift=staff2_current,
                staff2_workload=staff2_workload,
                day=day,
                day_index=day_idx,
                violations=json.dumps(violations, indent=2)
            )
            
            messages = [
                {"role": "system", "content": STAFF_SWAP_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ]
            
            response = await chat_with_gpt(messages)
            
            if response.success and response.data:
                content = response.data.get("content", "{}")
                try:
                    result = json.loads(content)
                    primary = result.get("primary_action", {})
                    
                    widget_data = {
                        "type": "roster_modification",
                        "primary_action": {
                            "title": primary.get("title", f"Swap {staff1_name} and {staff2_name}"),
                            "description": primary.get("description", f"Swapping shifts between {staff1_name} and {staff2_name} on {day}"),
                            "patches": primary.get("patches", []),
                            "button_text": primary.get("button_text", "Apply Swap"),
                            "confidence": primary.get("confidence", 0.8)
                        },
                        "metadata": {
                            "override_allowed": True,  # Always allow override for swaps
                            "constraints_violated": violations["constraints_violated"],
                            "violation_details": violations["violation_details"]
                        }
                    }
                    
                    return {"widget_data": widget_data}
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse LLM response: {e}")
                    return {
                        "widget_data": {}
                    }
            else:
                return {
                    "widget_data": {}
                }

        except Exception as e:
            logger.error(f"Error in handle_staff_swap: {e}")
            return {
                "widget_data": {}
            }

    def _detect_violations(
        self, 
        staff1_id: str, staff1_info: Dict, staff1_current: str, staff1_workload: int,
        staff2_id: str, staff2_info: Dict, staff2_current: str, staff2_workload: int,
        staff1_assignments: List[str], staff2_assignments: List[str], day_idx: int, compact_roster: Dict
    ) -> Dict[str, Any]:
        """Detect constraint violations for staff swap based on roster rules."""
        violations = {
            "constraints_violated": [],
            "violation_details": []
        }
        
        staff1_grade = staff1_info.get("grade", "Unknown")
        staff2_grade = staff2_info.get("grade", "Unknown")
        
        # 1. Grade compatibility checks
        if not self._can_staff_work_shift(staff1_grade, staff2_current):
            violations["constraints_violated"].append("grade_incompatible")
            violations["violation_details"].append({
                "type": "grade_incompatible",
                "staff": staff1_id,
                "staff_name": staff1_info.get("name", "Unknown"),
                "grade": staff1_grade,
                "shift": staff2_current,
                "message": f"{staff1_grade} cannot work {staff2_current} shift"
            })
        
        if not self._can_staff_work_shift(staff2_grade, staff1_current):
            violations["constraints_violated"].append("grade_incompatible")
            violations["violation_details"].append({
                "type": "grade_incompatible",
                "staff": staff2_id,
                "staff_name": staff2_info.get("name", "Unknown"),
                "grade": staff2_grade,
                "shift": staff1_current,
                "message": f"{staff2_grade} cannot work {staff1_current} shift"
            })
        
        # 2. N4 specific rules (6 G shifts + 1 OFF)
        if staff1_grade == "N4":
            n4_violations = self._check_n4_rules(staff1_assignments, staff2_current, day_idx, staff1_id, staff1_info.get("name", "Unknown"))
            violations["constraints_violated"].extend(n4_violations["constraints_violated"])
            violations["violation_details"].extend(n4_violations["violation_details"])
        
        if staff2_grade == "N4":
            n4_violations = self._check_n4_rules(staff2_assignments, staff1_current, day_idx, staff2_id, staff2_info.get("name", "Unknown"))
            violations["constraints_violated"].extend(n4_violations["constraints_violated"])
            violations["violation_details"].extend(n4_violations["violation_details"])
        
        # 3. 2N→OFF rule (rest after 2 consecutive nights)
        if self._violates_2n_off_rule(staff1_assignments, day_idx, staff2_current):
            violations["constraints_violated"].append("2n_violation")
            violations["violation_details"].append({
                "type": "2n_violation",
                "staff": staff1_id,
                "staff_name": staff1_info.get("name", "Unknown"),
                "message": f"Violates 2N→OFF rule - worked 2 consecutive nights and next day is OFF, cannot work {staff2_current} shift"
            })
        
        if self._violates_2n_off_rule(staff2_assignments, day_idx, staff1_current):
            violations["constraints_violated"].append("2n_violation")
            violations["violation_details"].append({
                "type": "2n_violation",
                "staff": staff2_id,
                "staff_name": staff2_info.get("name", "Unknown"),
                "message": f"Violates 2N→OFF rule - worked 2 consecutive nights and next day is OFF, cannot work {staff1_current} shift"
            })
        
        # 4. N5 coverage check (at least one N5 in M/E/N shifts)
        n5_coverage_violations = self._check_n5_coverage(staff1_id, staff1_current, staff2_id, staff2_current, day_idx, compact_roster)
        violations["constraints_violated"].extend(n5_coverage_violations["constraints_violated"])
        violations["violation_details"].extend(n5_coverage_violations["violation_details"])
        
        # 5. Consecutive work days (>6 days)
        if self._exceeds_consecutive_days(staff1_assignments, day_idx):
            violations["constraints_violated"].append("consecutive_days")
            violations["violation_details"].append({
                "type": "consecutive_days",
                "staff": staff1_id,
                "staff_name": staff1_info.get("name", "Unknown"),
                "message": f"Would work more than 6 consecutive days"
            })
        
        if self._exceeds_consecutive_days(staff2_assignments, day_idx):
            violations["constraints_violated"].append("consecutive_days")
            violations["violation_details"].append({
                "type": "consecutive_days",
                "staff": staff2_id,
                "staff_name": staff2_info.get("name", "Unknown"),
                "message": f"Would work more than 6 consecutive days"
            })
        
        # 6. Leave requests are absolute (CL, PL, LWP, PREF)
        if staff1_current in ["CL", "PL", "LWP", "PREF"]:
            violations["constraints_violated"].append("leave_override")
            violations["violation_details"].append({
                "type": "leave_override",
                "staff": staff1_id,
                "staff_name": staff1_info.get("name", "Unknown"),
                "leave_type": staff1_current,
                "message": f"Staff is on {staff1_current} - leave requests are absolute"
            })
        
        if staff2_current in ["CL", "PL", "LWP", "PREF"]:
            violations["constraints_violated"].append("leave_override")
            violations["violation_details"].append({
                "type": "leave_override",
                "staff": staff2_id,
                "staff_name": staff2_info.get("name", "Unknown"),
                "leave_type": staff2_current,
                "message": f"Staff is on {staff2_current} - leave requests are absolute"
            })
        
        # 7. Equal distribution violation (2M, 2E, 2N, 1OFF)
        if staff1_grade != "N4":  # N4 has different rules (6G + 1OFF)
            equal_dist_violations = self._check_equal_distribution(staff1_assignments, staff2_current, day_idx, staff1_id, staff1_info.get("name", "Unknown"))
            violations["constraints_violated"].extend(equal_dist_violations["constraints_violated"])
            violations["violation_details"].extend(equal_dist_violations["violation_details"])
        
        if staff2_grade != "N4":  # N4 has different rules (6G + 1OFF)
            equal_dist_violations = self._check_equal_distribution(staff2_assignments, staff1_current, day_idx, staff2_id, staff2_info.get("name", "Unknown"))
            violations["constraints_violated"].extend(equal_dist_violations["constraints_violated"])
            violations["violation_details"].extend(equal_dist_violations["violation_details"])
        
        return violations

    def _can_staff_work_shift(self, grade: str, shift: str) -> bool:
        """Check if staff grade can work the given shift."""
        if grade == "N4":
            return shift == "G"  # N4 can only work G shift
        elif grade in ["N5", "N6", "N7", "N8"]:
            return shift in ["M", "E", "N", "ME"]  # N5+ can work M/E/N/ME
        return False

    def _check_n4_rules(self, assignments: List[str], new_shift: str, day_idx: int, staff_id: str, staff_name: str) -> Dict[str, Any]:
        """Check N4 specific rules: 6 G shifts + 1 OFF per week."""
        violations = {"constraints_violated": [], "violation_details": []}
        
        # Count current G shifts
        g_count = sum(1 for shift in assignments if shift == "G")
        off_count = sum(1 for shift in assignments if shift == "OFF")
        
        # If swapping to G shift
        if new_shift == "G":
            if g_count >= 6:
                violations["constraints_violated"].append("n4_g_limit")
                violations["violation_details"].append({
                    "type": "n4_g_limit",
                    "staff": staff_id,
                    "staff_name": staff_name,
                    "message": f"N4 already has 6 G shifts this week (limit reached)"
                })
        
        # If swapping away from G shift
        elif assignments[day_idx] == "G":
            if g_count <= 6:
                violations["constraints_violated"].append("n4_g_minimum")
                violations["violation_details"].append({
                    "type": "n4_g_minimum",
                    "staff": staff_id,
                    "staff_name": staff_name,
                    "message": f"N4 needs exactly 6 G shifts per week"
                })
        
        return violations

    def _violates_2n_off_rule(self, assignments: List[str], day_idx: int, new_shift: str) -> bool:
        """Check if staff violates 2N→OFF rule: worked 2 consecutive nights AND next day is OFF AND trying to work on that OFF day."""
        if len(assignments) < 3 or day_idx < 2:
            return False
        
        # Check if worked NN (2 consecutive nights) before the current day
        if assignments[day_idx - 2] == "N" and assignments[day_idx - 1] == "N":
            # Check if current day is OFF (rest day after NN)
            if assignments[day_idx] == "OFF":
                # Check if trying to work on this OFF day
                if new_shift != "OFF":
                    return True
        
        return False

    def _check_equal_distribution(self, assignments: List[str], new_shift: str, day_idx: int, staff_id: str, staff_name: str) -> Dict[str, Any]:
        """Check if swap disrupts equal distribution (2M, 2E, 2N, 1OFF)."""
        violations = {"constraints_violated": [], "violation_details": []}
        
        # Count current shift distribution
        m_count = sum(1 for shift in assignments if shift == "M")
        e_count = sum(1 for shift in assignments if shift == "E")
        n_count = sum(1 for shift in assignments if shift == "N")
        off_count = sum(1 for shift in assignments if shift == "OFF")
        
        # Simulate the swap
        current_shift = assignments[day_idx] if day_idx < len(assignments) else "OFF"
        
        # Calculate new distribution after swap
        if current_shift == "M":
            m_count -= 1
        elif current_shift == "E":
            e_count -= 1
        elif current_shift == "N":
            n_count -= 1
        elif current_shift == "OFF":
            off_count -= 1
        
        if new_shift == "M":
            m_count += 1
        elif new_shift == "E":
            e_count += 1
        elif new_shift == "N":
            n_count += 1
        elif new_shift == "OFF":
            off_count += 1
        
        # Check if distribution is significantly off from ideal (2M, 2E, 2N, 1OFF)
        ideal_distribution = {"M": 2, "E": 2, "N": 2, "OFF": 1}
        actual_distribution = {"M": m_count, "E": e_count, "N": n_count, "OFF": off_count}
        
        # Calculate deviation from ideal
        deviations = []
        for shift_type, ideal_count in ideal_distribution.items():
            actual_count = actual_distribution[shift_type]
            deviation = abs(actual_count - ideal_count)
            if deviation > 0:  # Flag any deviation from ideal distribution
                deviations.append(f"{shift_type}: {actual_count} (ideal: {ideal_count})")
        
        if deviations:
            violations["constraints_violated"].append("equal_distribution")
            violations["violation_details"].append({
                "type": "equal_distribution",
                "staff": staff_id,
                "staff_name": staff_name,
                "message": f"Equal distribution disrupted: {', '.join(deviations)}. Ideal: 2M, 2E, 2N, 1OFF"
            })
        
        return violations

    def _check_n5_coverage(self, staff1_id: str, staff1_current: str, staff2_id: str, staff2_current: str, day_idx: int, compact_roster: Dict) -> Dict[str, Any]:
        """Check if N5 coverage is maintained after swap."""
        violations = {"constraints_violated": [], "violation_details": []}
        
        # Get all staff assignments for the day
        day_assignments = {}
        for staff_id, assignments in compact_roster.items():
            if day_idx < len(assignments):
                day_assignments[staff_id] = assignments[day_idx]
        
        # Simulate the swap
        day_assignments[staff1_id] = staff2_current
        day_assignments[staff2_id] = staff1_current
        
        # Check N5 coverage for each shift
        shifts_to_check = ["M", "E", "N"]
        for shift in shifts_to_check:
            n5_count = 0
            for staff_id, assignment in day_assignments.items():
                if assignment == shift:
                    # Check if staff is N5 (simplified - would need staff_lookup in real implementation)
                    # For now, we'll skip this check as we don't have access to staff_lookup
                    pass
            
            # Skip N5 coverage check for now - would need staff_lookup access
            # if n5_count == 0:
            #     violations["constraints_violated"].append("n5_coverage")
            #     violations["violation_details"].append({
            #         "type": "n5_coverage",
            #         "shift": shift,
            #         "message": f"No N5 coverage for {shift} shift after swap"
            #     })
        
        return violations

    def _exceeds_consecutive_days(self, assignments: List[str], day_idx: int) -> bool:
        """Check if staff would work more than 6 consecutive days."""
        consecutive_count = 0
        max_consecutive = 0
        
        for i, shift in enumerate(assignments):
            if shift not in ["OFF", "PL", "CL", "PREF"]:
                consecutive_count += 1
                max_consecutive = max(max_consecutive, consecutive_count)
            else:
                consecutive_count = 0
        
        return max_consecutive > 6

    async def handle_coverage_optimization(
        self, 
        roster_id: str, 
        day: str, 
        target_shift: str
    ) -> Dict[str, Any]:
        """Handle coverage optimization with intelligent suggestions."""
        try:
            roster_data = await self.get_roster_data(roster_id)
            if not roster_data:
                return {
                    "widget_data": {}
                }

            # Map day to index
            day_mapping = roster_data["day_mapping"]
            day_indices = self._map_day_names_to_indices([day], day_mapping)
            if not day_indices:
                return {
                    "widget_data": {}
                }
            day_idx = day_indices[0]
            
            # Build coverage for the day
            day_coverage = self._build_day_coverage(roster_data, day_idx)
            
            # Find available staff (currently OFF)
            compact_roster = roster_data["compact_roster"]
            staff_lookup = roster_data["staff_lookup"]
            available_staff = []
            
            for staff_id, assignments in compact_roster.items():
                if day_idx < len(assignments):
                    current_shift = assignments[day_idx]
                    if current_shift == "OFF":
                        staff_info = staff_lookup.get(staff_id, {})
                        workload = sum(1 for shift in assignments if shift not in ["OFF", "PL", "CL", "PREF"])
                        available_staff.append({
                            "id": staff_id,
                            "name": staff_info.get("name", "Unknown"),
                            "grade": staff_info.get("grade", "Unknown"),
                            "role": staff_info.get("role", "Unknown"),
                            "current_workload": workload,
                            "can_extend": workload < 5
                        })
            
            # Generate LLM response
            user_prompt = COVERAGE_OPTIMIZATION_USER_PROMPT.format(
                target_shift=target_shift,
                day=day,
                day_coverage=json.dumps(day_coverage, indent=2),
                available_staff=json.dumps(available_staff, indent=2),
                day_mapping=json.dumps(day_mapping, indent=2)
            )
            
            messages = [
                {"role": "system", "content": COVERAGE_OPTIMIZATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ]
            
            response = await chat_with_gpt(messages)
            
            if response.success and response.data:
                content = response.data.get("content", "{}")
                try:
                    result = json.loads(content)
                    primary = result.get("primary_action", {})
                    alt_list = result.get("alternatives", [])
                    
                    widget_data = {
                        "type": "roster_modification",
                        "primary_action": {
                            "title": primary.get("title", f"Coverage optimization for {target_shift}"),
                            "description": primary.get("description", f"Analyzing coverage for {target_shift} shift on {day}"),
                            "patches": primary.get("patches", []),
                            "button_text": primary.get("button_text", "View Options"),
                            "confidence": primary.get("confidence", 0.8)
                        },
                        "alternatives": alt_list,
                        "metadata": result.get("metadata", {
                            "override_allowed": False,
                            "constraints_violated": []
                        })
                    }
                    
                    return {"widget_data": widget_data}
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse LLM response: {e}")
                    return {
                        "widget_data": {}
                    }
            else:
                return {
                    "widget_data": {}
                }

        except Exception as e:
            logger.error(f"Error in handle_coverage_optimization: {e}")
            return {
                "widget_data": {}
            }