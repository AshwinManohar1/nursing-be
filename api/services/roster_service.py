from typing import Dict, List
from api.db import db_manager
from api.models.roster import Roster, RosterCreate, RosterStatus
from api.models.roster_details import RosterDetails, RosterDetailsCreate
from api.models.ward import Ward
from api.services.generator_pulp import RosterOptimizer
from api.services.ward_service import WardService
from api.types.responses import ApiResponse
from api.utils.logger import get_logger
from datetime import date, datetime, timedelta
from bson import ObjectId
from typing import List, Dict
from api.services.ward_transfer_service import get_transfers_for_ward, get_transfers_for_wards_batch
import random

logger = get_logger("roster_service")


async def generate_roster(
    roster_input: dict, method: str = "heuristic", seed: int | None = None
) -> ApiResponse:
    try:
        logger.info(f"Starting roster generation with method: {method}, seed: {seed}")
        if seed:
            random.seed(seed)

        start = roster_input.get("meta").get("schedule_start_date")
        end = roster_input.get("meta").get("schedule_end_date")

        query = {
            "period_start": start,
            "period_end": end,
            "ward_id": ObjectId(roster_input.get("ward_id")) if roster_input.get("ward_id") else None,
            "status": {"$ne": RosterStatus.DELETED.value}
        }

        existing_roster = await Roster.find_one(query)

        if existing_roster:
            return ApiResponse.fail("Roster already present for selected range")

        # Step 1: Create the Roster document first
        roster_data = RosterCreate(
            ward_id=roster_input.get("ward_id"),
            created_by=roster_input.get("created_by"),
            period_start=start,
            period_end=end,
            name=roster_input.get(
                "roster_name", f"Roster {datetime.utcnow().strftime('%Y-%m-%d')}"
            ),
            status="accepted",  # Initial status is draft , need to change this once RBAC comes.
            comments=roster_input.get("comments", ""),
        )

        # Convert string IDs to ObjectId for the Roster document
        roster_dict = roster_data.dict()
        roster_dict["ward_id"] = (
            ObjectId(roster_dict["ward_id"]) if roster_dict["ward_id"] else None
        )
        roster_dict["created_by"] = (
            ObjectId(roster_dict["created_by"]) if roster_dict["created_by"] else None
        )

        roster = Roster(**roster_dict)
        await roster.insert()

        print("roster creation started")
        # Step 2: Generate the actual roster using the optimizer
        optimizer = RosterOptimizer(roster_input)
        generated_roster = optimizer.solve()

        # Step 3: Convert internal staff ids back to emp_id map for persistence
        staff_lookup = {
            staff["id"]: staff["emp_id"]
            for staff in roster_input.get("staff_details", [])
            if staff.get("emp_id")
        }
        roster_with_emp_ids = {}
        for internal_id, schedule in generated_roster.items():
            emp_id = staff_lookup.get(internal_id, internal_id)
            # Convert emp_id to string for MongoDB compatibility
            roster_with_emp_ids[str(emp_id)] = {str(k): v for k, v in schedule.items()}

        # Step 4: Create RosterDetails document
        roster_details_data = RosterDetailsCreate(
            roster_id=ObjectId(roster.id),
            roster_input=roster_input,
            roster=roster_with_emp_ids,
        )

        roster_details = RosterDetails(**roster_details_data.dict())
        await roster_details.insert()

        return ApiResponse.ok(
            "Roster generated and saved successfully",
            {
                "roster_id": str(roster.id),
                "roster_details_id": str(roster_details.id),
                "status": "draft",
                "meta": roster_input.get("meta", {}),
                "roster": roster_with_emp_ids,
            },
        )

    except Exception as e:
        logger.error(f"Roster generation failed: {e}")
        return ApiResponse.fail(f"Roster generation failed: {e}")


async def get_roster(roster_id: str) -> ApiResponse:
    try:
        roster = await Roster.get(ObjectId(roster_id))
        if not roster:
            return ApiResponse.fail("Roster not found")

        if roster.status == RosterStatus.DELETED:
            return ApiResponse.fail("Roster not found")

        # Get the roster details as well
        roster_details = await RosterDetails.find_one(
            {"roster_id": ObjectId(roster_id)}
        )

        roster_data = roster.dict()
        roster_data["id"] = str(roster.id)
        roster_data["ward_id"] = str(roster.ward_id)
        roster_data["created_by"] = str(roster.created_by)
        if roster.approved_by:
            roster_data["approved_by"] = str(roster.approved_by)

        if roster_details:
            roster_data["roster_details"] = {
                "id": str(roster_details.id),
                "roster_input": roster_details.roster_input,
                "roster": roster_details.roster,
            }
            # Always fetch and include transfers based on ward_id
            try:
                ward_id = roster_details.roster_input.get("ward_id")
                if ward_id:
                    transfers = await get_transfers_for_ward(ward_id, roster.period_start)
                    roster_data["roster_details"]["transfers"] = transfers
                    roster_data["roster_details"]["has_transfers"] = len(transfers) > 0
                else:
                    roster_data["roster_details"]["transfers"] = []
                    roster_data["roster_details"]["has_transfers"] = False
            except Exception as e:
                logger.error(f"Error fetching transfers for roster {roster_id}: {e}", exc_info=True)
                roster_data["roster_details"]["transfers"] = []
                roster_data["roster_details"]["has_transfers"] = False
        else:
            # Even if no roster_details, transfers array will be empty
            roster_data["roster_details"] = {
                "transfers": [],
                "has_transfers": False
            }

        return ApiResponse.ok("Roster retrieved successfully", roster_data)
    except Exception as e:
        return ApiResponse.fail(f"Failed to fetch roster: {e}")


