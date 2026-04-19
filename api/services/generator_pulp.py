# roster_optimizer_with_preprocessor.py

import logging
from typing import Dict, Any, List, Tuple, Set
from datetime import date, timedelta
import pulp

# -------------------------
# Logger
# -------------------------
logger = logging.getLogger("roster_optimizer")
if not logger.handlers:
    ch = logging.StreamHandler()
    fmt = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    ch.setFormatter(fmt)
    logger.addHandler(ch)
logger.setLevel(logging.INFO)

# -------------------------
# Types / constants
# -------------------------
Staff = Dict[str, Any]
AllowedMap = Dict[Tuple[str, int], Set[str]]
WEEKDAY_INDEX = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def parse_preferred_day(pref) -> int | None:
    if pref is None:
        return None
    if isinstance(pref, int):
        return pref if 0 <= pref <= 6 else None
    if isinstance(pref, str):
        key = pref.strip().lower()[:3]
        return WEEKDAY_INDEX.get(key)
    return None


# -------------------------
# Pre-Analysis: Night Allocation
# -------------------------
def pre_analyze_night_allocation(roster_input: Dict[str, Any]) -> Dict[str, int]:
    """
    Pre-analysis phase that determines which nurses get 2N vs 3N shifts.
    
    Strategy:
    1. Calculate total N shifts needed from coverage requirements
    2. Count eligible nurses (non-N4, considering leaves)
    3. Calculate shortage: needed - (eligible * 2)
    4. Select nurses for 3N based on seniority (N5 > N6 > N7)
    
    Returns:
        Dict mapping staff_id to number of nights (2 or 3)
    """
    logger.info("Pre-Analysis: Calculating night shift allocation")
    
    meta = roster_input.get("meta", {})
    total_days = int(meta.get("total_days", 7))
    coverage_map = roster_input.get("constraints", {}).get("coverage", {}).get("per_shift", {})
    
    # Calculate total N shifts needed
    n_per_day = coverage_map.get("N", {}).get("min", coverage_map.get("N", {}).get("total", 0))
    total_n_needed = n_per_day * total_days
    
    # Get staff and identify grades
    staff = roster_input.get("staff_details", [])
    non_n4_by_grade = {"N5": [], "N6": [], "N7": []}
    
    for s in staff:
        sid = str(s.get("id") or s.get("_id") or s.get("emp_id"))
        grade = s.get("grade")
        if grade in non_n4_by_grade:
            non_n4_by_grade[grade].append(sid)
    
    # Count leave days per nurse
    leave_days_count = {}
    for req in roster_input.get("leave_requests", []):
        sid = str(req.get("id") or req.get("emp_id"))
        leave_count = len(req.get("leaves", []))
        leave_days_count[sid] = leave_count
    
    # Build list of eligible nurses sorted by priority (N5 > N6 > N7)
    # Within same grade: fewer leaves first
    eligible_nurses = []
    for grade in ["N5", "N6", "N7"]:
        grade_nurses = non_n4_by_grade[grade]
        # Sort by leave days (ascending) - fewer leaves first
        grade_nurses_sorted = sorted(grade_nurses, key=lambda sid: leave_days_count.get(sid, 0))
        eligible_nurses.extend(grade_nurses_sorted)
    
    # Calculate baseline: everyone gets 2N
    baseline_n_assigned = len(eligible_nurses) * 2
    
    # Calculate shortage
    shortage = total_n_needed - baseline_n_assigned
    
    logger.info(f"Night allocation: total_needed={total_n_needed}, eligible={len(eligible_nurses)}, baseline={baseline_n_assigned}, shortage={shortage}")
    
    # Initialize allocation: everyone gets 2N by default
    night_allocation = {sid: 2 for sid in eligible_nurses}
    
    # If shortage > 0, allocate 3N to nurses based on priority
    if shortage > 0:
        nurses_for_3n = min(shortage, len(eligible_nurses))
        logger.info(f"Allocating 3N to {nurses_for_3n} nurses based on seniority")
        
        for i in range(nurses_for_3n):
            if i < len(eligible_nurses):
                sid = eligible_nurses[i]
                # Check if they have capacity (not too many leaves)
                leaves = leave_days_count.get(sid, 0)
                if total_days - leaves >= 3:  # Can work at least 3 nights
                    night_allocation[sid] = 3
                    logger.info(f"  {sid} -> 3N")
    
    logger.info(f"Night allocation complete: {sum(1 for n in night_allocation.values() if n == 3)} nurses with 3N, {sum(1 for n in night_allocation.values() if n == 2)} nurses with 2N")
    
    return night_allocation


