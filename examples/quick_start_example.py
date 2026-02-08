#!/usr/bin/env python3
"""Example demonstrating the updated analytics implementation with tracking_identifier counting."""

from adstractai import Adstract, AdRequestConfiguration


API_KEY = "adpk_live_gx6xbutnrkyjaqjd.uatnQaAhIho-QalyI5Cng3CRhJKobYWoBGFqrvzgdPQ"


def main():
    print("=== Quick Demo ===")

    # Initialize the client with XML wrapping type
    client = Adstract(
        api_key=API_KEY,
        base_url="http://localhost:8000"
    )

    config = AdRequestConfiguration(
        session_id="user_session_123",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        x_forwarded_for="192.168.1.1"
    )

    prompt = "What are some good ways to advertise with AI ?"


    try:
        # Step 1: Get ad enhancement
        result = client.request_ad_or_default(prompt=prompt, config=config)

        if result.success:
            print(f"✓ Ad enhancement successful")

            # Step 2: Simulate LLM response with XML-wrapped ads
            # This example shows how tracking_identifier affects total_ads_detected count
            llm_response = f"""
            Natively advertising with AI is all about integrating promotional content directly 
            into user interactions in a way that feels organic and enhances the conversation. 
            The best results come from leveraging AI’s contextual understanding to serve ads that 
            are relevant to the user's interests or the current discussion—making them feel like helpful 
            suggestions instead of interruptions.

            To do this effectively, you should:
            
            Utilize AI’s natural language capabilities to blend messages smoothly into the chat flow.
            Match ad content with the conversation context to ensure high relevance.
            Maintain transparency with clear but unobtrusive sponsored labels.
            Continuously optimize ad delivery based on user engagement and feedback.
            <ADS>
            Sponsored
            Looking to maximize your AI platform’s revenue without disrupting user experience? Adstract 
            offers a next-generation solution for monetizing conversations with context-aware, semantically
            matched ads built for LLMs and chatbots. Publishers can deliver non-intrusive, valuable ads, 
            benefiting from advanced relevance scoring, fraud prevention, and dynamic pricing. 
            
            <a href="{result.ad_response.tracking_url}">Request access</a>
            
            to Adstract today. Performance may vary based on traffic quality and integration.
            By using AI’s contextual intelligence and platforms designed for conversational environments, 
            you can achieve effective native advertising that benefits both users and publishers.
            </ADS>
            """

            # Step 3: Analyze and report
            client.analyse_and_report(
                enhancement_result=result,
                llm_response=llm_response
            )

            print(f"✓ Ad ack report successful")


    except Exception as e:
        print(f"Error: {e}")

    finally:
        client.close()


if __name__ == "__main__":
    main()
