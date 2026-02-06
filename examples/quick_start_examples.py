#!/usr/bin/env python3
"""
Quick Start Guide - Adstract AI Integration Examples
Shows the most common ways developers integrate ad enhancement.
"""

import asyncio

from adstractai import AdEnhancementError, Adstract

API_KEY = "adpk_live_gx6xbutnrkyjaqjd.uatnQaAhIho-QalyI5Cng3CRhJKobYWoBGFqrvzgdPQ"


def basic_integration():
    """Most basic integration - enhance a user prompt."""

    # 1. Initialize client
    client = Adstract(api_key=API_KEY)

    # 2. Prepare user data
    user_prompt = "Where can i advertiser my products with AI?"
    conversation = {
        "conversation_id": "chat_session_123",
        "session_id": "user_session_456",
        "message_id": "message_789",
    }
    user_agent = "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)"
    # Put this host ip as value, for testing
    x_forwarded_for = "185.100.245.160"

    # 3. Enhance prompt (safe method - never fails)
    enhanced_prompt = client.request_ad_enhancement_or_default(
        prompt=user_prompt,
        conversation=conversation,
        user_agent=user_agent,
        x_forwarded_for=x_forwarded_for,
    )

    # 4. Use enhanced prompt with your LLM
    print(f"Send this to OpenAI/Claude: {enhanced_prompt}")

    # 5. Clean up
    client.close()


def chatbot_integration():
    """How to integrate into a chatbot service."""

    class MyChatBot:
        def __init__(self):
            self.ad_client = Adstract(api_key="your_api_key")

        def handle_user_message(
            self, user_id: str, message: str, user_agent: str, x_forwarded_for: str
        ):
            """Process user message with ad enhancement."""

            conversation = {
                "conversation_id": f"chat_{user_id}",
                "session_id": f"session_{user_id}",
                "message_id": f"msg_{hash(message) % 10000}",
            }

            # Enhance the user's message
            enhanced_prompt = self.ad_client.request_ad_enhancement_or_default(
                prompt=message,
                conversation=conversation,
                user_agent=user_agent,
                x_forwarded_for=x_forwarded_for,
            )

            # Send enhanced prompt to your LLM (OpenAI, Claude, etc.)
            # The LLM will see ad instructions and integrate them naturally
            llm_response = self.call_openai_api(enhanced_prompt)

            return llm_response

        def call_openai_api(self, prompt):
            # This is where you'd call OpenAI's API
            return "Your LLM response with naturally integrated ads"

        def close(self):
            self.ad_client.close()

    # Usage
    bot = MyChatBot()
    response = bot.handle_user_message(
        user_id="user123",
        message="What's the best laptop for programming?",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        x_forwarded_for="185.100.245.160",
    )
    print(f"Bot response: {response}")
    bot.close()


async def high_volume_integration():
    """How to handle many requests efficiently with async."""

    client = Adstract(api_key="your_api_key")

    async def process_user_request(user_data):
        """Process a single user request asynchronously."""

        enhanced_prompt = await client.request_ad_enhancement_or_default_async(
            prompt=user_data["message"],
            conversation={
                "conversation_id": f"conv_{user_data['user_id']}",
                "session_id": f"session_{user_data['user_id']}",
                "message_id": user_data["message_id"],
            },
            user_agent=user_data["user_agent"],
            x_forwarded_for=user_data["x_forwarded_for"],
        )

        # Process with your LLM
        return f"Enhanced response for {user_data['user_id']}"

    # Process multiple requests concurrently
    user_requests = [
        {
            "user_id": "user1",
            "message": "How to deploy Docker containers?",
            "message_id": "msg1",
            "user_agent": "Mozilla/5.0 (Macintosh)",
            "x_forwarded_for": "185.100.245.160",
        },
        {
            "user_id": "user2",
            "message": "Best practices for React development?",
            "message_id": "msg2",
            "user_agent": "Mozilla/5.0 (Windows)",
            "x_forwarded_for": "185.100.245.160",
        },
    ]

    # Process all requests concurrently
    tasks = [process_user_request(req) for req in user_requests]
    results = await asyncio.gather(*tasks)

    print(f"Processed {len(results)} requests concurrently")
    await client.aclose()


def strict_vs_safe_enhancement():
    """Understanding the difference between strict and safe enhancement."""

    client = Adstract(api_key="your_api_key")

    conversation = {
        "conversation_id": "demo_conv",
        "session_id": "demo_session",
        "message_id": "demo_msg",
    }
    user_agent = "Mozilla/5.0 (Demo)"
    prompt = "What's the weather today?"
    x_forwarded_for = "185.100.245.160"

    # Method 1: Strict enhancement (throws exceptions on failure)
    try:
        enhanced = client.request_ad_enhancement(
            prompt=prompt,
            conversation=conversation,
            user_agent=user_agent,
            x_forwarded_for=x_forwarded_for,
        )
        print("✅ Strict enhancement succeeded")
        # Use enhanced prompt...

    except AdEnhancementError:
        print("❌ Strict enhancement failed - handle error")
        # Fallback to original prompt...

    # Method 2: Safe enhancement (never throws exceptions)
    enhanced = client.request_ad_enhancement_or_default(
        prompt=prompt,
        conversation=conversation,
        user_agent=user_agent,
        x_forwarded_for=x_forwarded_for,
    )
    print("✅ Safe enhancement always works")
    # Always get a usable prompt (enhanced or original)...

    client.close()


if __name__ == "__main__":
    print("🚀 Adstract AI Integration Examples\n")

    print("1. Basic Integration:")
    basic_integration()
    print()

    # print("2. Chatbot Integration:")
    # chatbot_integration()
    # print()
    #
    # print("3. High-Volume Async Integration:")
    # asyncio.run(high_volume_integration())
    # print()
    #
    # print("4. Strict vs Safe Enhancement:")
    # strict_vs_safe_enhancement()
    print()

    print("✨ Integration examples completed!")
    print("\n💡 Choose your integration pattern:")
    print("   • request_ad_enhancement_or_default() - Reliable, never fails")
    print("   • request_ad_enhancement() - Strict, throws errors")
    print("   • Use async versions for high-throughput applications")
