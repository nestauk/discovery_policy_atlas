from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import httpx
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI(title="Policy Atlas API", version="0.1.0")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Your Next.js frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request/Response models
class SearchRequest(BaseModel):
    query: str
    per_page: Optional[int] = 3
    
class Author(BaseModel):
    author_position: str
    author: dict

class Paper(BaseModel):
    id: str
    title: str
    publication_year: Optional[int]
    cited_by_count: int
    doi: Optional[str]
    abstract: Optional[str]
    authors: List[Author]
    primary_location: Optional[dict]

class SearchResponse(BaseModel):
    results: List[dict]
    total_count: int
    query: str

# OpenAlex configuration
OPENALEX_API_URL = "https://api.openalex.org"
OPENALEX_EMAIL = os.getenv("OPENALEX_EMAIL")  # Optional but recommended

@app.get("/")
async def root():
    return {"message": "Policy Atlas API", "status": "running"}

@app.post("/api/search", response_model=SearchResponse)
async def search_papers(request: SearchRequest):
    """
    Search for academic papers using OpenAlex API
    """
    try:
        async with httpx.AsyncClient() as client:
            # Build request parameters
            params = {
                "search": request.query,
                "per_page": request.per_page,
                "sort": "cited_by_count:desc",  # Sort by most cited
            }
            
            # Add email if provided (OpenAlex asks for this for politeness)
            if OPENALEX_EMAIL:
                params["mailto"] = OPENALEX_EMAIL
            
            # Make request to OpenAlex
            response = await client.get(
                f"{OPENALEX_API_URL}/works",
                params=params,
                timeout=30.0
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"OpenAlex API error: {response.text}"
                )
            
            data = response.json()
            
            # Extract and format results
            results = data.get("results", [])
            total_count = data.get("meta", {}).get("count", 0)
            
            return SearchResponse(
                results=results,
                total_count=total_count,
                query=request.query
            )
            
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="OpenAlex API timeout")
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Network error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

@app.get("/api/health")
async def health_check():
    """
    Health check endpoint
    """
    try:
        # Test OpenAlex connection
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{OPENALEX_API_URL}/works",
                params={"per_page": 1},
                timeout=5.0
            )
            openalex_status = "healthy" if response.status_code == 200 else "unhealthy"
    except:
        openalex_status = "unhealthy"
    
    return {
        "status": "healthy",
        "openalex": openalex_status
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)