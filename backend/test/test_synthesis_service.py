"""
Test script for Synthesis service with monitoring.

Tests the full synthesis pipeline for a specific project, including:
- Async LLM calls (invoke -> ainvoke conversion)
- Resource monitoring
- Performance profiling

Usage:
    python test_synthesis_service.py <project_id>
    
Example:
    python test_synthesis_service.py abc123def456
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add backend to path before app imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.synthesis.service import SynthesisService  # noqa: E402
from app.services.monitoring import ResourceMonitor, StageTimer  # noqa: E402

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def test_synthesis_for_project(project_id: str, force_regenerate: bool = True):
    """
    Test synthesis service for a specific project with monitoring.

    Args:
        project_id: The analysis project ID to synthesize
        force_regenerate: If True, delete existing synthesis runs before generating new one
    """
    logger.info("=" * 60)
    logger.info("SYNTHESIS SERVICE TEST")
    logger.info("=" * 60)
    logger.info(f"Project ID: {project_id}")

    # Initialize monitoring
    monitor = ResourceMonitor(f"SynthesisTest-{project_id}")
    monitor.start()
    monitor.log_snapshot("Test start")

    try:
        # Delete existing synthesis runs if requested
        if force_regenerate:
            from app.services.vectorization import vectorization_service

            logger.info("Deleting existing synthesis runs...")
            try:
                result = (
                    vectorization_service.supabase.table("synthesis_runs")
                    .delete()
                    .eq("analysis_project_id", project_id)
                    .execute()
                )
                deleted_count = len(result.data) if result.data else 0
                logger.info(f"Deleted {deleted_count} existing synthesis run(s)")
            except Exception as e:
                logger.warning(f"Failed to delete existing runs: {e}")

        # Initialize synthesis service
        service = SynthesisService()

        # Run synthesis with monitoring
        with StageTimer(monitor, "full_synthesis"):
            logger.info("\nStarting synthesis...")
            result = await service.summarise(project_id)

        monitor.log_snapshot("Synthesis complete")

        # Display results
        logger.info("\n" + "=" * 60)
        logger.info("SYNTHESIS RESULTS")
        logger.info("=" * 60)

        logger.info(f"\n📊 Key Issues: {len(result.key_issues)}")
        for i, issue in enumerate(result.key_issues[:5], 1):
            logger.info(f"  {i}. {issue.issue_theme} (frequency: {issue.frequency})")
            logger.info(f"     {issue.summary_description[:100]}...")

        logger.info(f"\n🎯 Interventions: {len(result.interventions)}")
        for i, intervention in enumerate(result.interventions[:5], 1):
            logger.info(f"  {i}. {intervention.intervention_name}")
            logger.info(f"     {intervention.brief_description[:100]}...")

        logger.info("\n📝 Executive Briefing:")
        logger.info(f"{result.executive_briefing}")

        # Record metrics
        monitor.record_metric("key_issues_count", len(result.key_issues))
        monitor.record_metric("interventions_count", len(result.interventions))
        monitor.record_metric(
            "executive_briefing_length", len(result.executive_briefing)
        )

        # Log summary
        logger.info("\n" + "=" * 60)
        logger.info("PERFORMANCE SUMMARY")
        logger.info("=" * 60)
        monitor.log_summary()

        summary = monitor.get_summary()
        logger.info("\n✅ Synthesis completed successfully!")
        logger.info(f"   Total time: {summary['total_time_seconds']:.2f}s")
        logger.info(f"   Peak CPU: {summary['cpu']['max']:.1f}%")
        logger.info(f"   Peak RAM: {summary['memory']['max_mb']:.1f}MB")
        logger.info(f"   Max concurrent tasks: {summary['max_active_tasks']}")

        return result

    except Exception as e:
        logger.error(f"\n❌ Synthesis failed: {e}", exc_info=True)
        monitor.log_snapshot("Test failed")
        monitor.log_summary()
        raise


async def test_synthesis_agent(project_id: str, force_regenerate: bool = True):
    """
    Test the newer agent-based synthesis service.

    Args:
        project_id: The analysis project ID to synthesize
        force_regenerate: If True, delete existing synthesis runs before generating new one
    """
    logger.info("=" * 60)
    logger.info("SYNTHESIS AGENT TEST")
    logger.info("=" * 60)
    logger.info(f"Project ID: {project_id}")

    # Initialize monitoring
    monitor = ResourceMonitor(f"SynthesisAgentTest-{project_id}")
    monitor.start()
    monitor.log_snapshot("Test start")

    try:
        # Delete existing synthesis runs if requested
        if force_regenerate:
            from app.services.vectorization import vectorization_service

            logger.info("Deleting existing synthesis runs...")
            try:
                result = (
                    vectorization_service.supabase.table("synthesis_runs")
                    .delete()
                    .eq("analysis_project_id", project_id)
                    .execute()
                )
                deleted_count = len(result.data) if result.data else 0
                logger.info(f"Deleted {deleted_count} existing synthesis run(s)")
            except Exception as e:
                logger.warning(f"Failed to delete existing runs: {e}")

        from app.services.synthesis.agent import SynthesisAgent

        # Initialize agent
        agent = SynthesisAgent()

        # Run synthesis with monitoring
        with StageTimer(monitor, "agent_synthesis"):
            logger.info("\nStarting agent-based synthesis...")
            final_state = await agent.run(project_id)

        monitor.log_snapshot("Synthesis complete")

        # Display results
        logger.info("\n" + "=" * 60)
        logger.info("AGENT SYNTHESIS RESULTS")
        logger.info("=" * 60)

        issues = final_state.get("aggregated_issues", [])
        interventions = final_state.get("aggregated_interventions", [])
        briefing = final_state.get("executive_briefing", "")

        logger.info(f"\n📊 Aggregated Issues: {len(issues)}")
        for i, issue in enumerate(issues[:5], 1):
            logger.info(f"  {i}. {issue.issue_theme} (frequency: {issue.frequency})")

        logger.info(f"\n🎯 Aggregated Interventions: {len(interventions)}")
        for i, intervention in enumerate(interventions[:5], 1):
            logger.info(
                f"  {i}. {intervention.intervention_name} (frequency: {intervention.frequency})"
            )

        logger.info("\n📝 Executive Briefing:")
        logger.info(f"{briefing}")

        # Record metrics
        monitor.record_metric("issues_count", len(issues))
        monitor.record_metric("interventions_count", len(interventions))
        monitor.record_metric("briefing_length", len(briefing))

        # Log summary
        logger.info("\n" + "=" * 60)
        logger.info("PERFORMANCE SUMMARY")
        logger.info("=" * 60)
        monitor.log_summary()

        summary = monitor.get_summary()
        logger.info("\n✅ Agent synthesis completed successfully!")
        logger.info(f"   Total time: {summary['total_time_seconds']:.2f}s")
        logger.info(f"   Peak CPU: {summary['cpu']['max']:.1f}%")
        logger.info(f"   Peak RAM: {summary['memory']['max_mb']:.1f}MB")
        logger.info(f"   Max concurrent tasks: {summary['max_active_tasks']}")

        return final_state

    except Exception as e:
        logger.error(f"\n❌ Agent synthesis failed: {e}", exc_info=True)
        monitor.log_snapshot("Test failed")
        monitor.log_summary()
        raise


async def compare_synthesis_methods(project_id: str):
    """
    Compare legacy service vs agent-based synthesis.

    Args:
        project_id: The analysis project ID to synthesize
    """
    logger.info("\n" + "=" * 60)
    logger.info("COMPARING SYNTHESIS METHODS")
    logger.info("=" * 60)

    # Test legacy service
    logger.info("\n1️⃣  Testing Legacy Synthesis Service...")
    legacy_result = await test_synthesis_for_project(project_id)

    # Test agent-based service
    logger.info("\n2️⃣  Testing Agent-Based Synthesis...")
    agent_result = await test_synthesis_agent(project_id)

    # Compare
    logger.info("\n" + "=" * 60)
    logger.info("COMPARISON")
    logger.info("=" * 60)
    logger.info(
        f"Legacy: {len(legacy_result.key_issues)} issues, {len(legacy_result.interventions)} interventions"
    )

    agent_issues = agent_result.get("aggregated_issues", [])
    agent_interventions = agent_result.get("aggregated_interventions", [])
    logger.info(
        f"Agent:  {len(agent_issues)} issues, {len(agent_interventions)} interventions"
    )


async def main():
    """Main test function."""
    if len(sys.argv) < 2:
        logger.error(
            "Usage: python test_synthesis_service.py <project_id> [--legacy|--agent|--compare]"
        )
        logger.error("\nOptions:")
        logger.error("  --legacy   Test legacy synthesis service (default)")
        logger.error("  --agent    Test agent-based synthesis")
        logger.error("  --compare  Compare both methods")
        logger.error("\nNote:")
        logger.error(
            "  By default, existing synthesis runs are deleted before generating new ones."
        )
        logger.error("  This ensures you always get fresh results for testing.")
        logger.error("\nExample:")
        logger.error("  python test_synthesis_service.py abc123def456")
        logger.error("  python test_synthesis_service.py abc123def456 --agent")
        sys.exit(1)

    project_id = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else "--legacy"

    try:
        if mode == "--compare":
            await compare_synthesis_methods(project_id)
        elif mode == "--agent":
            await test_synthesis_agent(project_id)
        else:
            await test_synthesis_for_project(project_id)

    except KeyboardInterrupt:
        logger.info("\n\n⚠️  Test interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"\n\n❌ Test failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
