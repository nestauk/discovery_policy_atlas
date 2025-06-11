"""Quick test script for the API"""
import asyncio
import httpx


async def test_search():
    async with httpx.AsyncClient() as client:
        # Test the search endpoint
        response = await client.post(
            "http://localhost:8000/api/search",
            json={"query": "climate change policy", "per_page": 3},
        )

        print(f"Status: {response.status_code}")
        data = response.json()
        print(f"Found {data['total_count']} total results")
        print(f"Returning {len(data['results'])} results")

        for i, paper in enumerate(data["results"], 1):
            print(f"\n{i}. {paper['title']}")
            print(f"   Year: {paper.get('publication_year', 'N/A')}")
            print(f"   Citations: {paper['cited_by_count']}")


if __name__ == "__main__":
    asyncio.run(test_search())