async def list_rosters() -> ApiResponse:
    try:
        rosters = await Roster.find({"status": {"$ne": RosterStatus.DELETED.value}}).to_list()
        roster_list = []
        
        # Collect all roster_details and build ward_id -> list of roster periods mapping
        roster_details_list = []
        ward_rosters_map = {}  # Maps ward_id to list of (roster, period_start, period_end) tuples
        
        for roster in rosters:
            roster_details = await RosterDetails.find_one({"roster_id": roster.id})
            if roster_details is not None:
                roster_details_list.append((roster, roster_details))
                ward_id = roster_details.roster_input.get("ward_id")
                if ward_id:
                    ward_id_str = str(ward_id)
                    if ward_id_str not in ward_rosters_map:
                        ward_rosters_map[ward_id_str] = []
                    ward_rosters_map[ward_id_str].append({
                        "roster": roster,
                        "period_start": roster.period_start,
                        "period_end": roster.period_end
                    })
        
        # Batch fetch all transfers for all wards at once
        ward_ids = list(ward_rosters_map.keys())
        transfers_by_roster = {}
        if ward_ids:
            transfers_by_roster = await get_transfers_for_wards_batch(ward_ids, ward_rosters_map)
        
        # Build roster list with transfers
        for roster, roster_details in roster_details_list:
            # Convert to dict and convert all ObjectIds to strings
            roster_dict = roster_details.model_dump(mode='python')
            roster_dict = convert_objectid_to_str(roster_dict)
            # Ensure id is a string
            if '_id' in roster_dict:
                roster_dict['id'] = str(roster_dict.pop('_id'))
            else:
                roster_dict['id'] = str(roster_details.id)
            
            # Add transfers from batch result - use roster_id to get transfers for this specific roster
            roster_id = str(roster.id)
            transfers = transfers_by_roster.get(roster_id, [])
            roster_dict["transfers"] = transfers
            roster_dict["has_transfers"] = len(transfers) > 0

            # Order staff_details by grade priority (n4 -> n8 first)
            staff_details = (
                roster_dict.get("roster_input", {}).get("staff_details", [])
                if isinstance(roster_dict.get("roster_input"), dict)
                else []
            )
            if isinstance(staff_details, list):
                ordered_staff = sorted(
                    enumerate(staff_details),
                    key=lambda pair: (_grade_priority(pair[1].get("grade")), pair[0]),
                )
                ordered_staff = [item for _, item in ordered_staff]
                roster_dict.setdefault("roster_input", {})["staff_details"] = ordered_staff

                # Also reorder roster map to align with grade priority using emp_id lookup
                emp_order = {}
                emp_grade = {}
                for idx, staff in enumerate(ordered_staff):
                    emp_id = staff.get("emp_id")
                    if emp_id is not None:
                        emp_str = str(emp_id)
                        emp_order[emp_str] = idx
                        emp_grade[emp_str] = staff.get("grade")

                if isinstance(roster_dict.get("roster"), dict):
                    roster_items = list(roster_dict["roster"].items())
                    roster_items.sort(
                        key=lambda kv: (
                            _grade_priority(emp_grade.get(kv[0])),
                            emp_order.get(kv[0], 9999),
                        )
                    )
                    roster_dict["roster"] = {k: v for k, v in roster_items}
            
            roster_list.append(roster_dict)

        return ApiResponse.ok("Rosters list fetched", roster_list)
    except Exception as e:
        return ApiResponse.fail(f"Failed to list rosters: {e}")


