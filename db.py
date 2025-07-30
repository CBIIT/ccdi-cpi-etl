from prefect import flow, task
import subprocess
import os
import json
import boto3
import logging
from botocore.exceptions import ClientError

# Setup logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

@task
def get_mysql_credentials(secret_name: str, region_name: str = "us-east-1") -> dict:
    client = boto3.client("secretsmanager", region_name=region_name)

    try:
        response = client.get_secret_value(SecretId=secret_name)
    except ClientError as e:
        raise Exception(f"Unable to retrieve secret: {e}")
    
    if "SecretString" in response:
        return json.loads(response["SecretString"])
    else:
        import base64
        return json.loads(base64.b64decode(response["SecretBinary"]))

@task
def dump_mysql(environment: str = "dev"):
    # Environment-specific secret names
    env_secrets = {
        "dev": "ccdi-dev-cpi-mysql",
        "qa": "ccdi-qa-cpi-mysql", 
        "stage": "ccdi-stage-cpi-mysql",
        "prod": "ccdi-prod-cpi-mysql"
    }
    
    if environment not in env_secrets:
        raise ValueError(f"Invalid environment: {environment}. Must be one of: {list(env_secrets.keys())}")
    
    secret_name = env_secrets[environment]
    port = 3306
    db = "cpi"
    
    # Generate filename with today's date and environment
    from datetime import datetime
    today = datetime.now().strftime("%Y%m%d")
    dump_file = f"dump_file_{environment}_{today}.sql"

    try:
        # Get credentials from AWS Secrets Manager
        creds = get_mysql_credentials(secret_name)
        user = creds['user_name']
        password = creds['password']
        host = creds['host']  # Get host from secret manager

        # Create the command
        cmd = [
            "mysqldump",
            "-h", host,
            "-P", str(port),
            "-u", user,
            f"-p{password}",
            db
        ]

        # Run the command and redirect output
        logger.info(f"Starting MySQL dump for {environment} database: {db}")
        with open(dump_file, "w") as outfile:
            subprocess.run(cmd, stdout=outfile, check=True)
        
        logger.info(f"MySQL dump completed successfully: {dump_file}")
        return dump_file
        
    except subprocess.CalledProcessError as e:
        logger.error(f"MySQL dump failed: {e}")
        raise
    except Exception as e:
        logger.error(f"Error during MySQL dump: {e}")
        raise

@task
def restore_mysql(dump_file: str, environment: str = "dev"):
    """Restore MySQL database from a dump file"""
    # Environment-specific secret names
    env_secrets = {
        "dev": "ccdi-dev-cpi-mysql",
        "qa": "ccdi-qa-cpi-mysql", 
        "stage": "ccdi-stage-cpi-mysql",
        "prod": "ccdi-prod-cpi-mysql"
    }
    
    if environment not in env_secrets:
        raise ValueError(f"Invalid environment: {environment}. Must be one of: {list(env_secrets.keys())}")
    
    secret_name = env_secrets[environment]
    port = 3306
    db = "cpi"

    try:
        # Check if dump file exists
        if not os.path.exists(dump_file):
            raise FileNotFoundError(f"Dump file not found: {dump_file}")

        # Get credentials from AWS Secrets Manager
        creds = get_mysql_credentials(secret_name)
        user = creds['user_name']
        password = creds['password']
        host = creds['host']  # Get host from secret manager

        # Create the restore command
        cmd = [
            "mysql",
            "-h", host,
            "-P", str(port),
            "-u", user,
            f"-p{password}",
            db
        ]

        # Run the restore command
        logger.info(f"Starting MySQL restore to {environment} from file: {dump_file}")
        with open(dump_file, "r") as infile:
            result = subprocess.run(cmd, stdin=infile, check=True, capture_output=True, text=True)
        
        logger.info(f"MySQL restore to {environment} completed successfully from: {dump_file}")
        return f"Database restored successfully to {environment} from {dump_file}"
        
    except subprocess.CalledProcessError as e:
        logger.error(f"MySQL restore failed: {e}")
        if e.stderr:
            logger.error(f"Error details: {e.stderr}")
        raise
    except Exception as e:
        logger.error(f"Error during MySQL restore: {e}")
        raise

@flow(name="db-backup")
def mysql_backup_flow(environment: str = "dev"):
    """Backup MySQL database for specified environment"""
    result = dump_mysql(environment)
    print(f"MySQL dump for {environment} completed and saved to: {result}")

@flow(name="db-restore")
def mysql_restore_flow(dump_file: str, environment: str = "dev"):
    """Restore MySQL database from a dump file to specified environment"""
    result = restore_mysql(dump_file, environment)
    print(result)

if __name__ == "__main__":
    mysql_backup_flow()
