"""Example CrewAI agent with MUTX observability integration.

This example demonstrates:
1. Creating a 2-agent crew (researcher + writer) with CrewAI
2. Attaching MutxCrewAICallbackHandler for tracing
3. MUTX policy store integration for governance

Run with:
    pip install mutx[crewai] crewai
    python examples/crewai_agent.py
"""

# CrewAI imports
from crewai import Agent, Crew, Task
from crewai_tools import SerpSearchTool

# MUTX adapter imports
from mutx.adapters.crewai import MutxCrewAICallbackHandler, run_crew


def create_researcher_agent(api_key: str) -> Agent:
    """Create a researcher agent with web search capability.

    Args:
        api_key: API key for search tool.

    Returns:
        Configured Agent instance.
    """
    return Agent(
        role="Research Analyst",
        goal="Research and synthesize comprehensive information on the given topic",
        backstory="You are an experienced research analyst with expertise in "
        "finding and synthesizing information from various sources.",
        tools=[SerpSearchTool(api_key=api_key)],
        verbose=True,
    )


def create_writer_agent() -> Agent:
    """Create a writer agent for content creation.

    Returns:
        Configured Agent instance.
    """
    return Agent(
        role="Content Writer",
        goal="Create well-structured, engaging content based on research",
        backstory="You are a skilled content writer who transforms research "
        "into clear, compelling narratives.",
        verbose=True,
    )


def create_tasks(researcher: Agent, writer: Agent, topic: str) -> list[Task]:
    """Create tasks for the crew.

    Args:
        researcher: The researcher agent.
        writer: The writer agent.
        topic: The topic to research and write about.

    Returns:
        List of Task instances.
    """
    research_task = Task(
        description=f"Research comprehensive information about: {topic}",
        expected_output="A detailed research summary with key findings and sources",
        agent=researcher,
    )

    write_task = Task(
        description="Write an engaging article based on the research findings",
        expected_output="A well-structured article with introduction, body, and conclusion",
        agent=writer,
    )

    return [research_task, write_task]


def main():
    """Run the example demonstrating MUTX CrewAI integration."""

    # Configuration - replace with your actual values or set environment variables
    import os

    MUTX_API_URL = os.environ.get("MUTX_API_URL", "https://api.mutx.dev")
    MUTX_API_KEY = os.environ.get("MUTX_API_KEY", "***")  # Get from mutx.dev/dashboard
    SERP_API_KEY = os.environ.get("SERP_API_KEY", "***")  # For web search

    # ============================================================
    # Example 1: Basic crew with MUTX callback handler
    # ============================================================
    print("\n" + "=" * 60)
    print("Example 1: Crew with MutxCrewAICallbackHandler")
    print("=" * 60 + "\n")

    # Create agents
    researcher = create_researcher_agent(SERP_API_KEY)
    writer = create_writer_agent()

    # Create tasks
    tasks = create_tasks(researcher, writer, "latest AI trends in 2024")

    # Create crew
    crew = Crew(
        agents=[researcher, writer],
        tasks=tasks,
        verbose=True,
    )

    # Attach MUTX callback handler
    callback_handler = MutxCrewAICallbackHandler(
        api_url=MUTX_API_URL,
        api_key=MUTX_API_KEY,
        crew_name="research-writing-crew",
    )
    for agent in crew.agents:
        if getattr(agent, "callback", None) is None:
            agent.callback = callback_handler

    # Execute crew with callback (manual approach)
    result = crew.kickoff(inputs={"topic": "latest AI trends in 2024"})

    print(f"\nCrew result: {result}\n")

    # ============================================================
    # Example 2: Using run_crew() helper
    # ============================================================
    print("\n" + "=" * 60)
    print("Example 2: Using run_crew() helper")
    print("=" * 60 + "\n")

    # Create fresh crew for demonstration
    researcher2 = create_researcher_agent(SERP_API_KEY)
    writer2 = create_writer_agent()
    tasks2 = create_tasks(researcher2, writer2, "sustainable energy solutions")

    crew2 = Crew(
        agents=[researcher2, writer2],
        tasks=tasks2,
        verbose=True,
    )

    # Use run_crew helper to execute with MUTX tracing
    result2 = run_crew(crew2, {"topic": "sustainable energy solutions"})

    print(f"\nCrew result: {result2}\n")

    # ============================================================
    # Example 3: MUTX Policy Store Integration
    # ============================================================
    print("\n" + "=" * 60)
    print("Example 3: MUTX Policy Store Integration")
    print("=" * 60 + "\n")

    # This demonstrates how to fetch and apply MUTX policies
    # to govern crew behavior

    try:
        import httpx

        # Fetch policies from MUTX
        client = httpx.Client(
            base_url=MUTX_API_URL,
            headers={"Authorization": f"Bearer {MUTX_API_KEY}"},
            timeout=30.0,
        )

        # Get active policies for agent governance
        policies_response = client.get("/v1/policies")
        policies = policies_response.json()

        print(f"Fetched {len(policies.get('items', []))} active policies")

        # Example: Apply content filtering policy
        for policy in policies.get("items", []):
            if policy.get("type") == "content_filter":
                print(f"  - Applying policy: {policy.get('name')}")

                # In a real scenario, you would configure the crew
                # agents to respect these policies

    except Exception as e:
        print(f"Policy store integration example (actual usage requires valid credentials): {e}")

    print("\nExample completed successfully!")


if __name__ == "__main__":
    main()
