"""Testing utilities and R&D experiments."""
import logging
from pathlib import Path

# Define project directories
TESTING_DIR = Path(__file__).resolve().parent
BACKEND_DIR = TESTING_DIR.parent

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
