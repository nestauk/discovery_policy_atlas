import asyncio
from app.core.database import AsyncSessionLocal
from app.models.database import Project
from sqlalchemy import select


async def test_db():
    async with AsyncSessionLocal() as session:
        # Create a test project
        project = Project(
            clerk_user_id="test_user_123",
            name="Test Search Project",
            description="Testing database connection",
            query="test query",
            filters={"year_range": [2020, 2024]},
        )
        session.add(project)
        await session.commit()

        # Query it back
        result = await session.execute(
            select(Project).where(Project.clerk_user_id == "test_user_123")
        )
        projects = result.scalars().all()
        print(f"Found {len(projects)} projects")
        for p in projects:
            print(f"- {p.name}: {p.description}")
            print(f"  Query: {p.query}")
            print(f"  Filters: {p.filters}")


if __name__ == "__main__":
    asyncio.run(test_db())
