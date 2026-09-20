from urllib.parse import quote_plus
from dotenv import load_dotenv
import psycopg2
import os

load_dotenv()

password = os.getenv("database_password")
URLPART1 = os.getenv("URLPART1")
URLPART2 = os.getenv("URLPART2")

DATABASE_URL = (
    URLPART1
    + quote_plus(password)
    + URLPART2
)

def get_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        print("Database connection successful ✅")
        return conn
    except Exception as e:
        print(f"Database connection failed: {e}")
        return None

def extract_schema():
    conn = get_connection()
    cursor = conn.cursor()
    try:
        query = """
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position;
        """
        cursor.execute(query)
        schema = cursor.fetchall()

        schema_text = ""
        current_table = None
        for table, column, data_type in schema:
            if table != current_table:
                schema_text += f"\nTable: {table}\nColumns:\n"
                current_table = table
            schema_text += f"- {column}: {data_type}\n"

        return schema_text
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    schema = extract_schema()
    print("Database schema extracted successfully ✅")
    print(schema)


