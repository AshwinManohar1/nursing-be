from typing import Dict, List, Any
from datetime import datetime, date
from bs4 import BeautifulSoup
import re
from bson import ObjectId
from api.models.hospital import Hospital
from api.models.ward_occupancy import WardOccupancy, WardOccupancyCreate
from api.db import db_manager
from api.utils.logger import get_logger
from api.types.responses import ApiResponse

logger = get_logger("ward_occupancy_service")

collection = lambda: db_manager.db["ward_occupancy"]

def convert_objectid_to_str(doc):
    """Convert ObjectId fields to strings for JSON serialization"""
    if doc is None:
        return None
    if isinstance(doc, dict):
        return {k: str(v) if isinstance(v, ObjectId) else convert_objectid_to_str(v) for k, v in doc.items()}
    elif isinstance(doc, list):
        return [convert_objectid_to_str(item) for item in doc]
    return doc
    
class WardOccupancyService:

    @staticmethod
    def derive_shift_from_time(report_time: datetime) -> str:
        """
        Derive shift from report_time based on time ranges:
        - 8am-10am: Morning (M)
        - 2pm-3pm: Evening (E) 
        - 8pm-10pm: Night (N)
        - Default: General (G)
        """
        hour = report_time.hour
        
        if 6 <= hour <= 10:  # 6am-10am
            return 'M'
        elif 13 <= hour <= 15:  # 1pm-3pm
            return 'E'
        elif 19 <= hour <= 22:  # 7pm-10pm
            return 'N'
        else:
            return 'G'
    
    @staticmethod
    def parse_email_html(email_body: str) -> Dict[str, Any]:
        """Parse HTML email body and extract ward occupancy data"""
        try:
            soup = BeautifulSoup(email_body, 'html.parser')
            
            # Debug: Log basic HTML structure
            tables = soup.find_all('table')
            logger.info(f"Found {len(tables)} tables in HTML")
            
            # Extract metadata
            metadata = WardOccupancyService._extract_metadata(soup)
            logger.info(f"Extracted metadata: {metadata}")
            
            # Extract ward data from table
            ward_data = WardOccupancyService._extract_ward_data(soup)
            logger.info(f"Extracted {len(ward_data)} ward records")
            
            if not ward_data:
                return {
                    "success": False,
                    "message": "No ward data found in email",
                    "data": None
                }
            
            # Create ward occupancy records
            records = []
            for ward_info in ward_data:

                derived_shift = WardOccupancyService.derive_shift_from_time(metadata['report_time'])

                record = WardOccupancyCreate(
                    hospital_id=metadata['hospital_id'],
                    ward_name=ward_info['name'],
                    report_date=metadata['report_date'],
                    report_time=metadata['report_time'],
                    shift=derived_shift,
                    total_beds=ward_info['total_beds'],
                    open_beds=ward_info['open_beds'],
                    previous_day_total=ward_info['previous_day_total'],
                    new_admission=ward_info['new_admission'],
                    transfer_in=ward_info['transfer_in'],
                    transfer_out=ward_info['transfer_out'],
                    marked_for_discharge=ward_info['marked_for_discharge'],
                    normal_discharges=ward_info['normal_discharges'],
                    lama=ward_info['lama'],
                    deaths=ward_info['deaths'],
                    others=ward_info['others'],
                    total_present=ward_info['total_present'],
                    bed_occupancy_rate=ward_info['bed_occupancy_rate'],
                    source='integration',
                    raw_data=ward_info['raw_data']
                )
                records.append(record)

            logger.info(f"Created {len(records)} ward occupancy records")
            
            return {
                "success": True,
                "message":f"Successfully parsed {len(records)} ward records",
                "data":records
            }
            
        except Exception as e:
            logger.error(f"Error parsing email: {str(e)}")
            return {
                "success": False,
                "message": f"Error parsing email: {str(e)}",
                "data": None
            }
    
    @staticmethod
    def _extract_metadata(soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract metadata from email body"""
        metadata = {}
        text_content = soup.get_text()
        
        # Extract date - try multiple patterns
        date_patterns = [
            r'Date:\s*(\d{4}/\d{2}/\d{2})',
            r'(\d{2}/\d{2}/\d{4})',  # DD/MM/YYYY format
            r'(\d{4}-\d{2}-\d{2})'   # YYYY-MM-DD format
        ]
        
        for pattern in date_patterns:
            date_match = re.search(pattern, text_content)
            if date_match:
                date_str = date_match.group(1)
                try:
                    if '/' in date_str:
                        if len(date_str.split('/')[0]) == 4:  # YYYY/MM/DD
                            metadata['report_date'] = datetime.strptime(date_str, '%Y/%m/%d').date()
                        else:  # DD/MM/YYYY
                            metadata['report_date'] = datetime.strptime(date_str, '%d/%m/%Y').date()
                    else:  # YYYY-MM-DD
                        metadata['report_date'] = datetime.strptime(date_str, '%Y-%m-%d').date()
                    break
                except ValueError:
                    continue
        
        # If no date found, use today
        if 'report_date' not in metadata:
            metadata['report_date'] = date.today()
        
        # Extract hospital name - look for common patterns
        hospital_patterns = [
            r'Branch:\s*([^\n\r]+)',
            r'Hospital:\s*([^\n\r]+)',
            r'([A-Z\s]+HOSPITAL[A-Z\s]*)',  # Look for "HOSPITAL" in caps
        ]
        
        for pattern in hospital_patterns:
            hospital_match = re.search(pattern, text_content)
            if hospital_match:
                hospital_name = hospital_match.group(1).strip()
                # Clean up the hospital name
                hospital_name = re.sub(r'\s+', ' ', hospital_name)  # Remove extra spaces
                metadata['hospital_id'] = hospital_name
                break
        
        # If no hospital found, use a default
        if 'hospital_id' not in metadata:
            metadata['hospital_id'] = "Unknown Hospital"
        
        # Extract generation time
        gen_patterns = [
            r'Generated On:\s*(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2})',
            r'(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2})',  # DD/MM/YYYY HH:MM
        ]
        
        for pattern in gen_patterns:
            gen_match = re.search(pattern, text_content)
            if gen_match:
                gen_str = gen_match.group(1)
                try:
                    metadata['report_time'] = datetime.strptime(gen_str, '%d/%m/%Y %H:%M')
                    break
                except ValueError:
                    continue
        
        # If no generation time found, use current time
        if 'report_time' not in metadata:
            metadata['report_time'] = datetime.now()
        
        return metadata
    
    @staticmethod
    def _extract_ward_data(soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract ward data from HTML table"""
        ward_data = []
        
        # Find all tables in the document
        tables = soup.find_all('table')
        if not tables:
            return ward_data
        
        # Look for the main data table (usually the largest one with ward data)
        main_table = None
        for table in tables:
            rows = table.find_all('tr')
            if len(rows) > 5:  # Look for table with many rows (ward data)
                # Check if it has the expected structure
                first_row = rows[0] if rows else None
                if first_row:
                    cells = first_row.find_all(['td', 'th'])
                    if len(cells) >= 14:  # Expected number of columns
                        main_table = table
                        break
        
        if not main_table:
            return ward_data
        
        # Get table rows
        rows = main_table.find_all('tr')
        if len(rows) < 2:
            return ward_data
        
        # Process data rows (skip header and totals rows)
        for row in rows[1:]:
            cells = row.find_all(['td', 'th'])
            if len(cells) >= 14:
                try:
                    # Extract text from each cell, handling nested elements
                    cell_texts = []
                    for cell in cells:
                        # Get text content, handling nested <p> tags and <div> tags
                        text = cell.get_text(strip=True)
                        cell_texts.append(text)
                    
                    # Skip totals rows
                    if cell_texts[0].upper() in ['TOTALS', 'GRAND TOTALS', 'TOTAL']:
                        continue
                    
                    # Skip empty rows
                    if not cell_texts[0] or cell_texts[0] == '':
                        continue
                    
                    ward_info = {
                        'name': cell_texts[0],
                        'total_beds': int(cell_texts[1]) if cell_texts[1] else 0,
                        'open_beds': int(cell_texts[2]) if cell_texts[2] else 0,
                        'previous_day_total': int(cell_texts[3]) if cell_texts[3] else 0,
                        'new_admission': int(cell_texts[4]) if cell_texts[4] else 0,
                        'transfer_in': int(cell_texts[5]) if cell_texts[5] else 0,
                        'transfer_out': int(cell_texts[6]) if cell_texts[6] else 0,
                        'marked_for_discharge': int(cell_texts[7]) if cell_texts[7] else 0,
                        'normal_discharges': int(cell_texts[8]) if cell_texts[8] else 0,
                        'lama': int(cell_texts[9]) if cell_texts[9] else 0,
                        'deaths': int(cell_texts[10]) if cell_texts[10] else 0,
                        'others': int(cell_texts[11]) if cell_texts[11] else 0,
                        'total_present': int(cell_texts[12]) if cell_texts[12] else 0,
                        'bed_occupancy_rate': float(cell_texts[13]) if cell_texts[13] else 0.0,
                        'raw_data': {
                            'row_data': cell_texts
                        }
                    }
                    ward_data.append(ward_info)
                    
                except (ValueError, IndexError) as e:
                    # Skip rows that can't be parsed
                    logger.warning(f"Skipping row due to parsing error: {e}, row data: {cell_texts if 'cell_texts' in locals() else 'N/A'}")
                    continue
        
        return ward_data
    
    @staticmethod
    async def save_ward_occupancy_data(records: List[WardOccupancyCreate]) -> ApiResponse:
        """Save ward occupancy records to MongoDB"""
        try:
            saved_records = []
            for record in records:
                hospital = await Hospital.find_one({"name": {"$regex": f"^{record.hospital_id.lower()}$", "$options": "i"}})
                print(hospital, "hospital_record")

                derived_shift = WardOccupancyService.derive_shift_from_time(record.report_time)
                # Convert to document format for MongoDB
                document = {
                    "hospital_id": hospital.id,
                    "ward_name": record.ward_name,
                    "report_date": record.report_date.isoformat() if isinstance(record.report_date, date) else record.report_date,
                    "report_time": record.report_time.isoformat() if isinstance(record.report_time, datetime) else record.report_time,
                    "shift": derived_shift,
                    "total_beds": record.total_beds,
                    "open_beds": record.open_beds,
                    "previous_day_total": record.previous_day_total,
                    "new_admission": record.new_admission,
                    "transfer_in": record.transfer_in,
                    "transfer_out": record.transfer_out,
                    "marked_for_discharge": record.marked_for_discharge,
                    "normal_discharges": record.normal_discharges,
                    "lama": record.lama,
                    "deaths": record.deaths,
                    "others": record.others,
                    "total_present": record.total_present,
                    "bed_occupancy_rate": record.bed_occupancy_rate,
                    "source": record.source,
                    "raw_data": record.raw_data,
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat()
                }
                
                # Insert document
                result = await collection().insert_one(document)
                
                # Create WardOccupancy object with the inserted ID
                ward_occupancy = WardOccupancy(
                    id=str(result.inserted_id),
                    hospital_id=record.hospital_id,
                    ward_name=record.ward_name,
                    report_date=record.report_date,
                    report_time=record.report_time,
                    shift=derived_shift,
                    total_beds=record.total_beds,
                    open_beds=record.open_beds,
                    previous_day_total=record.previous_day_total,
                    new_admission=record.new_admission,
                    transfer_in=record.transfer_in,
                    transfer_out=record.transfer_out,
                    marked_for_discharge=record.marked_for_discharge,
                    normal_discharges=record.normal_discharges,
                    lama=record.lama,
                    deaths=record.deaths,
                    others=record.others,
                    total_present=record.total_present,
                    bed_occupancy_rate=record.bed_occupancy_rate,
                    source=record.source,
                    raw_data=record.raw_data,
                    created_at=datetime.fromisoformat(document["created_at"]),
                    updated_at=datetime.fromisoformat(document["updated_at"])
                )
                saved_records.append(ward_occupancy)
            
            logger.info(f"Successfully saved {len(saved_records)} ward occupancy records")
            
            return ApiResponse.ok(
                f"Successfully saved {len(saved_records)} ward occupancy records",
                saved_records
            )
            
        except Exception as e:
            logger.error(f"Error saving ward occupancy data: {str(e)}")
            return ApiResponse.fail(f"Error saving ward occupancy data: {str(e)}")
    
    @staticmethod
    async def get_ward_occupancy_data(
        hospital_id: str = None,
        ward_name: str = None,
        report_date: date = None,
        limit: int = 100,
        offset: int = 0
    ) -> ApiResponse:
        """Get ward occupancy records with optional filters from MongoDB"""
        try:
            from api.models.ward_occupancy import WardOccupancy
            
            # Build query filter using Beanie ORM
            query_filter = {}
            if hospital_id:
                query_filter["hospital_id"] = hospital_id
            if ward_name:
                query_filter["ward_name"] = ward_name
            if report_date:
                query_filter["report_date"] = report_date
            
            # Execute query with pagination using Beanie
            records = await WardOccupancy.find(query_filter).skip(offset).limit(limit).sort([("created_at", -1)]).to_list()
            
            # Convert to list of dicts
            documents = [convert_objectid_to_str(record.dict()) for record in records]
            
            logger.info(f"Retrieved {len(documents)} ward occupancy records")
            
            return ApiResponse.ok(
                f"Retrieved {len(documents)} ward occupancy records",
                documents
            )
            
        except Exception as e:
            logger.error(f"Error retrieving ward occupancy data: {str(e)}")
            return ApiResponse.fail(f"Error retrieving ward occupancy data: {str(e)}")

    @staticmethod
    async def get_ward_occupancy_by_id(occupancy_id: str) -> ApiResponse:
        """Get a single ward occupancy record by ID"""
        try:
            document = await collection().find_one({"_id": ObjectId(occupancy_id)})
            if not document:
                return ApiResponse.fail("Ward occupancy record not found")
            
            # Convert ObjectIds to strings and handle date/datetime fields
            document = convert_objectid_to_str(document)
            
            return ApiResponse.ok("Ward occupancy record retrieved successfully", document)
        except Exception as e:
            logger.error(f"Failed to fetch ward occupancy record: {e}")
            return ApiResponse.fail(f"Failed to fetch ward occupancy record: {e}")

    @staticmethod
    async def list_ward_occupancy_records(limit: int = 100) -> ApiResponse:
        """List all ward occupancy records"""
        try:
            documents = await collection().find({}).sort("created_at", -1).to_list(length=limit)
            # Convert ObjectIds to strings and handle date/datetime fields
            documents = convert_objectid_to_str(documents)
            
            return ApiResponse.ok("Ward occupancy records list fetched", documents)
        except Exception as e:
            logger.error(f"Failed to list ward occupancy records: {e}")
            return ApiResponse.fail(f"Failed to list ward occupancy records: {e}")

    
    @staticmethod
    async def get_latest_occupancy_by_ward(hospital_id: str, date: date, ward_name: str = None, shift: str = None) -> List[Dict]: 
        try:
            # Convert date to string format to match database storage
            date_str = date.isoformat()
            
            # Build query filter
            query_filter = {
                "hospital_id": ObjectId(hospital_id),
                "report_date": date_str
            }
            
            if ward_name:
                query_filter["ward_name"] = ward_name
            
            if shift:
                query_filter["shift"] = shift
            
            # Query MongoDB collection
            records = await collection().find(query_filter).to_list(None)
            
            # Convert ObjectIds to strings for JSON serialization
            return convert_objectid_to_str(records)
            
        except Exception as e:
            logger.error(f"Error in get_latest_occupancy_by_ward: {e}")
            return []


    @staticmethod
    async def get_occupancy_summary(hospital_id: str, date: date, shift: str = None) -> Dict:
        """Get summary statistics for all wards, optionally filtered by shift"""
        try:
            occupancy_data = await WardOccupancyService.get_latest_occupancy_by_ward(hospital_id, date, None, shift)
            
            # Calculate totals
            total_patients = sum(record.get("total_present", 0) for record in occupancy_data)
            total_beds = sum(record.get("total_beds", 0) for record in occupancy_data)
            occupied_beds = total_patients
            
            # Calculate bed occupancy percentage
            bed_occupancy_percentage = (occupied_beds / total_beds * 100) if total_beds > 0 else 0
            
            return {
                "total_patients": total_patients,
                "total_beds": total_beds,
                "occupied_beds": occupied_beds,
                "bed_occupancy_percentage": round(bed_occupancy_percentage, 2)
            }
        except Exception as e:
            logger.error(f"Error in get_occupancy_summary: {e}")
            return {
                "total_patients": 0,
                "total_beds": 0,
                "occupied_beds": 0,
                "bed_occupancy_percentage": 0
            }

    @staticmethod
    async def update_ward_occupancy(occupancy_id: str, update_data: dict) -> ApiResponse:
        """Update a ward occupancy record"""
        try:
            if not update_data:
                return ApiResponse.fail("No update data provided")

            if not occupancy_id:
                return ApiResponse.fail("No occupancy id provided")
            
            # Add updated_at timestamp
            update_data["updated_at"] = datetime.utcnow().isoformat()
            
            result = await collection().update_one(
                {"_id": ObjectId(occupancy_id)},
                {"$set": update_data}
            )
            
            if result.matched_count == 0:
                return ApiResponse.fail("Ward occupancy record not found")

            return ApiResponse.ok(
                "Ward occupancy record updated successfully", 
                {"id": occupancy_id, "updated_fields": list(update_data.keys())}
            )

        except Exception as e:
            logger.error(f"Failed to update ward occupancy record: {e}")
            return ApiResponse.fail(f"Failed to update ward occupancy record: {e}")

    @staticmethod
    async def delete_ward_occupancy(occupancy_id: str) -> ApiResponse:
        """Delete a ward occupancy record"""
        try:
            result = await collection().delete_one({"_id": ObjectId(occupancy_id)})
            if result.deleted_count == 0:
                return ApiResponse.fail("Ward occupancy record not found")
            return ApiResponse.ok("Ward occupancy record deleted successfully", {"id": occupancy_id})
        except Exception as e:
            logger.error(f"Failed to delete ward occupancy record: {e}")
            return ApiResponse.fail(f"Failed to delete ward occupancy record: {e}")

