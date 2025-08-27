#!/usr/bin/env python3
"""
Test enhanced conversational flow
"""

from far_chatbot import FARChatbot
import logging

logging.basicConfig(level=logging.INFO)

def test_conversation_flow():
    """Test enhanced conversation with follow-ups"""
    print("🚀 Testing Enhanced Conversational Flow")
    print("=" * 60)
    
    chatbot = FARChatbot(
        faiss_index_path="/Users/collinschreyer/GSA/FAR_BOT/dita_html/faiss_index.index",
        texts_path="/Users/collinschreyer/GSA/FAR_BOT/dita_html/texts.txt",
        use_gpt5=True
    )
    
    # Conversation flow
    queries = [
        "What are small business set-asides?",
        "What are the eligibility requirements?",  # Should understand context
        "Tell me more about the documentation"     # Should elaborate on current topic
    ]
    
    for i, query in enumerate(queries, 1):
        print(f"\n🔍 Turn {i}: {query}")
        print("-" * 40)
        
        result = chatbot.chat(query)
        analysis = result['query_analysis']
        
        print(f"📊 {analysis['type'].title()} query, {result['context_size']} chunks")
        print(f"🤖 Response: {len(result['response'])} chars")
        print(f"💡 Suggestions: {result['suggestions']}")
        
        if chatbot.conversation.current_topics:
            print(f"🧠 Context: {chatbot.conversation.current_topics[:2]}")
    
    print(f"\n✅ Conversation completed with {len(chatbot.conversation.turns)} turns")

if __name__ == "__main__":
    test_conversation_flow()