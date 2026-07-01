#!/usr/bin/env python3
"""
Test script for the FAR Chatbot
"""

from far_chatbot import FARChatbot
import logging
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

def test_chatbot():
    """Test the chatbot with sample queries"""
    
    # Initialize chatbot
    print("🏛️ Initializing FAR Chatbot...")
    chatbot = FARChatbot(
        faiss_index_path="/Users/collinschreyer/GSA/FAR_BOT/dita_html/faiss_index.index",
        texts_path="/Users/collinschreyer/GSA/FAR_BOT/dita_html/texts.txt"
    )
    
    # Test queries
    test_queries = [
        "What are small business set-asides?",
        "How do contract modifications work?",
        "What is the process for bid protests?",
        "Tell me about cost accounting standards",
        "What are the requirements for competitive bidding?"
    ]
    
    print("\n" + "="*80)
    print("TESTING FAR CHATBOT")
    print("="*80)
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n🔍 Test Query {i}: {query}")
        print("-" * 60)
        
        try:
            # Test search functionality
            results = chatbot.search_similar(query, top_k=5)
            print(f"Found {len(results)} relevant documents:")
            
            for j, (text, score) in enumerate(results, 1):
                citation = chatbot.extract_citation(text)
                preview = text[:150] + "..." if len(text) > 150 else text
                print(f"  {j}. [{citation}] (Score: {score:.3f}) {preview}")
            
            # Test full chat response
            print(f"\n🤖 Chatbot Response:")
            response = chatbot.chat(query)
            print(response)
            
        except Exception as e:
            print(f"❌ Error: {e}")
        
        print("\n" + "-" * 80)
    
    print("\n✅ Testing completed!")

if __name__ == "__main__":
    test_chatbot()