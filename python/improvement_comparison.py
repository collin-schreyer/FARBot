#!/usr/bin/env python3
"""
Compare search improvements before and after optimization
"""

from far_chatbot import FARChatbot
import logging

def test_improvements():
    """Test the improvements made to search quality"""
    
    print("🔍 Testing Search Quality Improvements")
    print("="*60)
    
    chatbot = FARChatbot(
        faiss_index_path="/Users/collinschreyer/GSA/FAR_BOT/dita_html/faiss_index.index",
        texts_path="/Users/collinschreyer/GSA/FAR_BOT/dita_html/texts.txt"
    )
    
    # Test cases that were problematic before
    problem_queries = [
        {
            "query": "What is the simplified acquisition threshold?",
            "expected_improvement": "Should now find 2.101 definitions and better threshold info"
        },
        {
            "query": "When can I use sole source procurement?",
            "expected_improvement": "Should find 6.3xx sections with query expansion"
        },
        {
            "query": "How do I protest a contract award?",
            "expected_improvement": "Should find 33.103, 33.104 with better coverage"
        }
    ]
    
    for i, test_case in enumerate(problem_queries, 1):
        query = test_case["query"]
        expected = test_case["expected_improvement"]
        
        print(f"\n🔍 Test {i}: {query}")
        print(f"📈 Expected improvement: {expected}")
        print("-" * 50)
        
        # Test with new improved search (top_k=7)
        results = chatbot.search_similar(query, top_k=7)
        
        print("🎯 Top 7 Results with Improvements:")
        relevant_count = 0
        
        for j, (text, score) in enumerate(results, 1):
            citation = chatbot.extract_citation(text)
            preview = text[:150].replace('\n', ' ').strip()
            if len(text) > 150:
                preview += "..."
            
            # Check for key sections we expect
            is_relevant = False
            if "threshold" in query.lower():
                is_relevant = any(section in citation for section in ["13.5", "2.101", "13.003"])
            elif "sole source" in query.lower():
                is_relevant = any(section in citation for section in ["6.3", "15.002", "6.2"])
            elif "protest" in query.lower():
                is_relevant = any(section in citation for section in ["33.1", "33.2", "33.3"])
            
            if is_relevant:
                relevant_count += 1
                
            relevance_marker = "✅" if is_relevant else "❌"
            print(f"  {j}. {relevance_marker} [{citation}] (Score: {score:.4f})")
            print(f"     {preview}")
        
        print(f"\n📊 Relevant results: {relevant_count}/7 ({relevant_count/7*100:.1f}%)")
        
        # Test the full response
        print(f"\n🤖 Full Response:")
        response = chatbot.chat(query)
        print(response[:300] + "..." if len(response) > 300 else response)
        
        print("\n" + "="*60)

def test_query_expansion():
    """Test the query expansion feature"""
    
    print("\n🧠 Testing Query Expansion Feature")
    print("="*50)
    
    chatbot = FARChatbot(
        faiss_index_path="/Users/collinschreyer/GSA/FAR_BOT/dita_html/faiss_index.index",
        texts_path="/Users/collinschreyer/GSA/FAR_BOT/dita_html/texts.txt"
    )
    
    test_queries = [
        "sole source procurement",
        "small business set-asides", 
        "simplified acquisition threshold",
        "cost accounting standards",
        "GSA schedule"
    ]
    
    for query in test_queries:
        expanded = chatbot.expand_query(query)
        print(f"Original: {query}")
        print(f"Expanded: {expanded}")
        print("-" * 30)

if __name__ == "__main__":
    # Reduce logging noise
    logging.getLogger().setLevel(logging.WARNING)
    
    test_improvements()
    test_query_expansion()