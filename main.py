from TextToSQLEngine import TTSQL_pipeline
from llm_as_a_Judge import judgement_pipeline #needs work on judgement pipeline
from fastapi import FastAPI
from schema_extraction_module import extract_schema
from pydantic import BaseModel
app=FastAPI()

class user_query(BaseModel):
    query: str

query_results={} #temporary storage for query results

@app.get("/generate_sql_query")
def generate_sql_query(query:user_query):
    global query_results
    user_query=query.query
    data=TTSQL_pipeline(user_query)
    query_results=data
    return {
        "generated_sql_query": data['generated_sql_query']
    }

@app.get("/get_reasoning")
def get_reasoning():
    return {
        "reasoning":query_results['reasoning']
    }

@app.get("/get_results")
def get_results():
    return {
        "results":query_results['results']
    }

@app.get("/get_judgement")
def get_judgement(query_results["user_query"]):
    judgement=

