MODIFICATION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "handle_absence_management",
            "description": "Handle staff absence scenarios - assign OFF/SL status and find replacements. Examples: 'John is sick today', 'Sarah is off tomorrow', 'Mike is unavailable this week', 'Mark Lisa as sick leave'",
            "parameters": {
                "type": "object",
                "properties": {
                    "staff_name": {
                        "type": "string",
                        "description": "Name of absent staff member (e.g., 'John', 'Sarah', 'Mike'). Use full name if multiple staff have same name."
                    },
                    "days": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["today", "tomorrow", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
                        },
                        "description": "Array of days for absence. Use ['today'] for single day, ['monday', 'tuesday'] for multiple days, etc."
                    },
                    "absence_type": {
                        "type": "string",
                        "enum": ["sick_leave", "personal_leave", "emergency"],
                        "description": "Type of absence - sick_leave for illness (assigns SL), personal_leave for planned time off (assigns OFF), emergency for urgent situations (assigns OFF, may override constraints)"
                    }
                },
                "required": ["staff_name", "days", "absence_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "handle_shift_assignment",
            "description": "Handle direct shift changes and assignments. Examples: 'Move John to morning shift', 'Assign Sarah to night shift tomorrow', 'Change Mike's shift from evening to morning', 'Put Lisa on General shift'",
            "parameters": {
                "type": "object",
                "properties": {
                    "staff_name": {
                        "type": "string", 
                        "description": "Name of staff member (e.g., 'John', 'Sarah', 'Mike')"
                    },
                    "day": {
                        "type": "string",
                        "enum": ["today", "tomorrow", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
                        "description": "Day for assignment. Use 'today' for current day, 'tomorrow' for next day, or specific day names."
                    },
                    "new_shift": {
                        "type": "string",
                        "enum": ["M", "E", "N", "G", "OFF", "SL"],
                        "description": "New shift assignment - M=Morning, E=Evening, N=Night, G=General, OFF=Day off, SL=Sick leave"
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for shift change (optional)"
                    }
                },
                "required": ["staff_name", "day", "new_shift"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "handle_staff_swap",
            "description": "Handle swapping shifts between staff members. Examples: 'Swap John and Sarah's shifts', 'Can Mike and Lisa switch their shifts?', 'I want to swap these two people'",
            "parameters": {
                "type": "object",
                "properties": {
                    "staff1_name": {
                        "type": "string",
                        "description": "Name of first staff member (e.g., 'John', 'Sarah', 'Mike')"
                    },
                    "staff2_name": {
                        "type": "string",
                        "description": "Name of second staff member (e.g., 'Lisa', 'Tom', 'Sarah')"
                    },
                    "day": {
                        "type": "string",
                        "enum": ["today", "tomorrow", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
                        "description": "Day for swap. Use 'today' for current day, 'tomorrow' for next day, or specific day names."
                    }
                },
                "required": ["staff1_name", "staff2_name", "day"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "handle_coverage_optimization",
            "description": "Handle coverage gaps and understaffing by making assignments. Examples: 'We're short on night shift coverage', 'Fill the coverage gaps', 'We need more staff on evening shift'",
            "parameters": {
                "type": "object",
                "properties": {
                    "day": {
                        "type": "string",
                        "enum": ["today", "tomorrow", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
                        "description": "Day to optimize. Use 'today' for current day, 'tomorrow' for next day, or specific day names."
                    },
                    "target_shift": {
                        "type": "string",
                        "enum": ["M", "E", "N", "G"],
                        "description": "Shift that needs coverage - M=Morning, E=Evening, N=Night, G=General"
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "description": "Priority of coverage need (default: medium)"
                    }
                },
                "required": ["day", "target_shift"],
            },
        },
    },
]


def get_tool_name(tool_call):
    """Extract tool name from tool call"""
    return tool_call.get("function", {}).get("name")


def get_tool_arguments(tool_call):
    """Extract tool arguments from tool call"""
    import json
    try:
        return json.loads(tool_call.get("function", {}).get("arguments", "{}"))
    except json.JSONDecodeError:
        return {}