import psycopg2
from urllib.parse import quote_plus
from dotenv import load_dotenv
import os

load_dotenv()

password = os.getenv("database_password")

DATABASE_URL = (
    "postgresql://postgres.amrrjlszfkjmsgxdwbqc:"
    + quote_plus(password)
    + "@aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres"
)

try:
    conn=psycopg2.connect(DATABASE_URL)
    print("Connection Successful ✅")
except Exception as e:
    print(f"Error connecting to the database: {e}")

def extract_schema():
    #Query To Extract Schema Information From The Database
    query = """
    SELECT
        table_name,
        column_name,
        data_type
    FROM information_schema.columns
    WHERE table_schema = 'public'
    ORDER BY table_name, ordinal_position;
    """

    #Executing The Query And Fetching The Results
    cursor = conn.cursor()
    cursor.execute(query)
    schema = cursor.fetchall()

    schema_text = ""

    current_table = None

    for table, column, data_type in schema:

        if table != current_table:
            schema_text += f"\nTable: {table}\n"
            schema_text += "Columns:\n"
            current_table = table

        schema_text += f"- {column}: {data_type}\n"
    print("Schema Extraction Successful ✅")
    return schema_text




