# api/services/dashboard_service.py
import asyncio
from api.services.ward_occupancy_service import WardOccupancyService
from api.services.ward_service import WardService
from api.services.roster_service import get_active_rosters_by_date, get_all_rosters_by_date, get_nurse_count_by_shift
from api.services.ward_transfer_service import get_transfer_counts_for_wards
from api.types.responses import WardPerformanceResponse, KPISummary, WardPerformanceItem
from api.utils.logger import get_logger
from datetime import date
from typing import List, Dict

logger = get_logger("dashboard_service")

class DashboardService:
    
    @staticmethod
    async def get_ward_performance(hospital_id: str, date: date, shift: str = None, ward_name: str = None):
        """Get ward performance data with KPIs and shift-specific metrics"""
        try:
            # Input validation
            if not hospital_id:
                raise ValueError("hospital_id is required")
            if not date:
                raise ValueError("date is required")
            
            # Fetch all required data in TRUE parallel (using asyncio.gather)
            all_roster_data, occupancy_data, roster_data, ward_result, occupancy_summary = await asyncio.gather(
                get_all_rosters_by_date(hospital_id, date),
                WardOccupancyService.get_latest_occupancy_by_ward(hospital_id, date, ward_name, shift),
                get_active_rosters_by_date(hospital_id, date),
                WardService.get_wards_by_hospital(hospital_id, ward_name),
                WardOccupancyService.get_occupancy_summary(hospital_id, date, shift),
                return_exceptions=False
            )
            
            ward_data = ward_result["data"] if ward_result["success"] else []
            
            # Calculate KPIs and ward performance in parallel
            kpis, ward_performance = await asyncio.gather(
                DashboardService._calculate_kpis(occupancy_summary, ward_data, roster_data, all_roster_data),
                DashboardService._build_ward_performance(occupancy_data, ward_data, roster_data, shift, date),
                return_exceptions=False
            )
            
            return WardPerformanceResponse(
                hospital_id=hospital_id,
                date=date,
                shift=shift,
                kpis=kpis,
                ward_performance=ward_performance,
                ai_suggestions=[]
            )
        except Exception as e:
            logger.error(f"Error in get_ward_performance for hospital {hospital_id}, date {date}, shift {shift}: {e}")
            raise

    @staticmethod
    def _normalize_ward_name(name: str) -> str:
        """Normalize ward name for consistent comparison by removing extra spaces and converting to lowercase"""
        if not name:
            return ""
        # Remove extra spaces and normalize whitespace
        normalized = " ".join(name.split())
        return normalized.lower()

    @staticmethod
    async def _build_ward_performance(occupancy_data, ward_data, roster_data, shift, date):
        """Build ward performance data with shift-specific metrics"""
        ward_performance = []
        # Create lookups for efficient data access - filter by shift if provided
        if shift:
            occupancy_lookup = {DashboardService._normalize_ward_name(record["ward_name"]): record for record in occupancy_data if record.get("shift") == shift}
        else:
            occupancy_lookup = {DashboardService._normalize_ward_name(record["ward_name"]): record for record in occupancy_data}
        
        # Convert roster data to dictionaries
        roster_dicts = [roster.dict() if hasattr(roster, 'dict') else roster for roster in roster_data]
        roster_lookup = {str(roster.get("ward_id")): roster for roster in roster_dicts if roster.get("ward_id")}
        
        # Pre-fetch nurse counts for all wards with rosters in parallel (batch queries)
        nurse_count_tasks = []
        ward_id_to_roster = {}
        for ward in ward_data:
            ward_id = str(ward.id) if hasattr(ward, 'id') else ward.get("id", "")
            if ward_id and ward_id in roster_lookup:
                roster = roster_lookup[ward_id]
                ward_id_to_roster[ward_id] = roster
                nurse_count_tasks.append(get_nurse_count_by_shift(str(roster["id"]), date, shift))
        
        # Execute all nurse count queries in parallel
        nurse_count_results = await asyncio.gather(*nurse_count_tasks, return_exceptions=False) if nurse_count_tasks else []
        
        # Build cache from results
        shift_nurse_counts_cache = {}
        for i, ward_id in enumerate(ward_id_to_roster.keys()):
            if i < len(nurse_count_results):
                nurse_count_result = nurse_count_results[i]
                shift_nurse_counts_cache[ward_id] = nurse_count_result.get(shift, 0) if isinstance(nurse_count_result, dict) else 0
        
        # Pre-fetch all ward ratios in parallel (batch query to avoid N+1)
        ratio_tasks = []
        ward_id_list = []
        for ward in ward_data:
            ward_id = str(ward.id) if hasattr(ward, 'id') else ward.get("id", "")
            if ward_id:
                ward_id_list.append(ward_id)
                ratio_tasks.append(WardService.get_ward_bed_nurse_ratio(ward_id))
        
        ratio_results = await asyncio.gather(*ratio_tasks, return_exceptions=False) if ratio_tasks else []
        ratio_cache = {}
        for i, ward_id in enumerate(ward_id_list):
            if i < len(ratio_results):
                ratio_result = ratio_results[i]
                if ratio_result.get("success"):
                    ratio_str = ratio_result["data"].get("bed_nurse_ratio", "0:0")
                    ratio_cache[ward_id] = DashboardService._parse_ratio_string(ratio_str)
                else:
                    ratio_cache[ward_id] = 0
            else:
                ratio_cache[ward_id] = 0
        
        # Build roster period map for transfer counts
        roster_period_map = {}
        for roster in roster_dicts:
            ward_id = str(roster.get("ward_id", ""))
            if ward_id:
                roster_period_map[ward_id] = {
                    "period_start": roster.get("period_start"),
                    "period_end": roster.get("period_end")
                }
        
        # Fetch transfer counts for wards with rosters
        ward_ids_for_transfers = list(roster_period_map.keys())
        transfer_counts = {}
        if ward_ids_for_transfers:
            transfer_counts = await get_transfer_counts_for_wards(ward_ids_for_transfers, roster_period_map)
        
        # Process each ward
        for ward in ward_data:
            # Extract ward data
            if hasattr(ward, 'name'):
                ward_name, ward_id, ward_total_beds = ward.name, str(ward.id), ward.total_beds
            else:
                ward_name = ward.get("name", "")
                ward_id = ward.get("id", "")
                ward_total_beds = ward.get("total_beds", 0)
            
            # Get occupancy and nurse data
            occupancy = occupancy_lookup.get(DashboardService._normalize_ward_name(ward_name), {})
            shift_nurses = shift_nurse_counts_cache.get(ward_id, 0)
            
            # Get patient count - show "-" if no occupancy data
            if not occupancy:
                total_patients = 0  # Will be displayed as "-"
                patients_display = "-"
                beds_available_display = "-"
                occupancy_display = "-"

            else:
                total_patients = occupancy.get("total_present", 0)
                patients_display = str(total_patients)
                open_beds = occupancy.get("open_beds", 0)
                total_present = occupancy.get("total_present", 0)
                
                total_beds = occupancy.get("total_beds", ward_total_beds)
                bed_occupancy_percentage = occupancy.get("bed_occupancy_rate", 0)
                if bed_occupancy_percentage == 0 and total_beds > 0:
                    
                    occupied_beds = total_beds - open_beds

                    bed_occupancy_percentage = (occupied_beds / total_beds)
                occupancy_display = DashboardService._get_occupancy_segment(bed_occupancy_percentage)
                
                beds_available = open_beds - total_present
                beds_available_display = str(beds_available)
            
            # Calculate nurse utilization (using cached ratio)
            ideal_ratio_float = ratio_cache.get(ward_id, 0)
            nurse_utilization_str = DashboardService._calculate_nurse_utilization(total_patients, shift_nurses, ideal_ratio_float)
            ideal_ratio_str = f"{ideal_ratio_float:.1f}" if ideal_ratio_float > 0 else "N/A"
            
            if ideal_ratio_float > 0 and shift_nurses > 0:
                ideal_nurses_needed = total_patients / ideal_ratio_float
                deficit_surplus = shift_nurses - ideal_nurses_needed
                deficit_surplus_str = f"{deficit_surplus:+.0f}"
            else:
                deficit_surplus_str = "N/A"
            
            # Get transfer counts for this ward
            ward_transfer_counts = transfer_counts.get(ward_id, {"in": 0, "out": 0, "total": 0})
            
            ward_performance.append(WardPerformanceItem(
                ward_id=ward_id,
                ward_name=ward_name,
                shift_patients=patients_display,
                shift_nurses="-" if shift_nurses == 0 else str(shift_nurses),
                ideal_ratio=ideal_ratio_str,
                occupancy=occupancy_display,
                nurse_utilization=nurse_utilization_str,
                deficit_surplus=deficit_surplus_str,
                beds_available=beds_available_display,
                transfers_in=ward_transfer_counts["in"],
                transfers_out=ward_transfer_counts["out"],
                total_transfers=ward_transfer_counts["total"]
            ))

            ward_performance.sort(key=lambda ward: (
                ward.shift_patients == "-",  # False (0) for actual data, True (1) for "-"
                ward.shift_nurses == "-",    # False (0) for actual data, True (1) for "-"
                ward.ward_name.lower()       # Secondary sort by ward name
            ))
        
        return ward_performance

    @staticmethod
    def _parse_ratio_string(ratio_str: str) -> float:
        """Parse ratio string like '19:3' to float"""
        try:
            if ':' in ratio_str:
                beds, nurses = ratio_str.split(':')
                beds = int(beds.strip())
                nurses = int(nurses.strip())
                if nurses > 0:
                    return beds / nurses
            return 0.0
        except (ValueError, ZeroDivisionError):
            return 0.0
    
    @staticmethod
    def _get_occupancy_segment(occupancy_percentage: float) -> str:
        """Determine occupancy segment based on percentage"""
        if occupancy_percentage < 75:
            return "low"
        elif occupancy_percentage <= 90:
            return "medium"
        else:
            return "high"
    
    @staticmethod
    async def _calculate_kpis(occupancy_summary: Dict, ward_data: List, roster_data: List[Dict] = None, all_roster_data: List[Dict] = None) -> KPISummary:
        """Calculate KPI summary"""
        total_patients = occupancy_summary.get("total_patients", 0)
        bed_occupancy_percentage = occupancy_summary.get("bed_occupancy_percentage", 0)
        
        # Calculate live rosters (accepted rosters / total generated rosters)
        total_generated_rosters = len(all_roster_data) if all_roster_data else 0
        accepted_rosters = 0
        
        if roster_data:
            # Convert roster documents to dictionaries to avoid coroutine issues
            roster_dicts = []
            for roster in roster_data:
                if hasattr(roster, 'dict'):
                    roster_dicts.append(roster.dict())
                else:
                    roster_dicts.append(roster)
            
            # Count rosters with accepted status
            accepted_rosters = len([roster for roster in roster_dicts if roster.get("status") == "accepted"])
        
        # Calculate active wards (wards with accepted rosters)
        active_wards = 0
        if roster_data:
            # Get unique ward IDs that have accepted rosters
            active_ward_ids = set()
            for roster in roster_dicts:
                if roster.get("status") == "accepted" and roster.get("ward_id"):
                    active_ward_ids.add(roster.get("ward_id"))
            active_wards = len(active_ward_ids)
        
        # Determine occupancy status
        if bed_occupancy_percentage > 90:
            occupancy_status = "High Occupancy Alert"
        elif bed_occupancy_percentage > 80:
            occupancy_status = "Moderate Occupancy"
        else:
            occupancy_status = "Normal Occupancy"
        
        return KPISummary(
            total_patients=total_patients,
            bed_occupancy_percentage=bed_occupancy_percentage,
            live_rosters=f"{accepted_rosters}/{total_generated_rosters}",
            active_wards=active_wards,
            occupancy_status=occupancy_status
        )

    @staticmethod
    def _calculate_nurse_utilization(patients: int, nurses: int, ideal_ratio) -> str:
        """Calculate nurse utilization classification"""
        if nurses <= 0:
            return "N/A"
        
        ratio = patients / nurses
        relevant_ratio = ratio / ideal_ratio 

        if relevant_ratio > 1.1:
            return "High"
        elif relevant_ratio >= 0.8:
            return "Medium"
        else:
            return "Low"