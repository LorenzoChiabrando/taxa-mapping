import json
import threading
from pathlib import Path

class ReportLoader:
    def __init__(self, filepath, on_success, on_error):
        self.filepath = Path(filepath)
        self.on_success = on_success
        self.on_error = on_error

    def start(self):
        thread = threading.Thread(target=self._load)
        thread.daemon = True
        thread.start()

    def _load(self):
        if not self.filepath.exists():
            self.on_error("File not found")
            return

        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            results = data.get("results", [])
            
            # Grouping Logic
            groups = {
                "unambiguous":       [], # GREEN
                "high_similarity":   [], # YELLOW-GREEN
                "near_tier":         [], # YELLOW
                "low_similarity":    [], # RED
                "no_correspondence": [], # BLACK
                "other":             []
            }

            for item in results:
                status = item.get("status", "other")
                if status in groups:
                    groups[status].append(item)
                else:
                    groups["other"].append(item)

            self.on_success(groups, data.get("total_bacteria", 0))

        except Exception as e:
            self.on_error(str(e))
