# MINeBUGS: Advanced Taxonomy Mapper

---

## 1. Installation & Prerequisites

Before executing the pipeline, ensure your environment is configured with Python 3.10 or higher.

### Install Python Dependencies
All required libraries are specified in the requirements.txt file. Install them using the following command:

```pip install -r requirements.txt```

### System Requirements (Linux/Ubuntu)
The graphical interface is built using Tkinter. On Linux systems, you must install the toolkit via the package manager to enable GUI functionality:

```
sudo apt-get update
sudo apt-get install python3-tk
```
---

## 2. Execution Methods

MINeBUGS can be operated through three distinct interfaces depending on your workflow requirements.

### Method A: CLI
The main.py script allows for headless execution, ideal for automated pipelines. The system automatically detects taxonomic name columns such as taxa_name, taxon, organism, or input_name.

Usage:

```
python main.py --input input_csv --output output_directory_path
```

---

### Method B: GUI
The GUI provides an interactive environment for real-time monitoring and visual result exploration.

Launch command:
```
python ui/app.py
```
---

### Method C: Docker 
For cross-platform compatibility without local installation, use the Docker container. This setup utilizes a virtual display accessible via a web browser.

1. Start:
```
docker compose up
```
2. Access the UI:
Navigate to the following URL in your browser:
```
http://localhost:8080/vnc.html
```
---

## 3. Output Directory Structure

Each execution creates a unique, timestamped run folder (e.g., run_123456/) within the output directory.

Directory Breakdown:
* /results: Contains final_mapping.csv and the comprehensive mapping_report.json.
* /debug: Contains intermediate data: Jaccard raw scores, filtering statistics, and NCBI rescue process logs.
* flow_analysis.png: A visual representation of the final mapping distribution.

---
