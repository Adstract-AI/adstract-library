#!/usr/bin/env python3
"""
Real-world workflow examples for the Adstract AI library.
This demonstrates how developers would integrate ad enhancement into their applications.
"""

import asyncio
import logging
import os
from typing import List, Dict, Any

# In production, this would be: from adstractai import AdClient, AdEnhancementError
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../src'))
from adstractai import Adstract, AdEnhancementError

# Configure logging to see what's happening
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ChatbotService:
    """Example chatbot service that integrates ad enhancements."""

    def __init__(self, adstract_api_key: str):
        self.ad_client = Adstract(api_key=adstract_api_key)
        self.conversation_sessions = {}

    def process_user_query(self, user_id: str, query: str, user_agent: str, ip_address: str = None) -> str:
        """Process a user query and enhance it with ads if possible."""

        # Create or get conversation context
        session_id = f"user_{user_id}_session"
        if session_id not in self.conversation_sessions:
            self.conversation_sessions[session_id] = {
                "conversation_id": f"conv_{user_id}_{int(time.time())}",
                "session_id": session_id,
                "message_count": 0
            }

        session = self.conversation_sessions[session_id]
        session["message_count"] += 1

        conversation_data = {
            "conversation_id": session["conversation_id"],
            "session_id": session["session_id"],
            "message_id": f"msg_{session['message_count']}"
        }

        # Use the default enhancement method - it never fails
        enhanced_prompt = self.ad_client.request_ad_enhancement_or_default(
            prompt=query,
            conversation=conversation_data,
            user_agent=user_agent,
            x_forwarded_for=ip_address  # Optional IP for geo-targeting
        )

        # In real app, you'd send enhanced_prompt to your LLM (OpenAI, Claude, etc.)
        # For demo, we'll just simulate the response
        if enhanced_prompt != query:
            logger.info(f"Enhanced prompt for user {user_id} ({len(enhanced_prompt)} chars)")
            return self._simulate_llm_response(enhanced_prompt, with_ads=True)
        else:
            logger.info(f"Using original prompt for user {user_id}")
            return self._simulate_llm_response(query, with_ads=False)

    def _simulate_llm_response(self, prompt: str, with_ads: bool) -> str:
        """Simulate LLM processing the enhanced prompt."""
        base_response = "I'd be happy to help you with that question!"

        if with_ads and "<ADS>" in prompt:
            # Extract ad content from the enhanced prompt
            return f"{base_response}\n\n[Ad content would be naturally integrated here based on the enhanced prompt instructions]"
        else:
            return base_response

    def close(self):
        """Clean up resources."""
        self.ad_client.close()


class BlogPlatform:
    """Example blog platform that enhances content with contextual ads."""

    def __init__(self, adstract_api_key: str):
        self.ad_client = Adstract(api_key=adstract_api_key)

    def enhance_blog_post(self, post_content: str, author_id: str, user_agent: str) -> str:
        """Enhance blog post content with contextually relevant ads."""

        conversation_data = {
            "conversation_id": f"blog_post_{author_id}",
            "session_id": f"author_{author_id}",
            "message_id": f"post_{int(time.time())}"
        }

        try:
            # Use strict enhancement method if ads are critical for revenue
            enhanced_content = self.ad_client.request_ad_enhancement(
                prompt=post_content,
                conversation=conversation_data,
                user_agent=user_agent
            )
            logger.info("Successfully enhanced blog post with ads")
            return enhanced_content

        except AdEnhancementError as e:
            logger.warning(f"Ad enhancement failed: {e}")
            # Fallback to original content if ads are not critical
            return post_content

    def enhance_blog_post_safe(self, post_content: str, author_id: str, user_agent: str) -> str:
        """Safe enhancement that always returns content (with or without ads)."""

        conversation_data = {
            "conversation_id": f"blog_post_{author_id}",
            "session_id": f"author_{author_id}",
            "message_id": f"post_{int(time.time())}"
        }

        # This never fails - perfect for content platforms
        enhanced_content = self.ad_client.request_ad_enhancement_or_default(
            prompt=post_content,
            conversation=conversation_data,
            user_agent=user_agent
        )

        if enhanced_content != post_content:
            logger.info("Enhanced blog post with ads")
        else:
            logger.info("Using original blog post content")

        return enhanced_content

    def close(self):
        self.ad_client.close()


class AsyncNewsService:
    """Example async news service that processes multiple articles concurrently."""

    def __init__(self, adstract_api_key: str):
        self.ad_client = Adstract(api_key=adstract_api_key)

    async def process_news_articles(self, articles: List[Dict[str, Any]]) -> List[str]:
        """Process multiple news articles with ad enhancements concurrently."""

        tasks = []
        for i, article in enumerate(articles):
            task = self._enhance_article(
                article["content"],
                article.get("category", "general"),
                f"news_reader_{i}",
                "Mozilla/5.0 (NewsBot) NewsService/1.0"
            )
            tasks.append(task)

        enhanced_articles = await asyncio.gather(*tasks, return_exceptions=True)

        results = []
        for i, result in enumerate(enhanced_articles):
            if isinstance(result, Exception):
                logger.error(f"Failed to process article {i}: {result}")
                results.append(articles[i]["content"])  # Use original content
            else:
                results.append(result)

        return results

    async def _enhance_article(self, content: str, category: str, reader_id: str, user_agent: str) -> str:
        """Enhance a single article with ads."""

        conversation_data = {
            "conversation_id": f"news_{category}_{reader_id}",
            "session_id": f"reader_{reader_id}",
            "message_id": f"article_{int(time.time())}"
        }

        # Use async default method for reliable processing
        enhanced_content = await self.ad_client.request_ad_enhancement_or_default_async(
            prompt=content,
            conversation=conversation_data,
            user_agent=user_agent
        )

        return enhanced_content

    async def close(self):
        await self.ad_client.aclose()


