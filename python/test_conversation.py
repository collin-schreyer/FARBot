#!/usr/bin/env python3
"""
Test conversational features of the FAR Chatbot
"""

from far_chatbot import FARChatbot
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

def test_conversation():
    """Test conversational flow with follow-up questions"""
    print("🏛️ Testing Conversational FAR Chatbot...")
    print("=" * 80)
    
    # Initialize chatbot
    chatbot = FARChatbot(
        faiss_index_path="/Users/collinschreyer/GSA/FAR_BOT/dita_html/faiss_index.index",
        texts_path="/Users/collinschreyer/GSA/FAR_BOT/dita_html/texts.txt"
    )
    
    # Test conversation flow
    conversation_flow = [
        "What are small business set-asides?",
        "What are the eligibility requirements?",  # Should understand "the" refers to set-asides
        "Tell me more about HUBZone",  # Should expand on HUBZone from previous context
        "How do I apply?",  # Should understand context is HUBZone application
        "What documentation is required?"  # Should continue HUBZone context
    ]
    
    for i, query in enumerate(conversation_flow, 1):
        print(f"\n🔍 Conversation Turn {i}: {query}")
        print("-" * 60)
        
        result = chatbot.chat(query)
        
        print(f"🤖 Response: {result['response'][:300]}...")
        print(f"📋 Topics: {result['topics']}")
        print(f"📄 Sections: {result['sections']}")
        print(f"💡 Suggestions: {result['suggestions']}")
        
        # Show conversation context
        if chatbot.conversation.current_topics:
            print(f"🧠 Current Context: {chatbot.conversation.current_topics}")
        
        print("-" * 60)
    
    print("\n✅ Conversation test completed!")

if __name__ == "__main__":
    test_conversation()