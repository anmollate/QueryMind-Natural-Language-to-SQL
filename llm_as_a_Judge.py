from TextToSQLEngine import get_userquery, get_sqlquery, get_results
from schema_extraction_module import extract_schema
from langchain_huggingface import HuggingFaceEndpoint, ChatHuggingFace
from dotenv import load_dotenv
import os


load_dotenv()
HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")

llm = HuggingFaceEndpoint(
    repo_id="Qwen/Qwen3-32B",
    task="text-generation",
    huggingfacehub_api_token=HUGGINGFACE_API_KEY,
    temperature=0.1,   # low temp — you want deterministic SQL, not creative variation
    )

model = ChatHuggingFace(llm=llm)

judge_prompt = f"""
You are an expert SQL evaluator for a Text-to-SQL system.

Your task is to evaluate whether the GENERATED SQL correctly answers
the USER QUERY using only the provided DATABASE SCHEMA.

USER QUERY:
{get_userquery()}

DATABASE SCHEMA:
{extract_schema()}

GENERATED SQL:
{get_sqlquery()}

GENERATED SQL RESULTS:
{get_results()}

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
"""

judgement=model.invoke(judge_prompt)

print(judgement.content)