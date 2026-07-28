"""Example AutoGen agent with MUTX observability integration.

This example demonstrates:
1. Creating a simple AutoGen agent team
2. Registering MutxAutoGenCallback for tracing
3. Using wrapped tool calls with OTel spans

Run with:
    pip install mutx[autogen] autogen
    python examples/autogen_agent.py
"""

# AutoGen imports
from autogen import ConversableAgent, GroupChat, GroupChatManager

# MUTX adapter imports
from mutx.adapters.autogen import MutxAutoGenCallback, register_with_autogen


def create_assistant_agent(name: str, api_key: str) -> ConversableAgent:
    """Create an assistant agent with MUTX callback.

    Args:
        name: Name for the agent.
        api_key: OpenAI API key for LLM calls.

    Returns:
        Configured ConversableAgent instance.
    """
    agent = ConversableAgent(
        name=name,
        llm_config={
            "model": "gpt-4",
            "api_key": api_key,
            "temperature": 0.7,
        },
        system_message="You are a helpful assistant that provides accurate information.",
    )

    # Register MUTX callback for observability
    register_with_autogen(agent, "https://api.mutx.dev", "***")

    return agent


def create_coder_agent(api_key: str) -> ConversableAgent:
    """Create a coder agent specialized in code tasks.

    Args:
        api_key: OpenAI API key for LLM calls.

    Returns:
        Configured ConversableAgent instance.
    """
    agent = ConversableAgent(
        name="coder",
        llm_config={
            "model": "gpt-4",
            "api_key": api_key,
            "temperature": 0.3,
        },
        system_message="You are a coding assistant that helps write clean, efficient code.",
    )

    # Register MUTX callback
    register_with_autogen(agent, "https://api.mutx.dev", "***")

    return agent


def example_two_agent_chat():
    """Example of two agents communicating."""
    print("\n" + "=" * 60)
    print("Example 1: Two-agent chat")
    print("=" * 60 + "\n")

    OPENAI_API_KEY = "your-openai-api-key"

    # Create agents
    assistant = create_assistant_agent("assistant", OPENAI_API_KEY)
    coder = create_coder_agent(OPENAI_API_KEY)

    # Initiate a conversation
    response = assistant.generate_reply(
        messages=[
            {
                "role": "user",
                "content": "Hello! Can you help me write a Python function to calculate fibonacci?",
            }
        ],
        sender=coder,
    )

    print(f"Coder response: {response}")


def example_with_callback_directly():
    """Example using MutxAutoGenCallback directly."""
    print("\n" + "=" * 60)
    print("Example 2: Using MutxAutoGenCallback directly")
    print("=" * 60 + "\n")

    OPENAI_API_KEY = "your-openai-api-key"
    MUTX_API_URL = "https://api.mutx.dev"
    MUTX_API_KEY = "***"

    # Create callback directly
    callback = MutxAutoGenCallback(
        api_url=MUTX_API_URL,
        api_key=MUTX_API_KEY,
        agent_name="direct-callback-agent",
    )

    # Create agent with the callback
    agent = ConversableAgent(
        name="direct-agent",
        llm_config={
            "model": "gpt-4",
            "api_key": OPENAI_API_KEY,
        },
        system_message="You are a helpful assistant.",
    )

    # Wrap an LLM call for demonstration
    def example_llm_call():
        return agent.generate_reply(
            messages=[{"role": "user", "content": "What is 2+2?"}],
            sender=agent,
        )

    # Use the wrapped LLM call
    wrapped_result = callback.wrap_llm_call(
        model="gpt-4",
        func=example_llm_call,
    )

    print(f"Wrapped LLM call result: {wrapped_result}")


def example_group_chat():
    """Example of a group chat with multiple agents."""
    print("\n" + "=" * 60)
    print("Example 3: Group chat with MUTX tracing")
    print("=" * 60 + "\n")

    OPENAI_API_KEY = "your-openai-api-key"

    # Create agents
    agent1 = ConversableAgent(
        name="Alice",
        llm_config={"model": "gpt-4", "api_key": OPENAI_API_KEY},
        system_message="You are Alice, a friendly assistant.",
    )
    agent2 = ConversableAgent(
        name="Bob",
        llm_config={"model": "gpt-4", "api_key": OPENAI_API_KEY},
        system_message="You are Bob, a helpful assistant.",
    )

    # Register callbacks
    register_with_autogen(agent1, "https://api.mutx.dev", "***")
    register_with_autogen(agent2, "https://api.mutx.dev", "***")

    # Create group chat
    group_chat = GroupChat(
        agents=[agent1, agent2],
        messages=[],
        max_round=5,
    )

    manager = GroupChatManager(
        groupchat=group_chat,
        llm_config={"model": "gpt-4", "api_key": OPENAI_API_KEY},
    )

    # Initiate group chat
    agent1.initiate_chat(
        manager,
        message="Hello everyone! Let's discuss AI trends.",
    )

    print("Group chat completed!")


def main():
    """Run all examples demonstrating MUTX AutoGen integration."""

    # Example 1: Two-agent chat
    example_two_agent_chat()

    # Example 2: Direct callback usage
    example_with_callback_directly()

    # Example 3: Group chat
    example_group_chat()

    print("\nAll examples completed successfully!")


if __name__ == "__main__":
    main()
