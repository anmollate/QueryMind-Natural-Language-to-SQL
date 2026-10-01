from TextToSQLEngine import get_sqlquery, get_results, TTSQL_pipeline
from schema_extraction_module import extract_schema
from langchain_huggingface import HuggingFaceEndpoint, ChatHuggingFace
from dotenv import load_dotenv
import json
import os


load_dotenv()
HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")

def parse_judgement(raw_text):
    if raw_text is None or raw_text.strip() == "":
        raise ValueError("Judge returned an empty response (likely hit the token limit).")

    text = raw_text

    # Drop the reasoning block if the model included one
    think_end = text.find("</think>")
    if think_end != -1:
        text = text[think_end + len("</think>"):]

    # Keep only the part from the first { to the last }
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found in judge response: " + repr(raw_text[:200]))

    json_text = text[start:end + 1]
    return json.loads(json_text)


def get_llm_judgement(user_query,schema,sql_query,results):
    llm = HuggingFaceEndpoint(
        repo_id="deepseek-ai/DeepSeek-V4-Pro-0813",
        task="text-generation",
        huggingfacehub_api_token=HUGGINGFACE_API_KEY,
        temperature=0.1,      # low temp — the judge should give consistent scores
        max_new_tokens=4096   # default is 512, which a reasoning model can use up on thinking alone
        )

    model = ChatHuggingFace(llm=llm)

    judge_prompt = f"""
    You are an expert SQL evaluator for a Text-to-SQL system.

    Your task is to evaluate whether the GENERATED SQL correctly answers
    the USER QUERY using only the provided DATABASE SCHEMA.

    USER QUERY:
    {user_query}

    DATABASE SCHEMA:
    {schema}

    GENERATED SQL:
    {sql_query}

    GENERATED SQL RESULTS:
    {results}



    Evaluate the generated SQL on the following criteria:

    1. SQL_VALIDITY
    - Is the SQL syntactically valid?
    - Can it reasonably be executed against the provided schema?

    2. SCHEMA_CORRECTNESS
    - Does it use valid tables and columns from the schema?
    - Are joins and relationships between tables used correctly?

    3. SEMANTIC_CORRECTNESS
    - Does the SQL correctly represent what the user asked?
    - Does it retrieve, filter, aggregate, sort, or group the data
        according to the user's intent?

    4. OVERALL_CORRECTNESS
    - Considering all the above factors, is the generated SQL a
        correct answer to the user's query?

    Use the following scoring system:

    0 = Incorrect
    1 = Partially correct
    2 = Correct

    Return ONLY valid JSON in exactly this format:

    {{
        "sql_validity": {{
            "score": 0,
            "reason": ""
        }},
        "schema_correctness": {{
            "score": 0,
            "reason": ""
        }},
        "semantic_correctness": {{
            "score": 0,
            "reason": ""
        }},
        "overall_correctness": {{
            "score": 0,
            "reason": ""
        }},
        "final_verdict": "PASS"
    }}

    Rules for final_verdict:
    - PASS only if the generated SQL correctly answers the user query.
    - FAIL if the SQL is incorrect or does not fully satisfy the query.
    - Do not judge based on formatting or SQL style.
    - Do not assume columns or tables that are not present in the schema.
    - Do not invent missing information.
    - Base your evaluation strictly on the USER QUERY, DATABASE SCHEMA,
    and GENERATED SQL.
    -Return ONLY valid JSON.
    -Do not use markdown code blocks.
    -Do not use single quotes.
    -Use double quotes for all keys and string values.
    """

    last_error = None

    for attempt in range(2):
        judgement = model.invoke(judge_prompt)
        print("JUDGE RAW RESPONSE:")
        print(repr(judgement.content))
        print("RESPONSE METADATA:")
        print(judgement.response_metadata)
        try:
            return parse_judgement(judgement.content)
        except ValueError as error:   # JSONDecodeError is a subclass of ValueError
            last_error = error
            print("Judge attempt", attempt + 1, "failed:", error)

    raise RuntimeError("Judge failed after 2 attempts: " + str(last_error))

# def judgement_pipeline(): #needs work
#     # user_query=input("Enter your query: ")
#     # schema=extract_schema()
#     # sql_query=get_sqlquery(user_query, schema)
#     # results=get_results(sql_query)
#     # judgement=get_judgement(user_query, schema, sql_query, results)
#     # print("User Query:", user_query)
#     # print("Database Schema:", schema)
#     # print("Generated SQL Query:", sql_query)
#     # print("SQL Query Results:", results)
#     # print("Judgement:", judgement)
#     # return {
#     #     "User Query": user_query,
#     #     "Database Schema": schema,
#     #     "Generated SQL Query": sql_query,
#     #     "SQL Query Results": results,
#     #     "Judgement": judgement
#     # }
#     data = TTSQL_pipeline() #this would cause break it has been updated get parameter
#     user_query = data['user_query']
#     schema = data['database_schema']
#     sql_query = data['generated_sql_query']
#     results = data['results']
#     judgement = get_judgement(user_query, schema, sql_query, results)
#     print("User Query:", user_query)
#     # print("Database Schema:", schema)
#     print("Generated SQL Query:", sql_query)
#     print("SQL Query Results:", results)
#     print("Judgement:", judgement)



if __name__ == "__main__":
    schema="""
    Table: credit_card_transactions
    Columns:
    - credit_transaction_id: bigint
    - customer_id: bigint
    - transaction_date: timestamp without time zone
    - amount: numeric
    - merchant_name: character varying
    - card_network: character varying
    - card_type: character varying
    - transaction_status: character varying
    - credit_limit: numeric

    Table: customers
    Columns:
    - customer_id: bigint
    - full_name: character varying
    - email: character varying
    - phone: character varying
    - city: character varying
    - state: character varying
    - registration_date: date

    Table: debit_card_transactions
    Columns:
    - debit_transaction_id: bigint
    - customer_id: bigint
    - transaction_date: timestamp without time zone
    - amount: numeric
    - merchant_name: character varying
    - card_network: character varying
    - account_type: character varying
    - transaction_status: character varying
    - transaction_type: character varying

    Table: upi_transactions
    Columns:
    - upi_transaction_id: bigint
    - customer_id: bigint
    - transaction_date: timestamp without time zone
    - amount: numeric
    - merchant_name: character varying
    - upi_app: character varying
    - transaction_status: character varying
    - transaction_type: character varying

"""
    result1=get_llm_judgement("select the total number of customers",schema,"select count(*) from customers;",100)



