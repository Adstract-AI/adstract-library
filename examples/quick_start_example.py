#!/usr/bin/env python3
"""
Quick Start Guide - Adstract AI Integration Examples
Shows the most common ways developers integrate ad enhancement.
"""

from adstractai import Adstract

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


if __name__ == "__main__":
    print("Adstract AI Integration Examples\n")

    print("1. Basic Integration:")
    basic_integration()
    print()

    print("Integration examples completed!")
    print("\nChoose your integration pattern:")
    print("   • request_ad_enhancement_or_default() - Reliable, never fails")
    print("   • request_ad_enhancement() - Strict, throws errors")
    print("   • Use async versions for high-throughput applications")
