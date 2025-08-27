#!/usr/bin/env python3
"""
Analyze search quality and chunk relevance for the FAR Chatbot
"""

from far_chatbot import FARChatbot
import logging

def analyze_search_results():
    """Analyze search results with different top_k values"""
    
    print("🔍 Initializing FAR Chatbot for Search Analysis...")
    chatbot = FARChatbot(
        faiss_index_path="/Users/collinschreyer/GSA/FAR_BOT/dita_html/faiss_index.index",
        texts_path="/Users/collinschreyer/GSA/FAR_BOT/dita_html/texts.txt"
    )
    
    # Test queries with expected relevant sections
    test_cases = [
        {
            "query": "What are small business set-asides?",
            "expected_sections": ["19.5", "52.219", "19.8"],
            "description": "Should find small business contracting sections"
        },
        {
            "query": "What is the simplified acquisition threshold?",
            "expected_sections": ["13.5", "2.101"],
            "description": "Should find SAT definition and simplified acquisition procedures"
        },
        {
            "query": "How do I protest a contract award?",
            "expected_sections": ["33.1", "33.2"],
            "description": "Should find protest procedures"
        },
        {
            "query": "What are the requirements for cost accounting standards?",
            "expected_sections": ["30.2", "52.230"],
            "description": "Should find CAS requirements and clauses"
        },
        {
            "query": "When can I use sole source procurement?",
            "expected_sections": ["6.3", "8.4"],
            "description": "Should find other than full and open competition procedures"
        }
    ]
    
    print("\n" + "="*100)
    print("SEARCH QUALITY ANALYSIS")
    print("="*100)
    
    for i, test_case in enumerate(test_cases, 1):
        query = test_case["query"]
        expected = test_case["expected_sections"]
        description = test_case["description"]
        
        print(f"\n🔍 Test Case {i}: {query}")
        print(f"📋 Expected: {description}")
        print(f"🎯 Looking for sections: {', '.join(expected)}")
        print("-" * 80)
        
        # Test with different top_k values
        for top_k in [3, 5, 10]:
            print(f"\n📊 TOP {top_k} RESULTS:")
            results = chatbot.search_similar(query, top_k=top_k)
            
            relevant_count = 0
            for j, (text, score) in enumerate(results, 1):
                citation = chatbot.extract_citation(text)
                
                # Check if this result matches expected sections
                is_relevant = any(exp in citation for exp in expected)
                if is_relevant:
                    relevant_count += 1
                
                relevance_marker = "✅" if is_relevant else "❌"
                
                # Show first 200 characters of text
                preview = text[:200].replace('\n', ' ').strip()
                if len(text) > 200:
                    preview += "..."
                
                print(f"  {j:2d}. {relevance_marker} [{citation}] (Score: {score:.4f})")
                print(f"      {preview}")
                print()
            
            print(f"      📈 Relevant results: {relevant_count}/{top_k} ({relevant_count/top_k*100:.1f}%)")
        
        print("\n" + "="*80)
    
    # Test semantic understanding
    print(f"\n🧠 SEMANTIC UNDERSTANDING TEST")
    print("="*80)
    
    semantic_tests = [
        ("What's the dollar limit for micro-purchases?", "Should find micro-purchase threshold"),
        ("How do I buy from GSA schedules?", "Should find GSA schedule procedures"),
        ("What paperwork do I need for a $50,000 contract?", "Should find documentation requirements"),
        ("Can I negotiate with vendors?", "Should find negotiation procedures"),
        ("What happens if a contractor doesn't perform?", "Should find default/termination procedures")
    ]
    
    for query, expectation in semantic_tests:
        print(f"\n🔍 Query: {query}")
        print(f"📋 Expected: {expectation}")
        
        results = chatbot.search_similar(query, top_k=5)
        print("🎯 Top 5 Results:")
        
        for j, (text, score) in enumerate(results, 1):
            citation = chatbot.extract_citation(text)
            preview = text[:150].replace('\n', ' ').strip()
            if len(text) > 150:
                preview += "..."
            
            print(f"  {j}. [{citation}] (Score: {score:.4f})")
            print(f"     {preview}")
        print()

def test_chunk_sizes():
    """Test how different numbers of chunks affect response quality"""
    
    print("\n🔬 CHUNK SIZE IMPACT ANALYSIS")
    print("="*80)
    
    chatbot = FARChatbot(
        faiss_index_path="/Users/collinschreyer/GSA/FAR_BOT/dita_html/faiss_index.index",
        texts_path="/Users/collinschreyer/GSA/FAR_BOT/dita_html/texts.txt"
    )
    
    test_query = "What are the requirements for small business set-asides?"
    
    for top_k in [3, 5, 7, 10]:
        print(f"\n📊 TESTING WITH {top_k} CHUNKS:")
        print("-" * 40)
        
        # Get search results
        results = chatbot.search_similar(test_query, top_k=top_k)
        context_texts = [text for text, _ in results]
        
        print("🔍 Retrieved chunks:")
        for i, (text, score) in enumerate(results, 1):
            citation = chatbot.extract_citation(text)
            print(f"  {i}. [{citation}] (Score: {score:.4f})")
        
        # Generate response
        print(f"\n🤖 Generated Response (using {top_k} chunks):")
        response = chatbot.generate_response_with_citations(test_query, context_texts)
        print(response[:500] + "..." if len(response) > 500 else response)
        print("\n" + "="*60)

if __name__ == "__main__":
    # Reduce logging noise
    logging.getLogger().setLevel(logging.WARNING)
    
    analyze_search_results()
    test_chunk_sizes()