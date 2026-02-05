import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

class LocalSettings:
    """
    Configuration class for the local execution environment.

    """

    # --- 1. Global File Paths ---
    # Absolute paths to the static reference data required by the algorithm.
    AGORA_MODELS_PATH = str(BASE_DIR / "data" / "mat_files_list.csv")
    NCBI_CACHE_PATH = str(BASE_DIR / "data" / "ncbi_cache.json")
    
    # Path for outputting results and intermediate debug files.
    SHARED_VOLUME_PATH = str(BASE_DIR / "output")

    # --- 2. Compatibility Aliases ---
    agora_models_path = AGORA_MODELS_PATH
    ncbi_cache_path = NCBI_CACHE_PATH
    shared_volume_path = SHARED_VOLUME_PATH
    
    # --- 3. Execution Settings ---
    # Number of CPU jobs for parallel processing via Joblib.
    N_JOBS = -2

    # --- 4. Infrastructure Mocks ---
    rabbit_host = "localhost"
    exchange = ""
    queue = ""


settings = LocalSettings()

Path(settings.SHARED_VOLUME_PATH).mkdir(parents=True, exist_ok=True)
