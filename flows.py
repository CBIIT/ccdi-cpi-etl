"""
Combined flows for CCDI CPI ETL project.
This file imports and exposes both flows for easy deployment.
"""

from main import main as etl_flow
from db import mysql_backup_flow as db_backup_flow

# Re-export flows with clear names
__all__ = ['etl_flow', 'db_backup_flow']

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        flow_name = sys.argv[1]
        if flow_name == "etl":
            etl_flow()
        elif flow_name == "db-backup":
            db_backup_flow()
        else:
            print(f"Unknown flow: {flow_name}")
            print("Available flows: etl, db-backup")
            sys.exit(1)
    else:
        print("Available flows:")
        print("  etl - Run the main ETL pipeline")
        print("  db-backup - Run database backup")
        print("\nUsage: python flows.py <flow_name>")
