#!/usr/bin/env python3
"""
Deploy script for CCDI CPI ETL flows.
This script helps deploy both ETL and DB backup flows to Prefect.
"""

import subprocess
import sys
from pathlib import Path

def run_command(cmd, description):
    """Run a command and handle errors."""
    print(f"\n🚀 {description}")
    print(f"Running: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("✅ Success!")
        if result.stdout:
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error: {e}")
        if e.stdout:
            print("STDOUT:", e.stdout)
        if e.stderr:
            print("STDERR:", e.stderr)
        return False

def main():
    """Deploy both flows to Prefect."""
    print("🔄 Deploying CCDI CPI ETL flows to Prefect...")
    
    # Change to the directory containing prefect.yaml
    config_dir = Path(__file__).parent / "config"
    original_dir = Path.cwd()
    
    try:
        if config_dir.exists():
            import os
            os.chdir(config_dir)
            print(f"📁 Changed to config directory: {config_dir}")
        
        # Deploy all flows defined in prefect.yaml
        success = run_command(
            ["prefect", "deploy", "--all"],
            "Deploying all flows from prefect.yaml"
        )
        
        if success:
            print("\n🎉 All flows deployed successfully!")
            print("\n📋 Available deployments:")
            print("  • etl-pipeline (Flow: etl)")
            print("  • database-backup (Flow: db-backup)")
            print("\n🌐 Check your Prefect UI to see the deployed flows.")
        else:
            print("\n💥 Deployment failed. Check the errors above.")
            sys.exit(1)
            
    finally:
        # Return to original directory
        import os
        os.chdir(original_dir)

if __name__ == "__main__":
    main()
