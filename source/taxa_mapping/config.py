from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # source/

class LocalSettings:
    # Percorsi ai dati di riferimento (via symlink ../data/)
    AGORA_MODELS_PATH = str(BASE_DIR / "data" / "mat_files_list.csv")
    NCBI_CACHE_PATH   = str(BASE_DIR / "data" / "ncbi_cache.json")

    # Alias lowercase per compatibilità con i moduli del worker
    agora_models_path = AGORA_MODELS_PATH
    ncbi_cache_path   = NCBI_CACHE_PATH

    # Parallelismo Joblib: usa tutti i core tranne uno
    N_JOBS = -2

settings = LocalSettings()
