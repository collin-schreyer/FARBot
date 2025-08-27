#!/usr/bin/env python3
"""
Test the GPT-5 enhanced FAR Chatbot with dynamic context loading
"""

from far_chatbot import FARChatbot
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

def test_enhanced_chatbot():
    """Test the enhanced chatbot with various query types"""
    print("🚀 Testing GPT-5 Enhanced FAR Chatbot")
    print("=" * 80)
    
    # Initialize enhanced chatbot
    chatbot = FARChatbot(
        faiss_index_path="/Users/collinschreyer/GSA/FAR_BOT/dita_html/faiss_index.index",
        texts_path="/Users/collinschreyer/GSA/FAR_BOT/dita_html/texts.txt",
        use_gpt5=True  # Enable GPT-5 optimization
    )
    
    # Test queries of different complexity levels
    test_queries = [
        # Simple definition
        "What is a small business set-aside?",
        
        # Complex process
        "Walk me through the complete process for protesting a contract award, including all deadlines and requirements",
        
        # Comprehensive guide
        "Tell me everything about cost accounting standards - requirements, compliance, documentation, and penalties",
        
        # Comparison query
        "Compare sole source procurement versus competitive bidding - when to use each and what's required",
        
        # Follow-up elaboration
        "Tell me more about the documentation requirements"
    ]
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n🔍 Test Query {i}: {query}")
        print("-" * 60)
        
        result = chatbot.chat(query)
        
        # Display enhanced results
        analysis = result['query_analysis']
        print(f"📊 Query Type: {analysis['type'].title()}")
        print(f"🎯 Complexity: {analysis['complexity']}/5")
        print(f"🔍 Context Chunks: {result['context_size']}")
        print(f"🤖 Model: {result['model_used']}")
        print(f"📝 Max Tokens: {analysis['search_params']['max_tokens']}")
        
        print(f"\n🤖 Response Preview:")
        response_preview = result['response'][:400] + "..." if len(result['response']) > 400 else result['response']
        print(response_preview)
        
        print(f"\n📋 Topics: {result['topics']}")
        print(f"📄 Sections: {result['sections'][:5]}...")  # Show first 5 sections
        print(f"💡 Suggestions: {result['suggestions']}")
        
        if chatbot.conversation.current_topics:
            print(f"🧠 Conversation Context: {chatbot.conversation.current_topics}")
        
        print("-" * 60)
    
    print("\n✅ Enhanced chatbot testing completed!")
    print(f"🎉 Total conversation turns: {len(chatbot.conversation.turns)}")

def compare_models():
    """Compare GPT-3.5 vs GPT-5 performance"""
    print("\n🔬 Model Comparison Test")
    print("=" * 80)
    
    query = "What are the requirements for competitive bidding and how does the process work?"
    
    # Test with GPT-3.5
    print("Testing with GPT-3.5...")
    chatbot_35 = FARChatbot(
        faiss_index_path="/Users/collinschreyer/GSA/FAR_BOT/dita_html/faiss_index.index",
        texts_path="/Users/collinschreyer/GSA/FAR_BOT/dita_html/texts.txt",
        use_gpt5=False
    )
    result_35 = chatbot_35.chat(query)
    
    # Test with GPT-5
    print("Testing with GPT-5...")
    chatbot_5 = FARChatbot(
        faiss_index_path="/Users/collinschreyer/GSA/FAR_BOT/dita_html/faiss_index.index",
        texts_path="/Users/collinschreyer/GSA/FAR_BOT/dita_html/texts.txt",
        use_gpt5=True
    )
    result_5 = chatbot_5.chat(query)
    
    # Compare results
    print(f"\n📊 Comparison Results:")
    print(f"GPT-3.5: {result_35['context_size']} chunks, {len(result_35['response'])} chars")
    print(f"GPT-5:   {result_5['context_size']} chunks, {len(result_5['response'])} chars")
    print(f"GPT-5 context increase: {result_5['context_size'] / result_35['context_size']:.1f}x")
    print(f"GPT-5 response increase: {len(result_5['response']) / len(result_35['response']):.1f}x")

if __name__ == "__main__":
    test_enhanced_chatbot()
    compare_models()