# -------------------------
# Preprocessor
# -------------------------
def preprocessor(roster_input: Dict[str, Any]) -> Tuple[AllowedMap, Dict[str, int]]:
    """
    Prepares allowed shifts per staff/day according to the new strategy:

    - Hard lock leaves (LEAVE) by date (exact labels).
    - N4: G only Mon–Sat, Sun OFF (unless leave).
    - Non-N4:
        * Hard lock preferred offs as 'PREF'.
        * Create one 2N or 3N block followed by OFF (wrapping week).
        * Prioritize N5s to guarantee at least one N5 per night.
    - After fixing N/Off/Leaves:
        * Non-N4 remaining cells only allow {M, E, ME}.
        * N4 only allows {G} Mon–Sat (unless leave), and {OFF} on Sun.
    
    Returns:
        Tuple of (allowed_map, night_allocation_dict)
    """

    logger.info("Preprocessor: start (new strategy)")
    
    # Pre-analysis: Determine 2N vs 3N allocation
    night_allocation = pre_analyze_night_allocation(roster_input)
    
    meta = roster_input.get("meta", {})
    start_date = date.fromisoformat(meta.get("schedule_start_date"))
    total_days = int(meta.get("total_days", 7))

    shift_defs = roster_input.get("shift_definitions", {})
    # Ensure ME exists
    if "ME" not in shift_defs:
        mhrs = int(shift_defs.get("M", {}).get("hours", 6))
        ehrs = int(shift_defs.get("E", {}).get("hours", 6))
        shift_defs["ME"] = {"name": "Morning+Evening", "hours": mhrs + ehrs}
        roster_input["shift_definitions"] = shift_defs

    all_shifts = list(shift_defs.keys())
    has_G = "G" in all_shifts
    has_N = "N" in all_shifts

    # --- Leaves by (sid, iso_date) -> type
    leave_by_day: Dict[Tuple[str, str], str] = {}
    for req in roster_input.get("leave_requests", []):
        sid = str(req.get("id") or req.get("emp_id"))
        for lv in req.get("leaves", []):
            iso = str(lv.get("date"))
            typ = str(lv.get("type", "")).upper()
            if iso and typ in {"CL", "PL", "LWP", "LEAVE"}:
                leave_by_day[(sid, iso)] = "LEAVE"

    # --- Preferences: per (sid, day) -> shift (OFF included). OFF prefs used for night-block anchors.
    pref_by_day: Dict[str, Dict[int, str]] = {}
    off_pref_days: Dict[str, List[int]] = {}
    for p in roster_input.get("preferences", []):
        sid = str(p.get("id") or p.get("emp_id"))
        iso = p.get("date")
        sh = p.get("shift")
        if not sid or not iso or not sh:
            continue
        try:
            d_idx = (date.fromisoformat(str(iso)) - start_date).days
        except Exception:
            continue
        if d_idx < 0 or d_idx >= total_days:
            continue
        sh_norm = str(sh).upper()
        pref_by_day.setdefault(sid, {})[d_idx] = sh_norm
        if sh_norm == "OFF":
            off_pref_days.setdefault(sid, []).append(d_idx)

    # --- Normalize staff list
    staff: List[Dict[str, Any]] = []
    for s in roster_input.get("staff_details", []):
        sid = str(s.get("id") or s.get("_id") or s.get("emp_id"))
        staff.append({
            "id": sid,
            "grade": s.get("grade"),
            "name": s.get("name")
        })
    staff_ids = [s["id"] for s in staff]
    n4_ids = [s["id"] for s in staff if s.get("grade") == "N4"]
    n5_ids = [s["id"] for s in staff if s.get("grade") == "N5"]
    n6_ids = [s["id"] for s in staff if s.get("grade") == "N6"]
    n5_or_n6_ids = n5_ids + n6_ids
    non_n4_ids = [s["id"] for s in staff if s.get("grade") != "N4"]

    # --- Init allowed map with all shifts + OFF
    allowed: AllowedMap = {}
    for sid in staff_ids:
        for d in range(total_days):
            allowed[(sid, d)] = set(all_shifts) | {"OFF"}

    # --- Apply LEAVES
    for sid in staff_ids:
        for d in range(total_days):
            iso = (start_date + timedelta(days=d)).isoformat()
            if (sid, iso) in leave_by_day:
                typ = leave_by_day[(sid, iso)]
                allowed[(sid, d)] = {typ}

    # --- N4: G Mon–Sat, Sun OFF (unless leave)
    def is_sunday(d: int) -> bool:
        return (start_date + timedelta(days=d)).weekday() == 6

    for sid in n4_ids:
        for d in range(total_days):
            if len(allowed[(sid, d)]) == 1 and list(allowed[(sid, d)])[0] not in all_shifts:
                continue
            if is_sunday(d):
                allowed[(sid, d)] = {"OFF"}
            else:
                allowed[(sid, d)] = {"G"} if has_G else {"OFF"}

    # --- Apply preferences: lock to shift or PREF (for OFF), skip if leave
    # Also collect N preference days for special handling in block placement
    n_pref_days: Dict[str, List[int]] = {}
    for sid, day_map in pref_by_day.items():
        for d, pref_shift in day_map.items():
            tok = allowed.get((sid, d))
            if tok is None:
                continue
            if len(tok) == 1 and list(tok)[0] in {"LEAVE"}:
                continue  # leave already fixed
            if pref_shift == "OFF":
                allowed[(sid, d)] = {"PREF"}
            else:
                if pref_shift not in all_shifts:
                    continue
                allowed[(sid, d)] = {pref_shift}
                # Track N preferences for block placement
                if pref_shift == "N":
                    n_pref_days.setdefault(sid, []).append(d)

    # --- Helper functions
    def current_off_load(day: int) -> int:
        cnt = 0
        for s in non_n4_ids:
            tok = allowed[(s, day)]
            if len(tok) == 1 and list(tok)[0] in {"OFF", "PREF", "LEAVE"}:
                cnt += 1
        return cnt

    nights_by_day = [0] * total_days
    n5_or_n6_present_on_night = [False] * total_days

    if has_N:
        for sid in staff_ids:
            for d in range(total_days):
                if allowed[(sid, d)] == {"N"}:
                    nights_by_day[d] += 1
                    if sid in n5_or_n6_ids:
                        n5_or_n6_present_on_night[d] = True

    def place_block(sid: str, off_day: int, num_nights: int = 2) -> bool:
        """
        Place consecutive night shifts followed by OFF.
        For 2N: N-N-OFF
        For 3N: N-N-N-OFF
        """
        # Calculate night shift days based on num_nights
        night_days = []
        for i in range(num_nights, 0, -1):
            night_days.append((off_day - i) % total_days)
        
        # Check if all days are available (no conflicts with leaves or locked shifts)
        days_to_check = night_days + [off_day]
        for dd in days_to_check:
            tok = allowed[(sid, dd)]
            if len(tok) == 1:
                val = list(tok)[0]
                if val in {"LEAVE"}:
                    return False
                if val == "PREF" and dd != off_day:
                    return False
                # Allow N if it's one of the N days, block otherwise
                if val == "N" and dd in night_days:
                    continue  # N preference on an N day is OK
                if val not in {"OFF", "PREF"} and val in all_shifts:
                    return False
        
        # Place the block: N shifts on night days, OFF on off_day
        # CRITICAL: Always lock N shifts, even if they were already N preferences
        for night_day in night_days:
            # Lock to N (or OFF if N not available)
            allowed[(sid, night_day)] = {"N"} if has_N else {"OFF"}
            nights_by_day[night_day] += 1
            if sid in n5_or_n6_ids:
                n5_or_n6_present_on_night[night_day] = True
        
        # Lock OFF day (unless it's already PREF - don't overwrite preference)
        if allowed[(sid, off_day)] != {"PREF"}:
            allowed[(sid, off_day)] = {"OFF"}
        
        return True

    # Place blocks for N5 first, then N6 (use N prefs, then OFF prefs as anchors)
    # We iterate n5_ids then n6_ids to prioritize N5s getting their preferred blocks
    for sid in n5_ids + n6_ids:
        num_nights = night_allocation.get(sid, 2)
        placed = False
        # First try to build block around N preferences
        for n_day in n_pref_days.get(sid, []):
            # Try off_day = n_day + 1 (N on n_day-1, n_day) or off_day = n_day + 2 (N on n_day, n_day+1)
            # For 3N, also try off_day = n_day + 3
            potential_off_days = [(n_day + 1) % total_days, (n_day + 2) % total_days]
            if num_nights == 3:
                potential_off_days.append((n_day + 3) % total_days)
            for off_day in potential_off_days:
                if place_block(sid, off_day, num_nights):
                    placed = True
                    break
            if placed:
                break
        if placed:
            continue
        # Then try OFF preferences
        for off_day in off_pref_days.get(sid, []):
            if place_block(sid, off_day, num_nights):
                placed = True
                break
        if placed:
            continue
        # Build candidates sorted by priority, try each until one succeeds
        candidates = []
        for off_day in range(total_days):
            tok = allowed[(sid, off_day)]
            if len(tok) == 1 and list(tok)[0] in {"LEAVE"}:
                continue
            # Check night days based on num_nights
            night_days = [(off_day - i) % total_days for i in range(num_nights, 0, -1)]
            # We want to fill nights that lack senior coverage first
            need_score = sum(0 if n5_or_n6_present_on_night[d] else 1 for d in night_days)
            off_load = current_off_load(off_day)
            key = (-need_score, off_load)
            candidates.append((key, off_day))
        candidates.sort(key=lambda x: x[0])
        for key, off_day in candidates:
            if place_block(sid, off_day, num_nights):
                break

    # Place blocks for remaining non-N4 (non-N5/N6)
    for sid in [s for s in non_n4_ids if s not in n5_or_n6_ids]:
        num_nights = night_allocation.get(sid, 2)
        placed = False
        # First try to build block around N preferences
        for n_day in n_pref_days.get(sid, []):
            potential_off_days = [(n_day + 1) % total_days, (n_day + 2) % total_days]
            if num_nights == 3:
                potential_off_days.append((n_day + 3) % total_days)
            for off_day in potential_off_days:
                if place_block(sid, off_day, num_nights):
                    placed = True
                    break
            if placed:
                break
        if placed:
            continue
        # Then try OFF preferences
        for off_day in off_pref_days.get(sid, []):
            if place_block(sid, off_day, num_nights):
                placed = True
                break
        if placed:
            continue
        # Build candidates sorted by off_load, try each until one succeeds
        candidates = []
        for off_day in range(total_days):
            tok = allowed[(sid, off_day)]
            if len(tok) == 1 and list(tok)[0] in {"LEAVE"}:
                continue
            load = current_off_load(off_day)
            candidates.append((load, off_day))
        candidates.sort(key=lambda x: x[0])
        for load, off_day in candidates:
            if place_block(sid, off_day, num_nights):
                break

    # Restrict remaining to {M,E,ME} — skip any day already locked to a single value
    # CRITICAL: Do NOT allow N here - N shifts are pre-determined by preprocessor blocks
    # This prevents optimizer from adding N shifts anywhere and breaking consecutive patterns
    for sid in non_n4_ids:
        for d in range(total_days):
            tok = allowed[(sid, d)]
            if len(tok) == 1:
                continue  # already locked (leave, PREF, N, or a shift preference)
            # Only allow M, E, ME - N is already placed in blocks
            allowed[(sid, d)] = {"M", "E", "ME"} & set(all_shifts)

    # Ensure non-N4 never get G
    if has_G:
        for sid in non_n4_ids:
            for d in range(total_days):
                allowed[(sid, d)].discard("G")

    # Validation: Verify all nurses got their allocated N blocks
    logger.info("Preprocessor: Validating N block placement")
    for sid in non_n4_ids:
        expected_nights = night_allocation.get(sid, 2)
        actual_locked_nights = sum(1 for d in range(total_days) if allowed.get((sid, d)) == {"N"})
        if actual_locked_nights < expected_nights:
            logger.warning(f"WARNING: {sid} expected {expected_nights}N but only {actual_locked_nights}N locked in preprocessor")
    
    logger.info("Preprocessor: done")
    return allowed, night_allocation


