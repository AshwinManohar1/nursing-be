from typing import Any, Dict, List, Optional
from api.models.ward_transfer import WardTransfer, WardTransferCreate
from api.models.roster import Roster, RosterStatus
from api.models.roster_details import RosterDetails
from api.models.staff import Staff
from api.types.responses import ApiResponse
from api.utils.logger import get_logger
from datetime import date, datetime, timedelta
from bson import ObjectId


logger = get_logger("ward_transfer_service")


def build_staff_snapshot(staff: Staff) -> Dict[str, Any]:
    """Capture relevant staff metadata for transfer records."""
    ward_ids = [str(wid) for wid in (staff.ward_id or [])]
    return {
        "staff_id": str(staff.id) if staff.id else None,
        "name": staff.name,
        "grade": staff.grade,
        "position": staff.position,
        "contact_no": staff.contact_no,
        "email": str(staff.email) if staff.email else None,
        "hospital_id": str(staff.hospital_id),
        "ward_ids": ward_ids,
    }


def calculate_day_index(transfer_date: date, period_start: date) -> str:
    """Calculate day index (0-based) for a date within a roster period"""
    delta = (transfer_date - period_start).days
    if delta < 0:
        raise ValueError(f"Transfer date {transfer_date} is before roster start {period_start}")
    return str(delta)


