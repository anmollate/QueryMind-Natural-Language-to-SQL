from langchain_huggingface import HuggingFaceEndpoint, ChatHuggingFace
from schema_extraction_module import extract_schema
from urllib.parse import quote_plus
from dotenv import load_dotenv
import psycopg2
import os

load_dotenv()

HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")



def get_sqlquery(query,schema):
    llm = HuggingFaceEndpoint(
        repo_id="XGenerationLab/XiYanSQL-QwenCoder-7B-2504",
        task="text-generation",
        provider="featherless-ai",
        huggingfacehub_api_token=HUGGINGFACE_API_KEY,
        temperature=0.1,   # low temp — you want deterministic SQL, not creative variation
    )

    model = ChatHuggingFace(llm=llm)

    prompt1 = f"""
    You are an expert SQL developer. Convert the user's natural language question into a single, correct SQL query based only on the database schema provided below.

    ### Database Schema
    {schema}

    ### Rules
    1. Only use tables and columns that exist in the schema above. Never invent column or table names.
    2. Use explicit JOINs (not comma joins), and qualify column names with table names/aliases when more than one table is involved.
    3. Use the exact SQL dialect: PostgreSQL.
    4. If the question is ambiguous or cannot be answered from the schema, respond with: -- CANNOT_ANSWER: <short reason>
    5. Do not include explanations, comments, or markdown formatting — output only the raw SQL query.
    6. Prefer readable formatting: one clause per line (SELECT, FROM, WHERE, GROUP BY, ORDER BY).
    7. Use LIMIT only if the user asks for "top N" / "first N" results.

    ### User Question
    {query}

    ### SQL Query
    """

    try:
        result1 = model.invoke(prompt1)
        sql_query = result1.content
        print("SQL Generation Successful ✅")
        return sql_query
    except Exception as e:
        print(f"Inference call failed: {e}")
        sql_query = None

def get_results(sql_query):
    password = os.getenv("database_password")
    DATABASE_URL = (
    "postgresql://postgres.amrrjlszfkjmsgxdwbqc:"
    + quote_plus(password)
    + "@aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres"
    )

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute(sql_query)
    results = cursor.fetchall()
    conn.close()
    print("Query executed successfully ✅")
    return results


if __name__ == "__main__":
    user_query = input("Enter your query (user query):")
    schema = extract_schema()
    sql_query=get_sqlquery(user_query,schema)
    results=get_results(sql_query)
    print(sql_query)
    print(results)



