#!/usr/bin/env python3
"""
Simple test of the enhanced FAR Chatbot
"""

from far_chatbot import FARChatbot
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

def test_simple():
    """Test basic enhanced functionality"""
    print("🚀 Testing Enhanced FAR Chatbot (Simple)")
    print("=" * 60)
    
    # Initialize enhanced chatbot
    chatbot = FARChatbot(
        faiss_index_path="/Users/collinschreyer/GSA/FAR_BOT/dita_html/faiss_index.index",
        texts_path="/Users/collinschreyer/GSA/FAR_BOT/dita_html/texts.txt",
        use_gpt5=True
    )
    
    # Test comprehensive query to trigger maximum 50-chunk loading
    query = "Tell me everything comprehensive about small business set-asides - complete comprehensive guide"
    print(f"Query: {query}")
    
    result = chatbot.chat(query)
    
    print(f"\n📊 Analysis:")
    analysis = result['query_analysis']
    print(f"  Type: {analysis['type']}")
    print(f"  Complexity: {analysis['complexity']}")
    print(f"  Context chunks: {result['context_size']}")
    print(f"  Model: {result['model_used']}")
    
    print(f"\n🤖 Response ({len(result['response'])} chars):")
    if result['response']:
        print(result['response'][:500] + "..." if len(result['response']) > 500 else result['response'])
    else:
        print("(Empty response - checking fallback)")
        print(f"Sections found: {result['sections']}")
        print(f"Topics: {result['topics']}")
    
    print(f"\n💡 Suggestions: {result['suggestions']}")

if __name__ == "__main__":
    test_simple()