async def update_roster(roster_id: str, patches: list) -> ApiResponse:
    try:
        if not patches:
            return ApiResponse.fail("No patches provided")

        if not roster_id:
            return ApiResponse.fail("No roster id provided")

        # Get the roster details to update the actual roster data
        roster_details = await RosterDetails.find_one(
            {"roster_id": ObjectId(roster_id)}
        )
        if not roster_details:
            return ApiResponse.fail("Roster details not found")

        updates = []
        for p in patches:
            updates.append(patch_to_mongo_update(p))

        # Apply patches to roster details
        for u in updates:
            result = await RosterDetails.find_one(
                {"roster_id": ObjectId(roster_id)}
            ).update(u)
            if not result:
                return ApiResponse.fail("Failed to update roster details")

        # Update the roster's updated_at timestamp
        roster = await Roster.get(ObjectId(roster_id))
        if roster:
            roster.update_timestamp()
            await roster.save()

        return ApiResponse.ok("Roster updated successfully", {"id": roster_id})

    except Exception as e:
        return ApiResponse.fail(f"Failed to update roster: {e}")


async def delete_roster(roster_id: str) -> ApiResponse:
    try:
        # Delete roster details first
        roster = await Roster.get(ObjectId(roster_id))
        if not roster:
            return ApiResponse.fail("Roster not found")

        if roster.status == RosterStatus.DELETED:
            return ApiResponse.fail("Roster already deleted")

        # Delete the roster
        roster.status = RosterStatus.DELETED
        roster.update_timestamp()
        await roster.save()
        
        return ApiResponse.ok("Roster deleted successfully", {"id": roster_id})
    except Exception as e:
        return ApiResponse.fail(f"Failed to delete roster: {e}")


def convert_objectid_to_str(doc):
    """Convert ObjectId fields to strings for JSON serialization"""
    if doc is None:
        return None
    if isinstance(doc, ObjectId):
        return str(doc)
    elif isinstance(doc, (date, datetime)):
        return doc.isoformat()
    elif isinstance(doc, dict):
        return {
            k: convert_objectid_to_str(v)
            for k, v in doc.items()
        }
    elif isinstance(doc, list):
        return [convert_objectid_to_str(item) for item in doc]
    return doc


def _grade_priority(grade: str) -> int:
    """Return a sortable priority for nurse grades, n4 highest."""
    if not grade:
        return 999
    return {"n4": 0, "n5": 1, "n6": 2, "n7": 3, "n8": 4}.get(grade.lower(), 999)


def patch_to_mongo_update(patch: dict):
    op = patch["op"]
    path = patch["path"].lstrip("/")
    mongo_key = path.replace("/", ".")

    if op == "replace":
        # For replace, ensure the value is always an array
        value = patch["value"]
        if not isinstance(value, list):
            value = [value]
        return {"$set": {mongo_key: value}}
    elif op == "add":
        # For add, we'll use $addToSet to add to array
        return {"$addToSet": {mongo_key: patch["value"]}}
    elif op == "remove":
        return {"$unset": {mongo_key: ""}}
    else:
        raise ValueError(f"Unsupported op: {op}")


async def update_constraints(roster_id: str, constraints: dict) -> ApiResponse:
    """
    Save or update global constraints for a roster
    """
    try:
        # Step 1: Check if the roster exists
        roster = await Roster.get(ObjectId(roster_id))
        if not roster:
            return ApiResponse.fail("Roster not found")

        # Step 2: Update constraints in roster details
        roster_details = await RosterDetails.find_one(
            {"roster_id": ObjectId(roster_id)}
        )
        if not roster_details:
            return ApiResponse.fail("Roster details not found")

        # Update constraints in roster details
        roster_details.roster_input["constraints"] = constraints
        roster_details.update_timestamp()
        await roster_details.save()

        return ApiResponse.ok(
            "Constraints updated successfully",
            {"id": roster_id, "constraints": constraints},
        )

    except Exception as e:
        return ApiResponse.fail(f"Failed to update constraints: {e}")


async def get_constraints(roster_id: str) -> ApiResponse:
    """
    Retrieve stored constraints for a given roster
    """
    try:
        roster_details = await RosterDetails.find_one(
            {"roster_id": ObjectId(roster_id)}
        )
        if not roster_details or "constraints" not in roster_details.roster_input:
            return ApiResponse.fail("No constraints found for this roster")
        return ApiResponse.ok(
            "Constraints retrieved successfully",
            roster_details.roster_input["constraints"],
        )
    except Exception as e:
        return ApiResponse.fail(f"Failed to fetch constraints: {e}")


async def get_active_rosters_by_date(hospital_id: str, date: date) -> List[Dict]:
    """Get active rosters for a specific date"""
    # Get wards for hospital
    ward_result = await WardService.get_wards_by_hospital(hospital_id)
    wards = ward_result["data"] if ward_result["success"] else []
    ward_ids = [ObjectId(ward.id) for ward in wards]

    # Get rosters for those wards that cover the date
    query = {
        "ward_id": {"$in": ward_ids},
        "period_start": {"$lte": date},
        "period_end": {"$gte": date},
        "status": {"$in": [RosterStatus.ACCEPTED.value, RosterStatus.PUBLISHED.value]},
    }
    
    rosters = await Roster.find(query).to_list()
    return convert_objectid_to_str(rosters)

