#!/usr/bin/env python
"""
TrendBlogo Autonomous Scheduler CLI.
Executes the auto-publishing queue directly via command line or cron job.
Usage:
    python run_scheduler.py [--force]
"""
import sys
from app.database import SessionLocal
from app.services.auto_scheduler import AutoSchedulerService

def main():
    force = "--force" in sys.argv
    print(f"Starting TrendBlogo Scheduler Run (force={force})...")
    with SessionLocal() as db:
        result = AutoSchedulerService.process_next_keyword(db, force=force)
        print("Execution Result:", result)

if __name__ == "__main__":
    main()
