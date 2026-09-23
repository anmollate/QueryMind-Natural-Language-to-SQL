from TextToSQLEngine import TTSQL_pipeline
from llm_as_a_Judge import get_llm_judgement #needs work on judgement pipeline
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles  
from schema_extraction_module import extract_schema
from pydantic import BaseModel
app=FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class user_query(BaseModel):
    query: str

query_results={} #temporary storage for query results


@app.post("/generate_sql_query")
def generate_sql_query(query:user_query):
    global query_results
    user_query=query.query
    data=TTSQL_pipeline(user_query)
    query_results=data
    return {
        "generated_sql_query": data['generated_sql_query']
    }

#endpoint to get the reasoning for generated sql query
@app.get("/get_reasoning")
def get_reasoning():
    return {
        "reasoning":query_results['reasoning']
    }

#endpoint to get the results of the generated sql query
@app.get("/get_results")
def get_results():
    return {
        "results":query_results['results']
    }

#endpoint to get the judgement of the judge llm on the generated query
@app.get("/get_judgement")
def get_judgement():
    judgement=get_llm_judgement(query_results["user_query"],query_results["database_schema"],query_results["generated_sql_query"],query_results["results"])
    return {
        "sql_validity_score":judgement["sql_validity"]["score"],
        "sql_validity_reason":judgement["sql_validity"]["reason"],
        "schema_correctness_score":judgement["schema_correctness"]["score"],
        "schema_correctness_reason":judgement["schema_correctness"]["reason"],
        "semantic_correctness_score":judgement["semantic_correctness"]["score"],
        "semantic_correctness_reason":judgement["semantic_correctness"]["reason"],
        "overall_correctness_score":judgement["overall_correctness"]["score"],
        "overall_correctness_reason":judgement["overall_correctness"]["reason"],
        "final_verdict":judgement["final_verdict"]
    }


app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

