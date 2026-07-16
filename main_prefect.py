import json
import os
import re
import networkx as nx
import pymysql
from datetime import datetime
from zoneinfo import ZoneInfo
import boto3

from prefect import flow, task, get_run_logger

DB_SECRET_NAME = os.getenv("DB_SECRET_NAME", "ccdi-dev-cpi-mysql")
SNS_TOPIC_ARN  = os.getenv("SNS_TOPIC_ARN",  "arn:aws:sns:us-east-1:893214465464:etl-notification")
S3_BUCKET      = os.getenv("S3_BUCKET",      "ccdi-nonprod-cpi-source-data")

_VERSION_PATTERN = re.compile(r"^v(?P<major>\d+)\.(?P<minor>\d+)$")


def _increment_version(current_version: str) -> str:
    match = _VERSION_PATTERN.match(current_version.strip())
    if match:
        major = match.group("major")
        minor = int(match.group("minor")) + 1
        return f"v{major}.{minor}"
    return "v1.0"


def get_mysql_credentials(secret_name: str, region_name: str = "us-east-1") -> dict:
    from botocore.exceptions import ClientError
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


# ── Prefect tasks ─────────────────────────────────────────────────────────────

@task(name="notify", retries=2, retry_delay_seconds=10)
def notify_completion(message: str, subject: str = "ETL Job Completed"):
    logger = get_run_logger()
    sns = boto3.client("sns", region_name="us-east-1")
    try:
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Message=message,
            Subject=subject,
        )
        logger.info("Notification sent to SNS.")
    except Exception as e:
        logger.error(f"Failed to send SNS notification: {e}")


@task(name="read_data_from_db", retries=3, retry_delay_seconds=30)
def read_data_from_db() -> list:
    logger = get_run_logger()
    result = []
    connection = None
    try:
        creds = get_mysql_credentials(DB_SECRET_NAME)
        connection = pymysql.connect(
            host=creds["host"],
            user=creds["user_name"],
            password=creds["password"],
            database="cpi",
            cursorclass=pymysql.cursors.DictCursor,
        )
        with connection.cursor() as cursor:
            query = (
                "SELECT `participant_id1` AS p1, `domain_name1` AS d1, "
                "`participant_id2` AS p2, `domain_name2` AS d2 FROM `mapping`"
            )
            cursor.execute(query)
            result = cursor.fetchall()
        logger.info(f"Read {len(result)} rows from DB.")
    except pymysql.MySQLError as err:
        logger.error(f"DB error: {err}")
        raise
    finally:
        if connection:
            connection.close()
    return result


@task(name="get_relationships")
def get_relationships(uids: list) -> dict:
    logger = get_run_logger()
    G = nx.Graph()
    for i in uids:
        G.add_edge(i["p1"] + "::" + i["d1"], i["p2"] + "::" + i["d2"])
    graph = dict(nx.all_pairs_shortest_path(G))
    logger.info(f"Built graph with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")
    return graph


@task(name="format_output")
def format_output(graph: dict) -> list:
    unique_linked_sets = set()
    for _, relationships in graph.items():
        related = list(relationships.keys())
        related.sort()
        unique_linked_sets.add(tuple(related))
    return [{"related": list(set_)} for set_ in unique_linked_sets]


@task(name="write_json_file")
def write_json_file(data: list, filename: str):
    logger = get_run_logger()
    with open(filename, "w") as file:
        json.dump(data, file, indent=4)
    logger.info(f"Written output to {filename}.")


@task(name="upload_to_s3", retries=3, retry_delay_seconds=30)
def upload_to_s3(file_path: str, bucket: str, prefix: str):
    logger = get_run_logger()
    s3 = boto3.client("s3")
    today = datetime.today().strftime("%Y-%m-%d")
    key = f"{prefix}{today}.json"
    s3.upload_file(file_path, bucket, key)
    logger.info(f"Uploaded to s3://{bucket}/{key}")


