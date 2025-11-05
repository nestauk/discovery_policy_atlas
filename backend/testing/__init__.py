"""Testing utilities and R&D experiments."""
from pathlib import Path
import logging

# Define project base directory
TESTING_DIR = Path(__file__).resolve().parents[0]

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
