from api.config import MONGO_URI
from api.models.ward_transfer import WardTransfer
from api.models.revoked_token import RevokedToken
from api.utils.logger import get_logger
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from beanie import init_beanie
from typing import Optional

# Import your Beanie models
from api.models.hospital import Hospital
from api.models.hospital_rules import HospitalRules
from api.models.shift_definition import ShiftDefinition
from api.models.user import User
from api.models.staff import Staff
from api.models.ward import Ward
from api.models.roster import Roster
from api.models.roster_details import RosterDetails
from api.models.copilot_actions import CopilotActions
from api.models.notification import Notification
from api.models.chats import CopilotChats
from api.models.ward_occupancy import WardOccupancy

logger = get_logger("database")

class DatabaseManager:
    """MongoDB database connection manager with Beanie"""
    
    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None
        self.mongodb_url = MONGO_URI
        self.database_name = "shiftwise"
    
    async def connect(self):
        """Connect to MongoDB and initialize Beanie"""
        try:
            self.client = AsyncIOMotorClient(self.mongodb_url)
            self.db = self.client[self.database_name]
            
            # Test connection
            await self.client.admin.command('ismaster')
            logger.info("Connected to MongoDB successfully")
            
            # Initialize Beanie with your models
            await init_beanie(
                database=self.db,
                document_models=[
                    Hospital,
                    HospitalRules,
                    ShiftDefinition,
                    User,
                    Staff,
                    Ward,
                    Roster,
                    RosterDetails,
                    CopilotActions,
                    Notification,
                    CopilotChats,
                    WardOccupancy,
                    WardTransfer,
                    RevokedToken,
                ]
            )
            logger.info("Beanie initialized successfully")
                        
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from MongoDB"""
        if self.client:
            self.client.close()
            logger.info("Disconnected from MongoDB")

# Global database manager instance
db_manager = DatabaseManager()