async def create_ward_transfer(transfer_data: dict) -> ApiResponse:
    """
    Create a ward transfer for an employee.
    
    Steps:
    1. Validate input and find source/destination rosters
    2. Validate staff assignment in source roster
    3. Create the persistent WardTransfer record
    4. Update source roster data (mark slot as TRANSFER_OUT)
    5. Update destination roster data (apply incoming shift)
    6. Attach rich transfer metadata to both rosters for UI/analytics
    """
    try:
        # Extract input
        staff_id = transfer_data.get("staff_id")
        hospital_id = transfer_data.get("hospital_id")
        transfer_date = transfer_data.get("transfer_date")
        from_shift = transfer_data.get("from_shift")
        to_shift = transfer_data.get("to_shift")
        from_ward_id = transfer_data.get("from_ward_id")
        to_ward_id = transfer_data.get("to_ward_id")
        remarks = transfer_data.get("remarks")  # Optional remarks field
        created_by = transfer_data.get("created_by")

        # Validate required fields
        if not all([staff_id, hospital_id, transfer_date, from_shift, to_shift, from_ward_id, to_ward_id, created_by]):
            return ApiResponse.fail("Missing required fields for transfer")

        if from_ward_id == to_ward_id:
            return ApiResponse.fail("Source and destination wards cannot be the same")

        if isinstance(transfer_date, str):
            transfer_date = date.fromisoformat(transfer_date)

        # Convert string IDs to ObjectId
        staff_obj_id = ObjectId(staff_id)
        hospital_obj_id = ObjectId(hospital_id)
        from_ward_obj_id = ObjectId(from_ward_id)
        to_ward_obj_id = ObjectId(to_ward_id)
        created_by_obj_id = ObjectId(created_by)

        # Validate staff exists and get employee_id
        staff = await Staff.get(staff_obj_id)
        if not staff:
            return ApiResponse.fail("Staff member not found")

        # Derive employee metadata
        employee_id = staff.emp_id
        if not employee_id:
            return ApiResponse.fail("Staff member does not have an employee ID")
        staff_snapshot = build_staff_snapshot(staff)

        # Find source roster covering the transfer date
        source_roster = await Roster.find_one({
            "ward_id": from_ward_obj_id,
            "period_start": {"$lte": transfer_date},
            "period_end": {"$gte": transfer_date},
            "status": {"$in": [RosterStatus.ACCEPTED.value, RosterStatus.PUBLISHED.value]}
        })

        if not source_roster:
            return ApiResponse.fail(f"No active roster found for source ward on {transfer_date}")

        # Find source roster details
        source_roster_details = await RosterDetails.find_one({"roster_id": source_roster.id})
        if not source_roster_details:
            return ApiResponse.fail("Source roster details not found")

        # Calculate day index
        try:
            day_index = calculate_day_index(transfer_date, source_roster.period_start)
        except ValueError as e:
            return ApiResponse.fail(str(e))

        # Validate staff is assigned in source roster for that day/shift
        source_roster_map = source_roster_details.roster
        if employee_id not in source_roster_map:
            return ApiResponse.fail(f"Employee {employee_id} not found in source roster")

        day_schedule = source_roster_map.get(employee_id, {}).get(day_index, [])
        if isinstance(day_schedule, str):
            day_schedule = [day_schedule]
        elif not isinstance(day_schedule, list):
            day_schedule = []

        # Validate that the employee has the from_shift assigned on that day
        if from_shift not in day_schedule:
            return ApiResponse.fail(f"Employee {employee_id} does not have shift {from_shift} assigned on {transfer_date} in source ward")

        # Find destination roster covering the transfer date
        destination_roster = await Roster.find_one({
            "ward_id": to_ward_obj_id,
            "period_start": {"$lte": transfer_date},
            "period_end": {"$gte": transfer_date},
            "status": {"$in": [RosterStatus.ACCEPTED.value, RosterStatus.PUBLISHED.value]}
        })

        if not destination_roster:
            return ApiResponse.fail(f"No active roster found for destination ward on {transfer_date}")

        # Find destination roster details
        destination_roster_details = await RosterDetails.find_one({"roster_id": destination_roster.id})
        if not destination_roster_details:
            return ApiResponse.fail("Destination roster details not found")

        # Check for existing transfer on same day/shift
        existing_transfer = await WardTransfer.find_one({
            "staff_id": staff_obj_id,
            "transfer_date": transfer_date,
            "from_shift": from_shift,
            "status": {"$in": ["pending", "applied"]}
        })
        if existing_transfer:
            return ApiResponse.fail("Transfer already exists for this staff/date/from_shift combination")

        # Create WardTransfer document
        transfer_doc = WardTransfer(
            hospital_id=hospital_obj_id,
            staff_id=staff_obj_id,
            employee_id=employee_id,
            transfer_date=transfer_date,
            from_shift=from_shift,
            to_shift=to_shift,
            from_ward_id=from_ward_obj_id,
            to_ward_id=to_ward_obj_id,
            roster_id=source_roster.id,
            roster_details_id=source_roster_details.id,
            destination_roster_id=destination_roster.id,
            destination_roster_details_id=destination_roster_details.id,
            status="pending",
            remarks=remarks,
            created_by=created_by_obj_id
        )
        await transfer_doc.insert()

        # Update source roster: replace from_shift with TRANSFER_OUT
        updated_day_schedule = []
        for shift in day_schedule:
            if shift == from_shift:
                updated_day_schedule.append("TRANSFER_OUT")
            else:
                updated_day_schedule.append(shift)
        source_roster_map[employee_id][day_index] = updated_day_schedule
        source_roster_details.roster = source_roster_map
        source_roster_details.update_timestamp()
        await source_roster_details.save()

        # Note: Destination roster data is NOT modified - transfers are metadata only
        # The UI will use the transfer record to show incoming transfers

        # Mark transfer as applied
        transfer_doc.status = "applied"
        transfer_doc.update_timestamp()
        await transfer_doc.save()

        # Prepare response
        transfer_response = {
            "id": str(transfer_doc.id),
            "employee_id": employee_id,
            "transfer_date": transfer_date.isoformat(),
            "from_shift": from_shift,
            "to_shift": to_shift,
            "from_ward_id": str(from_ward_obj_id),
            "to_ward_id": str(to_ward_obj_id),
            "status": "applied",
            "remarks": remarks,
            "created_at": transfer_doc.created_at.isoformat()
        }

        logger.info(f"Ward transfer created successfully: {transfer_doc.id}")
        return ApiResponse.ok("Ward transfer created and applied successfully", transfer_response)

    except Exception as e:
        logger.error(f"Failed to create ward transfer: {e}", exc_info=True)
        return ApiResponse.fail(f"Failed to create ward transfer: {str(e)}")


