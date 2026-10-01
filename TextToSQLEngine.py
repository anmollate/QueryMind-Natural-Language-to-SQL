from langchain_huggingface import HuggingFaceEndpoint, ChatHuggingFace
from schema_extraction_module import extract_schema
from urllib.parse import quote_plus
from dotenv import load_dotenv
import psycopg2
import os
import json
import ast

load_dotenv()

HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")



def parse_sql_response(raw_text):
    if raw_text is None or raw_text.strip() == "":
        raise ValueError("Model returned an empty response (or both models failed).")

    text = raw_text

    # Drop the reasoning block if the model included one
    think_end = text.find("</think>")
    if think_end != -1:
        text = text[think_end + len("</think>"):]

    # Keep only the part from the first { to the last }
    # (this also removes ```json fences and any text around the JSON)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found in model response: " + repr(raw_text[:200]))

    json_text = text[start:end + 1]

    try:
        # strict=False allows raw newlines inside string values (common in multi-line SQL)
        parsed = json.loads(json_text, strict=False)
    except json.JSONDecodeError:
        # Fallback: the model may have returned a Python-style dict with single quotes
        try:
            parsed = ast.literal_eval(json_text)
        except (ValueError, SyntaxError):
            raise ValueError("Could not parse model response: " + repr(raw_text[:200]))

    if not isinstance(parsed, dict) or "query" not in parsed:
        raise ValueError("Model response has no 'query' field: " + repr(raw_text[:200]))

    if "reasoning" not in parsed:
        parsed["reasoning"] = ""

    return parsed


def get_sqlquery(query,schema):
    llm1 = HuggingFaceEndpoint(
        repo_id="XGenerationLab/XiYanSQL-QwenCoder-32B-2504",
        task="text-generation",
        huggingfacehub_api_token=HUGGINGFACE_API_KEY,
        temperature=0.1,       # low temp — you want deterministic SQL, not creative variation
        max_new_tokens=2048,   # default is 512, which can cut long answers off
    )

    llm2 = HuggingFaceEndpoint(
        repo_id="Qwen/Qwen2.5-Coder-32B-Instruct",   # was missing the "Qwen/" org prefix
        task="text-generation",
        huggingfacehub_api_token=HUGGINGFACE_API_KEY,
        temperature=0.1,
        max_new_tokens=2048,
    )

    model1 = ChatHuggingFace(llm=llm1)
    model2 = ChatHuggingFace(llm=llm2)

    prompt1 = f"""
    You are an expert SQL developer specializing in PostgreSQL.

    Your task is to convert the user's natural language question into a single,
    correct SQL query using ONLY the database schema provided below.

    ### DATABASE SCHEMA
    {schema}

    ### USER QUESTION
    {query}

    ### INSTRUCTIONS

    1. Generate exactly one SQL query that answers the user's question.

    2. Use ONLY the tables and columns present in the provided database schema.
    Never invent, assume, or create table or column names.

    3. Use PostgreSQL syntax and SQL conventions.

    4. When multiple tables are required:
    - Use explicit JOIN statements.
    - Do not use comma-separated joins.
    - Use table names or aliases to qualify columns where necessary.

    5. Use appropriate SQL clauses such as:
    SELECT, FROM, JOIN, WHERE, GROUP BY, HAVING, ORDER BY, and LIMIT
    according to the user's question.

    6. Use LIMIT only when the user explicitly asks for a limited number of
    results, such as "top 5", "first 10", or "latest 20".

    7. If the question cannot be answered using the provided schema, do not
    generate a SQL query. Instead, set the "query" field to:
    "-- CANNOT_ANSWER"
    and explain the reason in the "reasoning" field.

    8. If the question is ambiguous, identify the ambiguity in the "reasoning"
    field and set the "query" field to:
    "-- CANNOT_ANSWER"

    9. The reasoning should briefly explain:
    - Which tables and columns were selected.
    - How they relate to the user's question.
    - Any JOIN, filtering, grouping, or ordering logic used.
    Do not provide unnecessary or unrelated information.

    10. Return the response ONLY as valid JSON.

    11. Do not use Markdown code fences.

    12. Do not add any text before or after the JSON object.

    ### REQUIRED OUTPUT FORMAT

    {{
        "query": "<generated PostgreSQL SQL query>",
        "reasoning": "<brief explanation of how the query was constructed>"
    }}
    """

    try:
        result1 = model1.invoke(prompt1)
        sql_query = result1.content
        print("SQL Generation Successful ✅")
        return sql_query
    except Exception as e:
        print(f"Model 1 inference failed {e}, trying Model 2...")

    try:
        result1 = model2.invoke(prompt1)
        sql_query = result1.content
        print("SQL Generation Successful ✅")
        return sql_query
    except Exception as e:
        print(f"Model 2 inference failed {e}")
        return None


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

def TTSQL_pipeline(user_query):
    try:
        schema = extract_schema()
    except Exception as e:
        print(f"Schema extraction failed: {e}")
        schema = None

    try:
        sql_query = get_sqlquery(user_query, schema)
        print("SQL GEN RAW RESPONSE:", repr(sql_query))
        sql_query_dict = parse_sql_response(sql_query)
        print("Generated SQL Query:", sql_query_dict['query'])
        print("Reasoning:", sql_query_dict['reasoning'])
    except Exception as e:
        print(f"SQL generation failed: {e}")
        return {
            "user_query": user_query,
            "database_schema": schema,
            "generated_sql_query": None,
            "reasoning": None,
            "results": None,
            "error": f"SQL generation failed: {e}",
        }

    # The prompt tells the model to return "-- CANNOT_ANSWER" when the schema can't answer the question
    if sql_query_dict['query'].strip().startswith("-- CANNOT_ANSWER"):
        print("Model could not answer:", sql_query_dict['reasoning'])
        return {
            "user_query": user_query,
            "database_schema": schema,
            "generated_sql_query": sql_query_dict['query'],
            "reasoning": sql_query_dict['reasoning'],
            "results": None,
            "error": "This question cannot be answered with the available schema: " + str(sql_query_dict['reasoning']),
        }

    try:
        results = get_results(sql_query_dict['query'])
        print(results)
    except Exception as e:
        print(f"Query execution failed: {e}")
        return {
            "user_query": user_query,
            "database_schema": schema,
            "generated_sql_query": sql_query_dict['query'],
            "reasoning": sql_query_dict['reasoning'],
            "results": None,
            "error": f"Failed to execute query: {e}",
        }

    return {
        "user_query": user_query,
        "database_schema": schema,
        "generated_sql_query": sql_query_dict['query'],
        "reasoning": sql_query_dict['reasoning'],
        "results": results,
        "error": None,
    }



if __name__ == "__main__":
    TTSQL_pipeline()




