import sys
import os

sys.path.append(os.getcwd())
os.environ["DATA_DIR"] = "./data"

from backend.tasks import task_process_ml_pipeline
task_process_ml_pipeline.delay()
print("Triggered ML pipeline task!")
