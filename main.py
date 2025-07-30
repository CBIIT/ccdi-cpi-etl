
import json
import networkx as nx
import pymysql
from datetime import datetime
import boto3
import logging
from prefect import flow, task

# Setup logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

@task
def get_mysql_credentials(secret_name: str, region_name: str = "us-east-1") -> dict:
    import boto3
    from botocore.exceptions import ClientError
    import json

    # Get current IAM role ARN for debugging
    try:
        sts_client = boto3.client("sts", region_name=region_name)
        identity = sts_client.get_caller_identity()
        current_arn = identity.get('Arn', 'Unknown')
        logger.info(f"Current execution role ARN: {current_arn}")
    except Exception as e:
        logger.warning(f"Could not retrieve current role ARN: {e}")

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
def read_data_from_db() -> list:
    result = []
    connection = None
    try:
        creds = get_mysql_credentials("ccdi-dev-cpi-mysql")
        connection = pymysql.connect(
            host=creds['host'],
            user=creds['user_name'],
            password=creds['password'],
            database='cpi',
            cursorclass=pymysql.cursors.DictCursor
        )
        with connection.cursor() as cursor:
            query = "SELECT `participant_id1` AS p1, `domain_name1` AS d1,  `participant_id2` AS p2,  `domain_name2` AS d2 FROM `mapping`"
            cursor.execute(query)
            result = cursor.fetchall()
    except pymysql.MySQLError as err:
        logger.error(f"Error: {err}")
    finally:
        if connection:
            connection.close()
    return result

@task
def get_relationships(uids: list) -> dict:
    G = nx.Graph()
    for i in uids:
        G.add_edge(i["p1"]+"::"+i["d1"], i["p2"]+"::"+i["d2"])
    return dict(nx.all_pairs_shortest_path(G))

@task
def format_output(graph: dict) -> list:
    unique_linked_sets = set()
    for _, relationships in graph.items():
        related = list(relationships.keys())
        related.sort()
        unique_linked_sets.add(tuple(related))
    return [{'related': list(set_)} for set_ in unique_linked_sets]

@task
def write_json_file(data: list, filename: str):
    with open(filename, "w") as file:
        json.dump(data, file, indent=4)

@task
def update_participants_from_json(json_file: str):
    creds = get_mysql_credentials("ccdi-dev-cpi-mysql")
    conn = pymysql.connect(
        host=creds['host'],
        user=creds['user_name'],
        password=creds['password'],
        database='cpi',
        autocommit=True
    )
    cursor = conn.cursor()
    try:
        # Step 1: Create temp table
        cursor.execute("DROP TEMPORARY TABLE IF EXISTS cpi.temp_alternatives")
        cursor.execute("""
            CREATE TEMPORARY TABLE cpi.temp_alternatives (
                id VARCHAR(255),
                alternative_participants TEXT
            )
        """)

        # Step 2: Load data from JSON and insert into temp table
        with open(json_file, 'r', encoding='utf-8-sig') as file:
            data = json.load(file)

        insert_query = "INSERT INTO cpi.temp_alternatives (id, alternative_participants) VALUES (%s, %s)"
        insert_values = []

        for item in data:
            linked_nodes = item['related']
            my_string = ', '.join(linked_nodes)
            for node_id in linked_nodes:
                insert_values.append((node_id, my_string))

        cursor.executemany(insert_query, insert_values)
        conn.commit()
        logger.info(f"Inserted {len(insert_values)} rows into temp table.")

        # Step 3: Clear existing values and update using join
        cursor.execute("UPDATE cpi.participant SET alternative_participants = NULL WHERE alternative_participants IS NOT NULL")
        conn.commit()
        logger.info("reset all alternative_participants to null")
        update_query = """
            UPDATE cpi.participant p
            JOIN cpi.temp_alternatives t ON p.id COLLATE utf8mb4_general_ci = t.id
            SET p.alternative_participants = t.alternative_participants
        """
        cursor.execute(update_query)
        conn.commit()
        logger.info("Bulk update of alternative_participants completed via temp table.")

    except Exception as e:
        logger.error(f"Error in update_participants_from_json: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

@task
def upload_to_s3(file_path: str, bucket: str, prefix: str):
    s3 = boto3.client('s3')
    today = datetime.today().strftime('%Y-%m-%d')
    key = f"{prefix}{today}.json"
    s3.upload_file(file_path, bucket, key)
    logger.info(f"Uploaded to s3://{bucket}/{key}")

@task
def update_statistics():
    notify_completion("main_with_logging_optimized.py has completed successfully.")
    creds = get_mysql_credentials("ccdi-dev-cpi-mysql")
    conn = pymysql.connect(
        host=creds['host'],
        user=creds['user_name'],
        password=creds['password'],
        database='cpi',
        autocommit=True
    )
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM cpi.statistic WHERE is_domain=1;")
        insert_query = """
            INSERT INTO cpi.statistic (counts_name, counts, is_domain)
            SELECT domain_name AS counts_name, COUNT(*) AS counts, 1 AS is_domain
            FROM cpi.participant
            GROUP BY domain_name;
        """
        cursor.execute(insert_query)

        # Update mapped_participant_count
        cursor.execute("SELECT COUNT(*) FROM cpi.mapping;")
        count = cursor.fetchone()[0]
        cursor.execute("""
            INSERT INTO cpi.statistic (counts_name, counts, is_domain)
            VALUES ('mapped_participant_count', %s, 0)
            ON DUPLICATE KEY UPDATE counts = VALUES(counts);
        """, (count,))

        # Update unique_participant_count
        cursor.execute("SELECT COUNT(DISTINCT alternative_participants) FROM cpi.participant;")
        unique_count = cursor.fetchone()[0]
        cursor.execute("""
            INSERT INTO cpi.statistic (counts_name, counts, is_domain)
            VALUES ('unique_participant_count', %s, 0)
            ON DUPLICATE KEY UPDATE counts = VALUES(counts);
        """, (unique_count,))

        logger.info("Statistics table updated.")
    except Exception as e:
        logger.error(f"Error updating statistics: {e}")
    finally:
        cursor.close()
        conn.close()


@task
def notify_completion(message: str, subject: str = "ETL Job Completed"):
    sns = boto3.client("sns", region_name="us-east-1")
    try:
        sns.publish(
            TopicArn="arn:aws:sns:us-east-1:893214465464:etl-notification",
            Message=message,
            Subject=subject
        )
        logger.info("Notification sent to SNS.")
    except Exception as e:
        logger.error(f"Failed to send SNS notification: {e}")


@flow(name="etl")
def main():
    notify_completion("main.py has started.")
    raw = read_data_from_db()
    graph = get_relationships(raw)
    output = format_output(graph)

    json_file = "test-output.json"
    write_json_file(output, json_file)
    upload_to_s3(json_file, "ccdi-nonprod-cpi-source-data", "json-file/")
    update_participants_from_json(json_file)
    update_statistics()
    notify_completion("main.py has completed successfully.")

if __name__ == "__main__":
    main()