# -------------------------
# Roster Optimizer
# -------------------------
class RosterOptimizer:
    def __init__(self, payload: Dict[str, Any]):
        logger.info("RosterOptimizer: init")
        self.data = payload
        self.total_days = int(self.data["meta"]["total_days"])
        self.shift_defs = self.data["shift_definitions"]
        self.coverage_map = self.data["constraints"]["coverage"]["per_shift"]
        self.enforce_exact = self.data["constraints"]["coverage"].get("enforce_exact", False)

        self.staff = self._normalize_staff(self.data["staff_details"])
        self.staff_ids = [s["id"] for s in self.staff]

        # Identify grades for constraints
        self.n5_ids = [s["id"] for s in self.staff if s.get("grade") == "N5"]
        self.n6_ids = [s["id"] for s in self.staff if s.get("grade") == "N6"]

        self.shifts = list(self.shift_defs.keys())
        self.shift_hours = {k: int(v["hours"]) for k, v in self.shift_defs.items()}

        allowed_result = preprocessor(self.data)
        self.allowed_shifts, self.night_allocation = allowed_result
        logger.info(f"Night allocation received: {len([n for n in self.night_allocation.values() if n == 3])} nurses with 3N")
        self.model = pulp.LpProblem("RosterHybrid", pulp.LpMinimize)

        # Decision vars
        self.x = {(sid, d, sh): pulp.LpVariable(f"x_{sid}_{d}_{sh}", cat=pulp.LpBinary)
                  for sid in self.staff_ids for d in range(self.total_days)
                  for sh in self.shifts if sh in self.allowed_shifts.get((sid, d), set())}
        self.off = {(sid, d): pulp.LpVariable(f"off_{sid}_{d}", cat=pulp.LpBinary)
                    for sid in self.staff_ids for d in range(self.total_days)}
        self.penalty_terms: List[pulp.LpAffineExpression] = []

    def _normalize_staff(self, raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen, staff = set(), []
        for s in raw:
            sid = s.get("id") or s.get("_id") or s.get("emp_id")
            if not sid:
                raise ValueError("Staff missing id")
            if sid in seen:
                raise ValueError(f"Duplicate staff id {sid}")
            seen.add(sid)
            staff.append({
                "id": sid,
                "grade": s.get("grade"),
                "accepts_me": bool(s.get("accepts_me", False)),
                "min_hours_per_period": s.get("min_hours_per_period", 48),
                "max_hours_per_period": s.get("max_hours_per_period"),
            })
        return staff

    def build_constraints(self):
        TD = self.total_days

        # One shift per day
        for sid in self.staff_ids:
            for d in range(TD):
                vars_sh = [self.x[(sid, d, sh)] for sh in self.shifts if (sid, d, sh) in self.x]
                self.model += (pulp.lpSum(vars_sh) + self.off[(sid, d)] == 1)

        # Force leave / OFF if required
        for (sid, d), shifts in self.allowed_shifts.items():
            if len(shifts) == 1 and list(shifts)[0] not in self.shifts:
                self.model += (self.off[(sid, d)] == 1)
            elif len(shifts) == 1:
                # Hard lock to the only allowed shift (e.g., user preference)
                only = list(shifts)[0]
                var = self.x.get((sid, d, only))
                if var is not None:
                    self.model += (var == 1)
                    self.model += (self.off[(sid, d)] == 0)

        # Force OFF=0 if OFF is not explicitly allowed in the preprocessor map
        # The preprocessor removes 'OFF' from the set for working days (remaining cells)
        # So we must forbid the solver from choosing OFF in those cases
        for sid in self.staff_ids:
            for d in range(TD):
                allowed = self.allowed_shifts.get((sid, d), set())
                # If "OFF" is not in allowed, force off variable to 0
                # Note: LEAVE and PREF cases are already handled above or locked
                if "OFF" not in allowed and "LEAVE" not in allowed and "PREF" not in allowed:
                    self.model += (self.off[(sid, d)] == 0)

        # Coverage constraints with soft upper and lower bounds
        # Prevent both under-coverage and over-coverage for M, E, N
        # G only has lower bound (can be flexible due to N4 availability)
        coverage_slack_weight = 100000.0  # High penalty for missing or exceeding coverage
        
        for d in range(TD):
            # Check all shifts for coverage (M, E, N, G)
            for sh in ["M", "E", "N", "G"]:
                req = self.coverage_map.get(sh, {}).get("min", self.coverage_map.get(sh, {}).get("total", 0))
                if req <= 0:
                    continue
                
                vars_sh = [self.x[(sid, d, sh)] for sid in self.staff_ids if (sid, d, sh) in self.x]
                
                # If checking M or E coverage, also include ME shifts
                if sh in ["M", "E"]:
                    vars_me = [self.x[(sid, d, "ME")] for sid in self.staff_ids if (sid, d, "ME") in self.x]
                    vars_sh.extend(vars_me)
                
                if not vars_sh:
                    continue
                
                total_assigned = pulp.lpSum(vars_sh)
                
                # For M, E, N: enforce both lower and upper bounds (soft)
                if sh in ["M", "E", "N"]:
                    # Lower bound: penalize under-coverage
                    slack_under = pulp.LpVariable(f"slack_under_{sh}_{d}", lowBound=0, cat=pulp.LpInteger)
                    self.model += (total_assigned + slack_under >= req)
                    self.penalty_terms.append(coverage_slack_weight * slack_under)
                    
                    # Upper bound: penalize over-coverage
                    slack_over = pulp.LpVariable(f"slack_over_{sh}_{d}", lowBound=0, cat=pulp.LpInteger)
                    self.model += (total_assigned - slack_over <= req)
                    self.penalty_terms.append(coverage_slack_weight * slack_over)
                else:
                    # For G: only lower bound (flexible due to N4 availability)
                    slack = pulp.LpVariable(f"slack_{sh}_{d}", lowBound=0, cat=pulp.LpInteger)
                    self.model += (total_assigned + slack >= req)
                    self.penalty_terms.append(coverage_slack_weight * slack)

            # 2. SENIOR COVERAGE (At least 1 N5 or N6 on Night)
            vars_senior_n = []
            for sid in self.n5_ids + self.n6_ids:
                if (sid, d, "N") in self.x:
                    vars_senior_n.append(self.x[(sid, d, "N")])
            
            if vars_senior_n:
                slack_senior = pulp.LpVariable(f"slack_senior_{d}", lowBound=0, cat=pulp.LpInteger)
                self.model += (pulp.lpSum(vars_senior_n) + slack_senior >= 1)
                self.penalty_terms.append(coverage_slack_weight * slack_senior)

        # SAFETY CONSTRAINTS
        # (Max 2 consecutive N shifts removed - handled by preprocessor blocks which allow 3N)

        # 2. No N followed by M/E/G (Rest after Night)
        # If N on day d, then day d+1 cannot be M, E, G, ME (must be OFF or N)
        for sid in self.staff_ids:
            for d in range(TD - 1):
                if (sid, d, "N") in self.x:
                    # Check next day shifts
                    next_day_working = []
                    for bad_sh in ["M", "E", "G", "ME"]:
                        if (sid, d + 1, bad_sh) in self.x:
                            next_day_working.append(self.x[(sid, d + 1, bad_sh)])
                    
                    if next_day_working:
                        # If N today, sum(bad shifts tomorrow) must be 0
                        # Implementation: x[d, N] + x[d+1, bad] <= 1
                        # We sum all bad shifts into one term
                        self.model += (self.x[(sid, d, "N")] + pulp.lpSum(next_day_working) <= 1)

        # MAX 1 OFF DAY CONSTRAINT (excluding LEAVE days and PREF days)
        # Company policy: each nurse gets exactly 1 OFF day per week (excluding leaves and preferences)
        logger.info("Applying max 1 OFF constraint (company policy)")
        n4_ids_set = {s["id"] for s in self.staff if s.get("grade") == "N4"}
        for sid in self.staff_ids:
            if sid in n4_ids_set:
                continue  # N4 has different pattern (Sunday OFF)
            
            off_vars = []
            for d in range(TD):
                # Check if this day is a LEAVE or PREF (both should be excluded from OFF count)
                allowed = self.allowed_shifts.get((sid, d), set())
                if len(allowed) == 1:
                    val = list(allowed)[0]
                    if val in {"LEAVE", "PREF"}:
                        continue  # Skip leave days and preference days from OFF count
                off_vars.append(self.off[(sid, d)])
            
            if off_vars:
                # Hard constraint: at most 1 OFF day per week (excluding leaves and preferences)
                self.model += (pulp.lpSum(off_vars) <= 1, f"max_one_off_{sid}")

        # EQUAL DISTRIBUTION OF ALL SHIFT TYPES
        # Apply equal distribution for M, E, N shifts to prevent overloading specific nurses
        # Key: Distribute EXTRA shifts evenly (beyond what's already locked by preprocessor)
        n4_ids_set = {s["id"] for s in self.staff if s.get("grade") == "N4"}
        shift_dist_weight = 5000.0  # Strong penalty for uneven distribution (increased from 500)
        
        # Process each shift type that needs equal distribution
        for shift_type in ["M", "E", "N"]:
            # Skip if shift doesn't exist
            if shift_type not in self.shifts:
                continue
            
            # Count shifts already locked by preprocessor for this shift type
            shifts_locked_by_preprocessor = {}
            eligible_nurses = []
            
            for sid in self.staff_ids:
                # N4 never works nights
                if shift_type == "N" and sid in n4_ids_set:
                    continue
                
                locked_count = 0
                available_for_shift = 0
                
                for d in range(TD):
                    allowed = self.allowed_shifts.get((sid, d), set())
                    
                    # Check if this shift type is locked or available
                    is_locked = False
                    is_available = False
                    
                    if shift_type in ["M", "E"]:
                        # For M and E, also consider ME shifts
                        if allowed == {shift_type} or allowed == {"ME"}:
                            is_locked = True
                        elif shift_type in allowed or "ME" in allowed:
                            is_available = True
                    else:
                        # For N and other shifts, only check the shift itself
                        if allowed == {shift_type}:
                            is_locked = True
                        elif shift_type in allowed:
                            is_available = True
                    
                    if is_locked:
                        locked_count += 1
                    elif is_available and len(allowed) > 1:
                        available_for_shift += 1
                
                shifts_locked_by_preprocessor[sid] = locked_count
                
                # Eligible if they can work this shift (either locked or available)
                if locked_count > 0 or available_for_shift > 0:
                    eligible_nurses.append(sid)
            
            # Calculate total shifts of this type needed from coverage requirements
            total_shifts_needed = 0
            for d in range(TD):
                req = self.coverage_map.get(shift_type, {}).get("min", self.coverage_map.get(shift_type, {}).get("total", 0))
                if req > 0:
                    total_shifts_needed += req
            
            # Skip if no requirement for this shift
            if total_shifts_needed == 0 or not eligible_nurses:
                continue
            
            # Calculate total shifts already locked by preprocessor
            total_locked_shifts = sum(shifts_locked_by_preprocessor.values())
            
            # Calculate EXTRA shifts that need to be distributed (beyond what's locked)
            extra_shifts_needed = max(0, total_shifts_needed - total_locked_shifts)
            
            logger.info(f"{shift_type} distribution: total_needed={total_shifts_needed}, locked={total_locked_shifts}, extra={extra_shifts_needed}, eligible={len(eligible_nurses)}")
            
            # Only apply distribution constraint if there are extra shifts to distribute
            if extra_shifts_needed > 0:
                # Calculate base extra shifts per nurse and remainder
                base_extra = extra_shifts_needed // len(eligible_nurses)
                remainder = extra_shifts_needed % len(eligible_nurses)
                
                logger.info(f"{shift_type} distribution: base_extra={base_extra}, remainder={remainder}")
                
                for idx, sid in enumerate(eligible_nurses):
                    # Get all shift variables of this type for this nurse
                    vars_shift = [self.x[(sid, d, shift_type)] for d in range(TD) if (sid, d, shift_type) in self.x]
                    if not vars_shift:
                        continue
                    
                    # For M and E, also count ME shifts (ME counts for both M and E)
                    if shift_type in ["M", "E"] and "ME" in self.shifts:
                        vars_me = [self.x[(sid, d, "ME")] for d in range(TD) if (sid, d, "ME") in self.x]
                        vars_shift = vars_shift + vars_me
                    
                    # Total shifts assigned (includes both locked and extra)
                    total_shifts_assigned = pulp.lpSum(vars_shift)
                    locked_count = shifts_locked_by_preprocessor.get(sid, 0)
                    
                    # Create variable for extra shifts assigned (beyond locked)
                    extra_shifts_var = pulp.LpVariable(f"{shift_type}_extra_{sid}", lowBound=0, cat=pulp.LpInteger)
                    # Constraint: extra_shifts = total_shifts - locked_shifts
                    self.model += (extra_shifts_var == total_shifts_assigned - locked_count)
                    
                    # Target: base_extra or base_extra+1 (for first 'remainder' nurses)
                    # Distribute the +1 to first 'remainder' nurses to spread evenly
                    target_extra = base_extra + (1 if idx < remainder else 0)
                    
                    # Slack variables for deviation from target
                    slack_under = pulp.LpVariable(f"{shift_type}_extra_under_{sid}", lowBound=0, cat=pulp.LpInteger)
                    slack_over = pulp.LpVariable(f"{shift_type}_extra_over_{sid}", lowBound=0, cat=pulp.LpInteger)
                    
                    # Constraint: extra_shifts should equal target_extra (with slacks for softness)
                    self.model += (extra_shifts_var + slack_under - slack_over == target_extra)
                    
                    # Penalize deviations heavily (especially over-assignment to prevent concentration)
                    self.penalty_terms.append(shift_dist_weight * slack_under)
                    self.penalty_terms.append(shift_dist_weight * 2.0 * slack_over)  # Penalize over-assignment more

        # SMART ME PENALTY: Balance hours between heavy N workers and light workers
        # Strategy: ME shifts are essential (math requires ~30 ME shifts with 1 OFF constraint)
        # But give ME to 2N nurses (lighter load) and avoid for 3N nurses (heavy load)
        logger.info("Applying smart ME penalty for hours balancing")
        me_penalty_2n = 1.0         # Low penalty for 2N nurses (allow ME to balance workload)
        me_penalty_3n = 50000.0     # Very high penalty for 3N nurses (avoid ME - already heavy)
        n6_night_penalty = 5.0      # Preference to use N5 over N6

        for (sid, d, sh), var in self.x.items():
            if sh == "ME":
                # Use night_allocation dict to determine if nurse has 3N allocation
                # This is more reliable than counting locked N shifts
                num_nights = self.night_allocation.get(sid, 2)
                
                # Very high penalty for 3N nurses (they already have heavy night load)
                # Low penalty for 2N nurses (ME helps them reach balanced hours)
                penalty = me_penalty_3n if num_nights >= 3 else me_penalty_2n
                self.penalty_terms.append(penalty * var)
            
            # Penalize N6 on Night to prioritize N5
            if sh == "N" and sid in self.n6_ids:
                self.penalty_terms.append(n6_night_penalty * var)

    def solve(self):
        self.build_constraints()
        self.model += pulp.lpSum(self.penalty_terms)
        solver = pulp.PULP_CBC_CMD(msg=1, timeLimit=120, threads=4)
        self.model.solve(solver)
        status = pulp.LpStatus[self.model.status]
        logger.info("Solver status: %s", status)

        roster = {sid: {} for sid in self.staff_ids}
        for sid in self.staff_ids:
            for d in range(self.total_days):
                forced = self.allowed_shifts.get((sid, d), set())
                if len(forced) == 1 and list(forced)[0] not in self.shifts:
                    roster[sid][d] = [list(forced)[0]]
                    continue
                if round(float(pulp.value(self.off[(sid, d)]))) == 1:
                    roster[sid][d] = ["OFF"]
                    continue
                assigned_shift = next((sh for sh in self.shifts
                                       if (sid, d, sh) in self.x and round(float(pulp.value(self.x[(sid, d, sh)]))) == 1),
                                      "OFF")
                roster[sid][d] = [assigned_shift]
        return roster