def simple_integration_example():
    """Simplest possible integration example."""
    print("🚀 Simple Integration Example")
    print("=" * 40)

    # Initialize client with API key
    client = Adstract(api_key="sk_test_your_api_key_here")

    # Basic usage - enhance a user prompt
    user_prompt = "How do I build a mobile app?"
    conversation = {
        "conversation_id": "demo_conv_1",
        "session_id": "demo_session_1",
        "message_id": "demo_msg_1"
    }

    # Safe enhancement (never throws exceptions)
    enhanced_prompt = client.request_ad_enhancement_or_default(
        prompt=user_prompt,
        conversation=conversation,
        user_agent="Mozilla/5.0 (Demo) MyApp/1.0"
    )

    print(f"Original: {user_prompt}")
    print(f"Enhanced: {enhanced_prompt[:100]}...")
    print(f"Was enhanced: {enhanced_prompt != user_prompt}")

    client.close()
    print("✅ Simple integration complete\n")


async def production_chatbot_example():
    """Production-ready chatbot integration."""
    print("🤖 Production Chatbot Example")
    print("=" * 40)

    # Initialize chatbot service
    chatbot = ChatbotService("sk_test_chatbot_api_key")

    # Simulate user interactions
    user_queries = [
        {
            "user_id": "user_123",
            "query": "What's the best programming language for AI?",
            "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)",
            "ip": "203.0.113.1"
        },
        {
            "user_id": "user_456",
            "query": "How do I optimize database performance?",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "ip": "198.51.100.1"
        }
    ]

    for query_data in user_queries:
        response = chatbot.process_user_query(
            user_id=query_data["user_id"],
            query=query_data["query"],
            user_agent=query_data["user_agent"],
            ip_address=query_data["ip"]
        )

        print(f"User {query_data['user_id']}: {query_data['query']}")
        print(f"Response: {response}\n")

    chatbot.close()
    print("✅ Chatbot example complete\n")


async def content_platform_example():
    """Content platform with batch processing."""
    print("📰 Content Platform Example")
    print("=" * 40)

    # Initialize services
    blog_platform = BlogPlatform("sk_test_blog_api_key")
    news_service = AsyncNewsService("sk_test_news_api_key")

    # Blog post enhancement
    blog_post = """
    The future of artificial intelligence is rapidly evolving. 
    Machine learning algorithms are becoming more sophisticated...
    """

    enhanced_blog = blog_platform.enhance_blog_post_safe(
        post_content=blog_post,
        author_id="author_789",
        user_agent="Mozilla/5.0 (BlogEditor) BlogPlatform/2.1"
    )

    print("Blog post enhanced successfully")

    # Batch news processing
    news_articles = [
        {"content": "Breaking: New AI breakthrough announced...", "category": "tech"},
        {"content": "Market update: Tech stocks rise...", "category": "finance"},
        {"content": "Sports update: Championship results...", "category": "sports"}
    ]

    enhanced_articles = await news_service.process_news_articles(news_articles)
    print(f"Processed {len(enhanced_articles)} news articles")

    # Cleanup
    blog_platform.close()
    await news_service.close()
    print("✅ Content platform example complete\n")


def error_handling_example():
    """Demonstration of different error handling approaches."""
    print("⚠️  Error Handling Example")
    print("=" * 40)

    client = Adstract(api_key="sk_test_error_handling_key")

    conversation = {
        "conversation_id": "error_test_conv",
        "session_id": "error_test_session",
        "message_id": "error_test_msg"
    }

    test_prompt = "Test prompt for error handling"
    user_agent = "Mozilla/5.0 (ErrorTest) TestApp/1.0"

    # Approach 1: Strict enhancement (raises exceptions)
    print("1. Strict enhancement approach:")
    try:
        enhanced = client.request_ad_enhancement(
            prompt=test_prompt,
            conversation=conversation,
            user_agent=user_agent
        )
        print(f"   ✅ Enhancement successful")
    except AdEnhancementError as e:
        print(f"   ❌ Enhancement failed: {e}")
        print("   🔄 Fallback: using original prompt")

    # Approach 2: Safe enhancement (never fails)
    print("\n2. Safe enhancement approach:")
    enhanced = client.request_ad_enhancement_or_default(
        prompt=test_prompt,
        conversation=conversation,
        user_agent=user_agent
    )
    print(f"   ✅ Always returns content: {enhanced == test_prompt}")

    client.close()
    print("✅ Error handling example complete\n")


async def main():
    """Run all workflow examples."""
    print("🎯 Adstract AI Library - Real World Workflows")
    print("=" * 60)
    print("These examples show how to integrate ad enhancement into production applications.\n")

    # Run examples
    simple_integration_example()
    await production_chatbot_example()
    await content_platform_example()
    error_handling_example()

    print("=" * 60)
    print("🎉 All workflow examples completed!")
    print("\n💡 Key Integration Patterns:")
    print("   • Use request_ad_enhancement_or_default() for reliability")
    print("   • Use request_ad_enhancement() when ads are critical")
    print("   • Async methods for high-throughput applications")
    print("   • Proper conversation context for better ad targeting")
    print("   • Always clean up resources with close()/aclose()")


if __name__ == "__main__":
    # Import time for timestamps
    import time

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Workflow examples interrupted by user")
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        import traceback
        traceback.print_exc()