async def get_all_rosters_by_date(hospital_id: str, date: date) -> List[Dict]:
    """Get ALL rosters for a specific date (regardless of status)"""
    # Get wards for hospital
    ward_result = await WardService.get_wards_by_hospital(hospital_id)
    
    wards = ward_result["data"] if ward_result["success"] else []
    ward_ids = [ObjectId(ward.id) for ward in wards]
    # Get ALL rosters for those wards that cover the date (regardless of status)
    query = {
        "ward_id": {"$in": ward_ids}, # to associate with hospital.
        "period_start": {"$lte": date},
        "period_end": {"$gte": date},
        "status": {"$ne": RosterStatus.DELETED.value}
    }
    
    rosters = await Roster.find(query).to_list()
    return convert_objectid_to_str(rosters)


async def get_nurse_count_by_shift(
    roster_id: str, date: date, shift: str = None
) -> Dict:
    """Get nurse count per shift from roster details, excluding TRANSFER_OUT"""
    roster_details = await RosterDetails.find_one({"roster_id": ObjectId(roster_id)})
    if not roster_details:
        return {}

    roster_data = roster_details.roster
    
    # Get the roster period to calculate day index
    roster = await Roster.get(ObjectId(roster_id))
    if not roster:
        return {}
    
    # Calculate day index (0-based) from roster start date
    if date < roster.period_start or date > roster.period_end:
        return {}
    
    day_index = str((date - roster.period_start).days)
    
    # Exclude these codes from counting
    excluded_codes = {"TRANSFER_OUT", "OFF", "PREF", "PL", "CL"}

    shift_counts = {"M": 0, "E": 0, "N": 0, "G": 0}

    for staff_id, schedule in roster_data.items():
        if day_index in schedule:
            day_schedule = schedule[day_index]  # This is a list like ['G'] or ['M', 'E']
            if not isinstance(day_schedule, list):
                day_schedule = [day_schedule] if day_schedule else []
            
            for shift_code in day_schedule:
                # Skip excluded codes (TRANSFER_OUT, OFF, etc.)
                if shift_code in excluded_codes:
                    continue
                
                # Handle compound shifts like "ME" - count both M and E
                if shift_code == "ME":
                    shift_counts["M"] += 1
                    shift_counts["E"] += 1
                elif shift_code in shift_counts:
                    shift_counts[shift_code] += 1

    if shift:
        return {shift: shift_counts.get(shift, 0)}

    return shift_counts


async def get_next_week_preferences(previous_roster_id: str) -> list:
    try:

        resp = await get_roster(previous_roster_id)
        print(resp, "resp")
        if not resp.success:
            return ApiResponse.fail(resp.message or "Failed to fetch previous roster")


        roster_data = resp.data or {}
        details = roster_data.get("roster_details", {})
        roster_map = details.get("roster", {}) or {}
        roster_input = details.get("roster_input", {}) or {}
        meta = roster_input.get("meta", {}) or {}

        total_days = int(meta.get("total_days", 0))
        period_end = roster_data.get("period_end")
        if not period_end or total_days < 2:
            return ApiResponse.ok("No preferences (insufficient data)", [])

        if isinstance(period_end, str):
            period_end_dt = datetime.fromisoformat(period_end).date()
        else:
            period_end_dt = period_end
        next_day_str = (period_end_dt + timedelta(days=1)).isoformat()

        d_prev = str(total_days - 2)
        d_last = str(total_days - 1)


        def normalize_shift(val) -> str:
            if isinstance(val, list):
                shift = val[0] if val else "OFF"
            else:
                shift = val
            if shift in ["PREF", "PL", "CL", None, ""]:
                return "OFF"
            return shift

        staff_index = {}
        for s in roster_input.get("staff_details", []):
            emp = s.get("emp_id")
            sid = s.get("id")
            if emp and sid:
                staff_index[str(emp)] = str(sid)

        out = []
        for emp_id, schedule in roster_map.items():
            if not isinstance(schedule, dict):
                continue
            if d_prev not in schedule or d_last not in schedule:
                continue
            s1 = normalize_shift(schedule.get(d_prev, "OFF"))
            s2 = normalize_shift(schedule.get(d_last, "OFF"))
            if s1 == "N" and s2 == "N":
                staff_mongo_id = staff_index.get(str(emp_id))
                if not staff_mongo_id:
                    continue  # skip if we can't resolve to Mongo ID
                out.append({
                    "id": staff_mongo_id,
                    "preferred_date_offs": [next_day_str],
                })

        return ApiResponse.ok("Preferences computed", out)


    except Exception as e:
        return {
            "success": False,
            "message": str(e),
            "data": {}
        }