async def get_transfers_for_wards_batch(ward_ids: List[str], ward_rosters_map: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Batch fetch transfers for multiple wards at once, matching transfers to the correct roster.
    
    Args:
        ward_ids: List of ward IDs to get transfers for
        ward_rosters_map: Dict mapping ward_id to list of roster info (each with roster, period_start, period_end)
    
    Returns:
        Dict mapping roster_id to list of transfers (only transfers that fall within that roster's period)
    """
    try:
        if not ward_ids:
            return {}
        
        ward_obj_ids = [ObjectId(wid) for wid in ward_ids]
        
        # Fetch all transfers for all wards in one query
        transfers = await WardTransfer.find({
            "$or": [
                {"from_ward_id": {"$in": ward_obj_ids}},
                {"to_ward_id": {"$in": ward_obj_ids}}
            ],
            "status": {"$in": ["pending", "applied"]}
        }).to_list()
        
        # Get all unique staff_ids to batch fetch
        staff_ids = list(set([t.staff_id for t in transfers]))
        staff_map = {}
        if staff_ids:
            staff_list = await Staff.find({"_id": {"$in": staff_ids}}).to_list()
            staff_map = {str(s.id): s for s in staff_list}
        
        # Build a map of roster_id -> roster info for quick lookup
        roster_info_map: Dict[str, Dict[str, Any]] = {}
        for ward_id, rosters_list in ward_rosters_map.items():
            for roster_info in rosters_list:
                roster_id = str(roster_info["roster"].id)
                roster_info_map[roster_id] = {
                    "ward_id": ward_id,
                    "period_start": roster_info["period_start"],
                    "period_end": roster_info["period_end"]
                }
        
        # Group transfers by roster_id, matching each transfer to the specific roster that covers its date
        transfers_by_roster: Dict[str, List[Dict[str, Any]]] = {rid: [] for rid in roster_info_map.keys()}
        
        def find_matching_roster(ward_id: str, transfer_date: date) -> Optional[Dict[str, Any]]:
            """Find the specific roster that covers the transfer date for a given ward"""
            rosters = ward_rosters_map.get(ward_id, [])
            for roster_info in rosters:
                period_start = roster_info["period_start"]
                period_end = roster_info["period_end"]
                if period_start <= transfer_date <= period_end:
                    return {
                        "roster_id": str(roster_info["roster"].id),
                        "period_start": period_start,
                        "period_end": period_end
                    }
            return None
        
        for transfer in transfers:
            # Get staff snapshot from cache
            staff = staff_map.get(str(transfer.staff_id))
            staff_snapshot = {}
            if staff:
                staff_snapshot = build_staff_snapshot(staff)
            
            # Process transfer for source ward (from_ward_id)
            from_ward_id = str(transfer.from_ward_id)
            if from_ward_id in ward_ids:
                roster_match = find_matching_roster(from_ward_id, transfer.transfer_date)
                if roster_match:
                    roster_id = roster_match["roster_id"]
                    try:
                        day_index = calculate_day_index(transfer.transfer_date, roster_match["period_start"])
                        transfer_record = {
                            "transfer_id": str(transfer.id),
                            "direction": "out",
                            "staff_id": str(transfer.staff_id),
                            "employee_id": transfer.employee_id,
                            "day_index": day_index,
                            "transfer_date": transfer.transfer_date.isoformat(),
                            "from_shift": transfer.from_shift,
                            "to_shift": transfer.to_shift,
                            "from_ward_id": from_ward_id,
                            "to_ward_id": str(transfer.to_ward_id),
                            "staff_snapshot": staff_snapshot,
                            "remarks": transfer.remarks,
                            "created_by": str(transfer.created_by),
                            "created_at": transfer.created_at.isoformat()
                        }
                        transfers_by_roster[roster_id].append(transfer_record)
                    except ValueError as e:
                        logger.warning(f"Could not calculate day_index for transfer {transfer.id} (from_ward {from_ward_id}): {e}")
            
            # Process transfer for destination ward (to_ward_id)
            to_ward_id = str(transfer.to_ward_id)
            if to_ward_id in ward_ids:
                roster_match = find_matching_roster(to_ward_id, transfer.transfer_date)
                if roster_match:
                    roster_id = roster_match["roster_id"]
                    try:
                        day_index = calculate_day_index(transfer.transfer_date, roster_match["period_start"])
                        transfer_record = {
                            "transfer_id": str(transfer.id),
                            "direction": "in",
                            "staff_id": str(transfer.staff_id),
                            "employee_id": transfer.employee_id,
                            "day_index": day_index,
                            "transfer_date": transfer.transfer_date.isoformat(),
                            "from_shift": transfer.from_shift,
                            "to_shift": transfer.to_shift,
                            "from_ward_id": from_ward_id,
                            "to_ward_id": to_ward_id,
                            "staff_snapshot": staff_snapshot,
                            "remarks": transfer.remarks,
                            "created_by": str(transfer.created_by),
                            "created_at": transfer.created_at.isoformat()
                        }
                        transfers_by_roster[roster_id].append(transfer_record)
                    except ValueError as e:
                        logger.warning(f"Could not calculate day_index for transfer {transfer.id} (to_ward {to_ward_id}): {e}")
        
        return transfers_by_roster
    except Exception as e:
        logger.error(f"Failed to batch get transfers for wards: {e}", exc_info=True)
        return {wid: [] for wid in ward_ids}


async def get_transfers_for_ward(ward_id: str, roster_period_start: date) -> List[Dict[str, Any]]:
    """
    Get all transfers associated with a ward (both as source and destination).
    
    This function finds transfers where:
    - from_ward_id matches → direction "out" (transfers out of this ward)
    - to_ward_id matches → direction "in" (transfers into this ward)
    
    Both types are included in the returned array.
    
    Args:
        ward_id: The ward ID from roster_input to get transfers for
        roster_period_start: The period_start date of the roster (needed to calculate day_index)
    
    Returns:
        List of TransferRecord-like dictionaries with direction set appropriately
    """
    try:
        ward_obj_id = ObjectId(ward_id)
        
        # Find transfers where this ward is involved (either as source or destination)
        transfers = await WardTransfer.find({
            "$or": [
                {"from_ward_id": ward_obj_id},  # Ward is source (outgoing transfers)
                {"to_ward_id": ward_obj_id}     # Ward is destination (incoming transfers)
            ],
            "status": {"$in": ["pending", "applied"]}
        }).to_list()
        
        # Batch fetch all staff records at once
        staff_ids = list(set([t.staff_id for t in transfers]))
        staff_map = {}
        if staff_ids:
            staff_list = await Staff.find({"_id": {"$in": staff_ids}}).to_list()
            staff_map = {str(s.id): s for s in staff_list}
        
        # Convert to TransferRecord format
        transfer_records = []
        for transfer in transfers:
            # Determine direction based on which ward_id matches
            if str(transfer.from_ward_id) == str(ward_obj_id):
                # This ward is the source → transfer is going OUT
                direction = "out"
            elif str(transfer.to_ward_id) == str(ward_obj_id):
                # This ward is the destination → transfer is coming IN
                direction = "in"
            else:
                # Shouldn't happen since we filtered by $or, but skip if it does
                continue
            
            # Calculate day_index
            try:
                day_index = calculate_day_index(transfer.transfer_date, roster_period_start)
            except ValueError as e:
                logger.warning(f"Could not calculate day_index for transfer {transfer.id}: {e}")
                continue  # Skip if we can't calculate day_index
            
            # Get staff snapshot from cache
            staff = staff_map.get(str(transfer.staff_id))
            staff_snapshot = {}
            if staff:
                staff_snapshot = build_staff_snapshot(staff)
            
            transfer_records.append({
                "transfer_id": str(transfer.id),
                "direction": direction,
                "staff_id": str(transfer.staff_id),
                "employee_id": transfer.employee_id,
                "day_index": day_index,
                "transfer_date": transfer.transfer_date.isoformat(),
                "from_shift": transfer.from_shift,
                "to_shift": transfer.to_shift,
                "from_ward_id": str(transfer.from_ward_id),
                "to_ward_id": str(transfer.to_ward_id),
                "staff_snapshot": staff_snapshot,
                "remarks": transfer.remarks,
                "created_by": str(transfer.created_by),
                "created_at": transfer.created_at.isoformat()
            })
        
        return transfer_records
    except Exception as e:
        logger.error(f"Failed to get transfers for ward {ward_id}: {e}", exc_info=True)
        return []


async def get_ward_transfers(
    hospital_id: Optional[str] = None,
    ward_id: Optional[str] = None,
    staff_id: Optional[str] = None,
    transfer_date: Optional[date] = None,
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> ApiResponse:
    """
    Get list of ward transfers with optional filtering.
    
    Args:
        hospital_id: Filter by hospital ID
        ward_id: Filter by ward ID (matches both source and destination)
        staff_id: Filter by staff ID
        transfer_date: Filter by specific transfer date (exact match)
        period_start: Start date for date range filter (use with period_end)
        period_end: End date for date range filter (use with period_start)
        status: Filter by transfer status (defaults to active transfers if not specified)
        limit: Maximum number of transfers to return
        offset: Number of transfers to skip
    """
    try:
        query = {}

        if hospital_id:
            query["hospital_id"] = ObjectId(hospital_id)
        if ward_id:
            # Match either from_ward_id or to_ward_id
            query["$or"] = [
                {"from_ward_id": ObjectId(ward_id)},
                {"to_ward_id": ObjectId(ward_id)}
            ]
        if staff_id:
            query["staff_id"] = ObjectId(staff_id)
        
        # Date filtering: either exact date or date range
        if transfer_date:
            query["transfer_date"] = transfer_date
        elif period_start and period_end:
            query["transfer_date"] = {"$gte": period_start, "$lte": period_end}
        elif period_start:
            query["transfer_date"] = {"$gte": period_start}
        elif period_end:
            query["transfer_date"] = {"$lte": period_end}
        
        # Default to active transfers if status not specified
        if status:
            query["status"] = status
        else:
            query["status"] = {"$in": ["pending", "applied"]}

        transfers = await WardTransfer.find(query).skip(offset).limit(limit).sort([("created_at", -1)]).to_list()
        total = await WardTransfer.find(query).count()

        # Recursive function to convert ObjectIds to strings
        def convert_objectid_recursive(obj):
            """Recursively convert ObjectId to string in nested structures"""
            if obj is None:
                return None
            elif isinstance(obj, ObjectId):
                return str(obj)
            elif isinstance(obj, date):
                return obj.isoformat()
            elif isinstance(obj, datetime):
                return obj.isoformat()
            elif isinstance(obj, dict):
                return {k: convert_objectid_recursive(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_objectid_recursive(item) for item in obj]
            else:
                return obj

        # Convert to response format - ensure all ObjectIds are converted to strings
        transfer_list = []
        for transfer in transfers:
            # Get all fields as dict
            transfer_dict = transfer.model_dump(mode='python')
            
            # Recursively convert all ObjectIds to strings
            transfer_dict = convert_objectid_recursive(transfer_dict)
            
            # Ensure id is a string (it might be _id in the dict)
            if '_id' in transfer_dict:
                transfer_dict['id'] = str(transfer_dict.pop('_id'))
            else:
                transfer_dict['id'] = str(transfer.id)
            
            transfer_list.append(transfer_dict)

        return ApiResponse.ok(
            "Ward transfers retrieved successfully",
            {
                "transfers": transfer_list,
                "total": total,
                "limit": limit,
                "offset": offset
            }
        )

    except Exception as e:
        logger.error(f"Failed to get ward transfers: {e}", exc_info=True)
        return ApiResponse.fail(f"Failed to retrieve ward transfers: {str(e)}")


async def get_transfer_counts_for_wards(
    ward_ids: List[str],
    roster_period_map: Dict[str, Dict[str, date]]  # {ward_id: {"period_start": date, "period_end": date}}
) -> Dict[str, Dict[str, int]]:
    """
    Get transfer counts per ward within their roster periods.
    
    Counts transfers where transfer_date falls within the roster period (period_start <= transfer_date <= period_end).
    Only counts active transfers (status: pending or applied).
    
    Args:
        ward_ids: List of ward IDs
        roster_period_map: Dict mapping ward_id to {"period_start": date, "period_end": date}
    
    Returns:
        Dict mapping ward_id to {"in": count, "out": count, "total": count}
    """
    try:
        if not ward_ids:
            return {}
        
        ward_obj_ids = [ObjectId(wid) for wid in ward_ids]
        
        # Build date range queries for each ward
        date_range_queries = []
        for ward_id in ward_ids:
            period_info = roster_period_map.get(ward_id)
            if period_info:
                period_start = period_info.get("period_start")
                period_end = period_info.get("period_end")
                if period_start and period_end:
                    date_range_queries.append({
                        "$and": [
                            {"$or": [
                                {"from_ward_id": ObjectId(ward_id)},
                                {"to_ward_id": ObjectId(ward_id)}
                            ]},
                            {"transfer_date": {"$gte": period_start, "$lte": period_end}},
                            {"status": {"$in": ["pending", "applied"]}}
                        ]
                    })
        
        if not date_range_queries:
            return {wid: {"in": 0, "out": 0, "total": 0} for wid in ward_ids}
        
        # Fetch all transfers matching any ward's date range
        transfers = await WardTransfer.find({
            "$or": date_range_queries
        }).to_list()
        
        # Initialize counts
        counts_by_ward: Dict[str, Dict[str, int]] = {
            wid: {"in": 0, "out": 0, "total": 0} for wid in ward_ids
        }
        
        # Count transfers per ward
        for transfer in transfers:
            transfer_date = transfer.transfer_date
            from_ward_id_str = str(transfer.from_ward_id)
            to_ward_id_str = str(transfer.to_ward_id)
            
            # Check if transfer falls within roster period for source ward
            if from_ward_id_str in ward_ids:
                period_info = roster_period_map.get(from_ward_id_str)
                if period_info:
                    period_start = period_info.get("period_start")
                    period_end = period_info.get("period_end")
                    if period_start and period_end and period_start <= transfer_date <= period_end:
                        counts_by_ward[from_ward_id_str]["out"] += 1
                        counts_by_ward[from_ward_id_str]["total"] += 1
            
            # Check if transfer falls within roster period for destination ward
            if to_ward_id_str in ward_ids:
                period_info = roster_period_map.get(to_ward_id_str)
                if period_info:
                    period_start = period_info.get("period_start")
                    period_end = period_info.get("period_end")
                    if period_start and period_end and period_start <= transfer_date <= period_end:
                        counts_by_ward[to_ward_id_str]["in"] += 1
                        counts_by_ward[to_ward_id_str]["total"] += 1
        
        return counts_by_ward
    except Exception as e:
        logger.error(f"Failed to get transfer counts for wards: {e}", exc_info=True)
        return {wid: {"in": 0, "out": 0, "total": 0} for wid in ward_ids}


async def cancel_ward_transfer(transfer_id: str) -> ApiResponse:
    """
    Cancel a ward transfer (soft delete) and reverse its effects on active rosters only.
    
    Steps:
    1. Find the transfer record
    2. Check if transfer is already cancelled
    3. Check if source roster is still active (ACCEPTED/PUBLISHED)
    4. If active, reverse roster changes (restore from_shift in source)
    5. Mark transfer status as "cancelled" (don't delete - keep for history)
    """
    try:
        # Validate and convert transfer_id
        try:
            transfer_obj_id = ObjectId(transfer_id)
        except Exception:
            return ApiResponse.fail("Invalid transfer ID format")

        # Find the transfer
        transfer_doc = await WardTransfer.get(transfer_obj_id)
        if not transfer_doc:
            return ApiResponse.fail("Transfer not found")
        
        # Check if already cancelled
        if transfer_doc.status == "cancelled":
            return ApiResponse.fail("Transfer is already cancelled")

        # Get source roster to check status and calculate day_index
        source_roster = await Roster.get(transfer_doc.roster_id)
        if not source_roster:
            return ApiResponse.fail("Source roster not found")

        # Only reverse changes if roster is still active
        if source_roster.status in [RosterStatus.ACCEPTED.value, RosterStatus.PUBLISHED.value]:
            # Get source roster details
            source_roster_details = await RosterDetails.get(transfer_doc.roster_details_id)
            if not source_roster_details:
                return ApiResponse.fail("Source roster details not found")

            # Calculate day_index for source roster
            try:
                source_day_index = calculate_day_index(transfer_doc.transfer_date, source_roster.period_start)
            except ValueError as e:
                return ApiResponse.fail(str(e))

            # Reverse source roster changes
            source_roster_map = source_roster_details.roster
            employee_id = transfer_doc.employee_id
            
            if employee_id in source_roster_map and source_day_index in source_roster_map[employee_id]:
                day_schedule = source_roster_map[employee_id][source_day_index]
                if isinstance(day_schedule, list) and "TRANSFER_OUT" in day_schedule:
                    # Replace TRANSFER_OUT with the original from_shift
                    restored_schedule = []
                    for shift in day_schedule:
                        if shift == "TRANSFER_OUT":
                            restored_schedule.append(transfer_doc.from_shift)
                        else:
                            restored_schedule.append(shift)
                    source_roster_map[employee_id][source_day_index] = restored_schedule
                    source_roster_details.roster = source_roster_map
                    source_roster_details.update_timestamp()
                    await source_roster_details.save()
                    logger.info(f"Reversed roster changes for active roster: {source_roster.id}")
        else:
            logger.info(f"Skipping roster reversal - roster {source_roster.id} is not active (status: {source_roster.status})")

        # Note: Destination roster data is NOT modified during cancellation
        # Since we don't modify destination roster during create, there's nothing to restore

        # Mark transfer as cancelled (soft delete - keep record for history)
        transfer_doc.status = "cancelled"
        transfer_doc.update_timestamp()
        await transfer_doc.save()

        logger.info(f"Ward transfer cancelled successfully: {transfer_id}")
        return ApiResponse.ok("Ward transfer cancelled successfully", {
            "id": str(transfer_doc.id),
            "status": "cancelled"
        })

    except Exception as e:
        logger.error(f"Failed to cancel ward transfer: {e}", exc_info=True)
        return ApiResponse.fail(f"Failed to cancel ward transfer: {str(e)}")

