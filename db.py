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
def dump_mysql():
    host = "ccdi-dev-cpi-rds.cji2s0rgsplw.us-east-1.rds.amazonaws.com"
    port = 3306
    db = "cpi"
    dump_file = "dump_file_July22.sql"

    try:
        # Get credentials from AWS Secrets Manager
        creds = get_mysql_credentials("ccdi-dev-cpi-mysql")
        user = creds['user_name']
        password = creds['password']

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
        logger.info(f"Starting MySQL dump for database: {db}")
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

@flow(name="db-backup")
def mysql_backup_flow():
    result = dump_mysql()
    print(f"MySQL dump completed and saved to: {result}")

if __name__ == "__main__":
    mysql_backup_flow()
