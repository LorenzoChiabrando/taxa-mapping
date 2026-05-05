from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # source/

class LocalSettings:
    # Paths to reference data (via symlink ../data/)
    AGORA_MODELS_PATH = str(BASE_DIR / "data" / "mat_files_list.csv")
    NCBI_CACHE_PATH   = str(BASE_DIR / "data" / "ncbi_cache.json")

    # Lowercase aliases for compatibility with worker modules
    agora_models_path = AGORA_MODELS_PATH
    ncbi_cache_path   = NCBI_CACHE_PATH

    # Joblib parallelism: use all cores minus one
    N_JOBS = -2

settings = LocalSettings()
