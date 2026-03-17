#!/usr/bin/env python3
"""Example demonstrating integration with Adstract SDK and OpenAI.

Note: This example requires the 'openai' package to be installed locally for testing.
      OpenAI is NOT a dependency of the adstractai package.
      Install it separately: pip install openai
"""

import os

from adstractai import Adstract, AdRequestContext, OptionalContext
from dotenv import load_dotenv

load_dotenv()

# Adstract API Key
ADSTRACT_API_KEY = "adpk_live_wc2yahh2trc7tixu.mj1FvgtOygLkLavGLb4JtFdJTNecW7m94O7KxfnGBlw"

# OpenAI API Key (set via environment variable or replace with your key)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")


def main():
    print("=== Adstract + OpenAI Integration Demo ===")

    # Initialize the Adstract client
    client = Adstract(api_key=ADSTRACT_API_KEY, base_url="http://localhost:8000", wrapping_type="xml")

    context = AdRequestContext(
        session_id="user_session_123",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        user_ip="192.168.1.1",
    )

    optional_context = OptionalContext(country="US",
                                       age=30,
                                       gender="male",
                                       city="New York",
                                       asn=12345,
                                       region="NY"
                                       )

    user_prompt = "What are some good ways to advertise with AI?"

    try:
        # Step 1: Get ad enhancement from Adstract
        result = client.request_ad(prompt=user_prompt,
                                   context=context,
                                   optional_context=optional_context,
                                   raise_exception=True)

        if result.success:
            print("✓ Ad enhancement successful")
            print(f"  Product: {result.ad_response.product_name}")

            # Step 2: Call OpenAI with the enhanced prompt

            from openai import OpenAI
            openai_client = OpenAI(api_key=OPENAI_API_KEY)

            # Use the enhanced prompt from Adstract
            response = openai_client.responses.create(
                model="gpt-4.1-nano",
                instructions="Always format your responses using clean HTML tags for better readability in chat. "
                             "Use appropriate tags like <p>, <strong>, <em>, <ul>, <ol>, <li>, <code>, <pre>, "
                             "etc. Do not include <html>, <head>, or <body> tags - only content tags.",
                input=result.prompt,
            )

            llm_response = response.output_text
            print("✓ OpenAI response received")

            # Step 3: Report ad acknowledgment to Adstract
            ack = client.acknowledge(enhancement_result=result, llm_response=llm_response)
            print("✓ Ad acknowledgment reported")
            print(f"  Ack status: {ack.status}")

        else:
            print("✗ Ad enhancement not successful, using original prompt")
            print(f"  Error: {result.error}")

    except Exception as e:
        print(f"Error: {e}")

    finally:
        client.close()


if __name__ == "__main__":
    main()