@task(name="update_participants_from_json", retries=2, retry_delay_seconds=30)
def update_participants_from_json(json_file: str):
    logger = get_run_logger()
    creds = get_mysql_credentials(DB_SECRET_NAME)
    conn = pymysql.connect(
        host=creds["host"],
        user=creds["user_name"],
        password=creds["password"],
        database="cpi",
        autocommit=True,
    )
    cursor = conn.cursor()
    try:
        cursor.execute("DROP TEMPORARY TABLE IF EXISTS cpi.temp_alternatives")
        cursor.execute("""
            CREATE TEMPORARY TABLE cpi.temp_alternatives (
                id VARCHAR(255),
                alternative_participants TEXT
            )
        """)

        with open(json_file, "r", encoding="utf-8-sig") as file:
            data = json.load(file)

        insert_query = "INSERT INTO cpi.temp_alternatives (id, alternative_participants) VALUES (%s, %s)"
        insert_values = []
        for item in data:
            linked_nodes = item["related"]
            my_string = ", ".join(linked_nodes)
            for node_id in linked_nodes:
                insert_values.append((node_id, my_string))

        cursor.executemany(insert_query, insert_values)
        conn.commit()
        logger.info(f"Inserted {len(insert_values)} rows into temp table.")

        cursor.execute(
            "UPDATE cpi.participant SET alternative_participants = NULL WHERE alternative_participants IS NOT NULL"
        )
        conn.commit()
        logger.info("Reset all alternative_participants to null.")

        update_query = """
            UPDATE cpi.participant p
            JOIN cpi.temp_alternatives t ON p.id COLLATE utf8mb4_general_ci = t.id
            SET p.alternative_participants = t.alternative_participants
        """
        cursor.execute(update_query)
        conn.commit()
        logger.info("Bulk update of alternative_participants completed.")
    except Exception as e:
        logger.error(f"Error in update_participants_from_json: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


@task(name="update_statistics", retries=2, retry_delay_seconds=30)
def update_statistics():
    logger = get_run_logger()
    creds = get_mysql_credentials(DB_SECRET_NAME)
    conn = pymysql.connect(
        host=creds["host"],
        user=creds["user_name"],
        password=creds["password"],
        database="cpi",
        autocommit=True,
    )
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = 'cpi' AND TABLE_NAME = 'domain_counts';
            """
        )
        domain_counts_columns = {row[0] for row in cursor.fetchall()}
        use_version_id = "version_id" in domain_counts_columns
        use_version_column = "version" in domain_counts_columns

        if not use_version_id and not use_version_column:
            raise Exception("domain_counts table is missing a version or version_id column.")

        cursor.execute(
            "SELECT version FROM cpi.version ORDER BY version_id DESC LIMIT 1;"
        )
        latest_version_row = cursor.fetchone()
        new_version = (
            _increment_version(latest_version_row[0])
            if latest_version_row and latest_version_row[0]
            else "v1.0"
        )

        est_timestamp = datetime.utcnow().astimezone(ZoneInfo("America/New_York")).replace(tzinfo=None)
        cursor.execute(
            "INSERT INTO cpi.version (version, version_time) VALUES (%s, %s);",
            (new_version, est_timestamp),
        )
        new_version_id = cursor.lastrowid
        logger.info("Recorded version %s at %s Eastern.", new_version, est_timestamp)

        cursor.execute("""
            SELECT p.domain_name, COUNT(*) as counts
            FROM cpi.participant p
            JOIN cpi.domain d ON p.domain_name = d.domain_name
            WHERE d.is_private = 0
            GROUP BY p.domain_name;
        """)
        current_counts = cursor.fetchall()

        if use_version_id:
            insert_domain_counts = (
                "INSERT INTO cpi.domain_counts (domain_name, counts, version_id, diff) VALUES (%s, %s, %s, %s);"
            )
        else:
            insert_domain_counts = (
                "INSERT INTO cpi.domain_counts (domain_name, counts, version, diff) VALUES (%s, %s, %s, %s);"
            )

        for domain_name, counts in current_counts:
            cursor.execute(
                "SELECT counts FROM cpi.domain_counts WHERE domain_name = %s ORDER BY domain_count_id DESC LIMIT 1;",
                (domain_name,),
            )
            prev_result = cursor.fetchone()
            prev_count = prev_result[0] if prev_result else 0
            diff = counts - prev_count
            cursor.execute(
                insert_domain_counts,
                (domain_name, counts, new_version_id if use_version_id else new_version, diff),
            )

        logger.info("Domain counts updated.")

        cursor.execute("SELECT COUNT(*) FROM cpi.mapping;")
        mapped_count = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO cpi.statistic (counts_name, counts) VALUES ('mapped_participant_count', %s) "
            "ON DUPLICATE KEY UPDATE counts = VALUES(counts);",
            (mapped_count,),
        )

        cursor.execute(
            "SELECT COUNT(DISTINCT alternative_participants) FROM cpi.participant WHERE alternative_participants IS NOT NULL;"
        )
        distinct_alternative_count = cursor.fetchone()[0]
        cursor.execute(
            "SELECT COUNT(*) FROM cpi.participant WHERE alternative_participants IS NULL;"
        )
        null_alternative_count = cursor.fetchone()[0]
        unique_count = distinct_alternative_count + null_alternative_count
        cursor.execute(
            "INSERT INTO cpi.statistic (counts_name, counts) VALUES ('unique_participant_count', %s) "
            "ON DUPLICATE KEY UPDATE counts = VALUES(counts);",
            (unique_count,),
        )

        cursor.execute("""
            SELECT dataset_count, COUNT(*) as num_participants
            FROM (
                SELECT p.alternative_participants, COUNT(DISTINCT p.domain_name) as dataset_count
                FROM cpi.participant p
                JOIN cpi.domain d ON p.domain_name = d.domain_name
                WHERE p.alternative_participants IS NOT NULL AND d.domain_category = 'dataset'
                GROUP BY p.alternative_participants
            ) subquery
            GROUP BY dataset_count ORDER BY dataset_count;
        """)
        for dataset_count, num_participants in cursor.fetchall():
            if dataset_count >= 2:
                counts_name = f"unique_participants_{dataset_count}_dataset"
                cursor.execute(
                    "INSERT INTO cpi.statistic (counts_name, counts) VALUES (%s, %s) "
                    "ON DUPLICATE KEY UPDATE counts = VALUES(counts);",
                    (counts_name, num_participants),
                )
                logger.info(f"Inserted/Updated {counts_name}: {num_participants}")

        logger.info("Statistics table updated.")
    except Exception as e:
        logger.error(f"Error updating statistics: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


# ── Prefect flow ──────────────────────────────────────────────────────────────

@flow(name="cpi-etl-pipeline", log_prints=True)
def cpi_etl_pipeline():
    """CPI ETL: read DB → build graph → write JSON → S3 → update DB → statistics."""
    json_file = "output.json"

    notify_completion("ETL job main_prefect.py has started.", subject="ETL Job Started")

    raw = read_data_from_db()
    graph = get_relationships(raw)
    output = format_output(graph)
    write_json_file(output, json_file)
    upload_to_s3(json_file, S3_BUCKET, "json-file/")
    update_participants_from_json(json_file)
    update_statistics()

    notify_completion("ETL job main_prefect.py has completed successfully.", subject="ETL Job Completed")


if __name__ == "__main__":
    cpi_etl_pipeline()
