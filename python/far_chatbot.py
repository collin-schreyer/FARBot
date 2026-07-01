#!/usr/bin/env python3
"""
FAR Chatbot - A RAG-based chatbot that searches Federal Acquisition Regulation documents
and provides responses with proper citations.
"""

import os
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from openai import OpenAI
from typing import List, Tuple, Dict, Optional
import logging
import argparse
from dotenv import load_dotenv
import re
from dataclasses import dataclass
from datetime import datetime

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

@dataclass
class ConversationTurn:
    """Represents a single turn in the conversation"""
    query: str
    response: str
    topics: List[str]
    far_sections: List[str]
    timestamp: datetime
    
class ConversationContext:
    """Manages conversation history and context"""
    
    def __init__(self):
        self.turns: List[ConversationTurn] = []
        self.current_topics: List[str] = []
        self.mentioned_sections: List[str] = []
        
    def add_turn(self, query: str, response: str, topics: List[str], far_sections: List[str]):
        """Add a new conversation turn"""
        turn = ConversationTurn(
            query=query,
            response=response,
            topics=topics,
            far_sections=far_sections,
            timestamp=datetime.now()
        )
        self.turns.append(turn)
        
        # Update current context (keep last 3 turns for active context)
        recent_turns = self.turns[-3:]
        self.current_topics = []
        self.mentioned_sections = []
        
        for turn in recent_turns:
            self.current_topics.extend(turn.topics)
            self.mentioned_sections.extend(turn.far_sections)
            
        # Remove duplicates while preserving order
        self.current_topics = list(dict.fromkeys(self.current_topics))
        self.mentioned_sections = list(dict.fromkeys(self.mentioned_sections))
        
    def get_context_for_query(self, query: str) -> str:
        """Get relevant context for resolving ambiguous queries"""
        if not self.turns:
            return query
            
        # Check for reference words that need context
        reference_words = ['this', 'that', 'these', 'those', 'it', 'they', 'them']
        query_lower = query.lower()
        
        needs_context = any(word in query_lower for word in reference_words)
        
        if needs_context and self.current_topics:
            # Add context from recent topics
            context = f"In the context of {', '.join(self.current_topics[:2])}: {query}"
            return context
            
        return query
        
    def get_last_topic(self) -> Optional[str]:
        """Get the most recent topic discussed"""
        return self.current_topics[0] if self.current_topics else None
        
    def generate_follow_up_suggestions(self, current_topics: List[str]) -> List[str]:
        """Generate contextual follow-up questions"""
        suggestions = []
        
        if not current_topics:
            return suggestions
            
        # Topic-specific follow-up patterns
        follow_up_patterns = {
            'small business': [
                "What are the eligibility requirements?",
                "How do I apply for small business certification?",
                "What documentation is required?"
            ],
            'sole source': [
                "What justification is required?",
                "What are the approval processes?",
                "When is sole source procurement allowed?"
            ],
            'protest': [
                "What are the protest deadlines?",
                "How do I file a bid protest?",
                "What happens during the protest process?"
            ],
            'threshold': [
                "What are the current dollar amounts?",
                "How do thresholds affect procurement procedures?",
                "What happens above/below the threshold?"
            ],
            'cost accounting': [
                "Which contracts require CAS coverage?",
                "What are the disclosure requirements?",
                "How do I ensure CAS compliance?"
            ]
        }
        
        # Generate suggestions based on current topics
        for topic in current_topics[:2]:  # Focus on top 2 topics
            topic_lower = topic.lower()
            for pattern_key, pattern_suggestions in follow_up_patterns.items():
                if pattern_key in topic_lower:
                    suggestions.extend(pattern_suggestions[:2])  # Max 2 per topic
                    break
                    
        # Generic follow-ups if no specific patterns match
        if not suggestions:
            suggestions = [
                "Can you explain this in more detail?",
                "What are the key requirements?",
                "Are there any exceptions or special cases?"
            ]
            
        return suggestions[:3]  # Return max 3 suggestions

class FARChatbot:
    def __init__(self, 
                 faiss_index_path: str,
                 texts_path: str,
                 model_name: str = 'paraphrase-MiniLM-L6-v2',
                 openai_api_key: str = None,
                 use_gpt5: bool = True):
        """
        Initialize the FAR Chatbot with GPT-5 optimization
        
        Args:
            faiss_index_path: Path to the FAISS index file
            texts_path: Path to the texts file
            model_name: SentenceTransformer model name
            openai_api_key: OpenAI API key (optional, will try env var)
            use_gpt5: Whether to use GPT-5 for enhanced context handling
        """
        logging.info("🚀 Initializing FARChatbot...")
        logging.info(f"📍 FAISS index path: {faiss_index_path}")
        logging.info(f"📄 Texts path: {texts_path}")
        logging.info(f"🤖 Model name: {model_name}")
        logging.info(f"⚡ GPT-5 enabled: {use_gpt5}")
        
        logging.info("🔄 Loading SentenceTransformer model...")
        self.model = SentenceTransformer(model_name)
        logging.info("✅ SentenceTransformer model loaded successfully")
        
        self.faiss_index = None
        self.texts = []
        self.conversation = ConversationContext()
        self.use_gpt5 = use_gpt5
        
        # Load FAISS index and texts
        logging.info("📚 Loading FAISS index and texts...")
        self.load_index(faiss_index_path)
        self.load_texts(texts_path)
        
        # Setup OpenAI client
        logging.info("🔑 Setting up OpenAI client...")
        api_key = openai_api_key or os.getenv('OPENAI_API_KEY')
        if api_key:
            self.openai_client = OpenAI(api_key=api_key)
            logging.info(f"✅ OpenAI client initialized successfully (GPT-5: {use_gpt5})")
        else:
            self.openai_client = None
            logging.warning("⚠️ No OpenAI API key provided. Using retrieval-only mode.")
            
        logging.info("🎉 FARChatbot initialization complete!")
            
    def load_index(self, index_path: str):
        """Load the FAISS index"""
        logging.info(f"🔍 Loading FAISS index from {index_path}")
        
        if not os.path.exists(index_path):
            raise FileNotFoundError(f"❌ FAISS index file not found: {index_path}")
            
        file_size = os.path.getsize(index_path) / (1024 * 1024)  # MB
        logging.info(f"📊 FAISS index file size: {file_size:.1f} MB")
        
        logging.info("⏳ Reading FAISS index (this may take a moment)...")
        self.faiss_index = faiss.read_index(index_path)
        logging.info(f"✅ FAISS index loaded successfully with {self.faiss_index.ntotal} vectors")
        
    def load_texts(self, texts_path: str):
        """Load the corresponding texts"""
        logging.info(f"📄 Loading texts from {texts_path}")
        
        if not os.path.exists(texts_path):
            raise FileNotFoundError(f"❌ Texts file not found: {texts_path}")
            
        file_size = os.path.getsize(texts_path) / (1024 * 1024)  # MB
        logging.info(f"📊 Texts file size: {file_size:.1f} MB")
        
        logging.info("⏳ Reading texts file...")
        with open(texts_path, 'r', encoding='utf-8') as f:
            self.texts = [line.strip() for line in f.readlines()]
        logging.info(f"✅ Loaded {len(self.texts)} texts successfully")
        
    def extract_topics_from_query(self, query: str) -> List[str]:
        """Extract main topics from a query for conversation tracking"""
        topics = []
        query_lower = query.lower()
        
        # Topic patterns to identify
        topic_patterns = {
            'small business set-asides': ['small business', 'set-aside', 'sdvosb', 'wosb', 'hubzone'],
            'sole source procurement': ['sole source', 'noncompetitive', 'single source', 'other than full and open'],
            'bid protests': ['protest', 'bid protest', 'award protest', 'gao protest'],
            'simplified acquisition threshold': ['simplified acquisition', 'sat', 'threshold'],
            'cost accounting standards': ['cost accounting', 'cas', 'casb'],
            'contract modifications': ['modification', 'change order', 'supplemental agreement'],
            'termination procedures': ['termination', 'default', 'convenience'],
            'gsa schedules': ['gsa schedule', 'federal supply schedule', 'fss', 'mas'],
            'micro-purchase procedures': ['micro-purchase', 'micropurchase', 'small purchase']
        }
        
        for topic, keywords in topic_patterns.items():
            if any(keyword in query_lower for keyword in keywords):
                topics.append(topic)
                
        return topics
    
    def expand_query(self, query: str, use_context: bool = True) -> str:
        """Expand query with synonyms, related terms, and conversation context"""
        # First, resolve context if needed
        if use_context:
            contextual_query = self.conversation.get_context_for_query(query)
        else:
            contextual_query = query
            
        query_lower = contextual_query.lower()
        
        # Handle "tell me more" type queries
        if any(phrase in query_lower for phrase in ['tell me more', 'more details', 'elaborate', 'explain further']):
            last_topic = self.conversation.get_last_topic()
            if last_topic:
                contextual_query = f"detailed information about {last_topic} {contextual_query}"
        
        # Common FAR term expansions
        expansions = {
            "sole source": " sole source noncompetitive single source other than full and open competition",
            "protest": " protest bid protest award protest GAO protest agency protest",
            "threshold": " threshold dollar limit acquisition threshold procurement limit",
            "small business": " small business SB small business concern set-aside SDVOSB WOSB HUBZone",
            "simplified acquisition": " simplified acquisition SAT simplified procedures",
            "micro-purchase": " micro-purchase micropurchase small purchase",
            "cost accounting": " cost accounting standards CAS CASB",
            "GSA schedule": " GSA schedule federal supply schedule FSS multiple award schedule MAS",
            "contract modification": " contract modification change order supplemental agreement",
            "termination": " termination default cure notice stop work"
        }
        
        expanded_query = contextual_query
        for term, expansion in expansions.items():
            if term in query_lower:
                expanded_query += expansion
                
        return expanded_query
    
    def classify_query_complexity(self, query: str) -> Dict[str, any]:
        """Classify query to determine optimal search and response strategy"""
        query_lower = query.lower()
        
        # Query type classification
        query_type = "general"
        if any(word in query_lower for word in ["what is", "define", "definition", "meaning"]):
            query_type = "definition"
        elif any(word in query_lower for word in ["how do", "how to", "process", "procedure", "steps"]):
            query_type = "process"
        elif any(word in query_lower for word in ["when", "timeline", "deadline", "timeframe"]):
            query_type = "timing"
        elif any(word in query_lower for word in ["compare", "difference", "versus", "vs"]):
            query_type = "comparison"
        elif any(word in query_lower for word in ["tell me everything", "comprehensive", "complete guide"]):
            query_type = "comprehensive"
        elif any(word in query_lower for word in ["tell me more", "elaborate", "details"]):
            query_type = "elaboration"
        
        # Complexity scoring
        complexity_score = 0
        
        # Length-based complexity
        if len(query.split()) > 10:
            complexity_score += 2
        elif len(query.split()) > 5:
            complexity_score += 1
            
        # Topic complexity
        complex_topics = ["cost accounting", "protest", "termination", "modification", "competition"]
        if any(topic in query_lower for topic in complex_topics):
            complexity_score += 2
            
        # Multi-part questions
        if any(word in query_lower for word in ["and", "also", "additionally", "furthermore"]):
            complexity_score += 1
            
        # Determine search parameters - always use maximum context for best results
        if self.use_gpt5:
            # GPT-4 Turbo: Always use 50 chunks for comprehensive coverage
            if query_type == "comprehensive":
                search_params = {"top_k": 50, "max_tokens": 4000}
            elif query_type == "process":
                search_params = {"top_k": 50, "max_tokens": 2500}
            elif query_type == "comparison":
                search_params = {"top_k": 50, "max_tokens": 3000}
            elif query_type == "elaboration":
                search_params = {"top_k": 50, "max_tokens": 2000}
            else:
                # Even simple queries get full context for completeness
                search_params = {"top_k": 50, "max_tokens": 1500}
        else:
            # GPT-3.5: Conservative approach due to smaller context window
            if complexity_score >= 2:
                search_params = {"top_k": 10, "max_tokens": 1000}
            else:
                search_params = {"top_k": 7, "max_tokens": 800}
        
        return {
            "type": query_type,
            "complexity": complexity_score,
            "search_params": search_params
        }
    
    def search_similar(self, query: str, top_k: int = None, use_context: bool = True) -> List[Tuple[str, float]]:
        """
        Enhanced search with dynamic context loading for GPT-5
        
        Args:
            query: User query
            top_k: Number of top results to return (auto-determined if None)
            use_context: Whether to use conversation context for search
            
        Returns:
            List of (text, similarity_score) tuples
        """
        # Classify query to determine optimal parameters
        query_analysis = self.classify_query_complexity(query)
        if top_k is None:
            top_k = query_analysis["search_params"]["top_k"]
        
        # Expand and encode the query with context
        expanded_query = self.expand_query(query, use_context)
        query_embedding = self.model.encode([expanded_query])
        
        # For GPT-5, search much wider initially
        initial_search_k = min(top_k * 2, 100) if self.use_gpt5 else min(top_k + 3, 15)
        
        # Search in FAISS index
        distances, indices = self.faiss_index.search(query_embedding.astype('float32'), initial_search_k)
        
        # Get the results
        results = []
        for i, (distance, idx) in enumerate(zip(distances[0], indices[0])):
            if idx < len(self.texts):
                # Convert L2 distance to similarity score (higher is better)
                similarity = 1 / (1 + distance)
                results.append((self.texts[idx], similarity))
        
        # Enhanced context blending for follow-up questions
        if use_context and self.conversation.turns:
            # Boost results that contain sections mentioned in recent conversation
            for i, (text, score) in enumerate(results):
                boost_factor = 1.0
                
                # Strong boost for recently mentioned sections
                for section in self.conversation.mentioned_sections[-2:]:
                    if section in text:
                        boost_factor *= 1.3
                
                # Moderate boost for current topics
                for topic in self.conversation.current_topics[:2]:
                    topic_keywords = topic.lower().split()
                    if any(keyword in text.lower() for keyword in topic_keywords):
                        boost_factor *= 1.1
                
                results[i] = (text, score * boost_factor)
        
        # Add comprehensive definitional context for GPT-5
        query_lower = expanded_query.lower()
        
        # Add definitions for threshold/dollar queries
        threshold_terms = ["threshold", "dollar", "limit", "$", "amount", "value"]
        if any(term in query_lower for term in threshold_terms):
            definition_results = []
            for i, text in enumerate(self.texts):
                if "2.101" in text and any(term in text.lower() for term in ["definition", "means", "threshold"]):
                    definition_results.append((text, 0.040))
            results.extend(definition_results[:3])  # Add top 3 definition sections
        
        # Add cross-references for complex topics
        if self.use_gpt5 and query_analysis["complexity"] >= 2:
            # Look for related sections based on current results
            mentioned_sections = set()
            for text, _ in results[:10]:
                # Extract section numbers from text
                section_matches = re.findall(r'\b\d+\.\d+(?:-\d+)?\b', text)
                mentioned_sections.update(section_matches)
            
            # Find cross-referenced sections
            cross_ref_results = []
            for section in list(mentioned_sections)[:5]:  # Limit to avoid explosion
                for i, text in enumerate(self.texts):
                    if section in text and not any(section in result[0] for result in results):
                        cross_ref_results.append((text, 0.025))
                        if len(cross_ref_results) >= 5:
                            break
            results.extend(cross_ref_results)
        
        # Sort by similarity and return top_k
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]
        
    def extract_citation(self, text: str) -> str:
        """Extract FAR citation from text"""
        # The text format is "Section Title Content..."
        # Extract the section number/title for citation
        parts = text.split(' ', 2)
        if len(parts) >= 2:
            return parts[0]  # e.g., "32.606"
        return "FAR"
        
    def extract_far_sections(self, texts: List[str]) -> List[str]:
        """Extract FAR section numbers from a list of texts"""
        sections = []
        for text in texts:
            citation = self.extract_citation(text)
            if citation != "FAR":
                sections.append(citation)
        return sections
        
    def generate_response_with_citations(self, query: str, context_texts: List[str], query_analysis: Dict[str, any]) -> str:
        """
        Generate a response using OpenAI with dynamic token allocation and enhanced prompting
        
        Args:
            query: User query
            context_texts: Relevant FAR texts for context
            query_analysis: Query classification and parameters
            
        Returns:
            Generated response with citations
        """
        if not self.openai_client:
            return self.generate_simple_response(query, context_texts)
        
        # Prepare comprehensive context with citations
        context_with_citations = []
        for i, text in enumerate(context_texts):
            citation = self.extract_citation(text)
            context_with_citations.append(f"[{citation}] {text}")
        
        context = "\n\n".join(context_with_citations)
        
        # Enhanced conversation context
        conversation_context = ""
        if self.conversation.turns:
            recent_topics = ", ".join(self.conversation.current_topics[:3])
            recent_sections = ", ".join(self.conversation.mentioned_sections[-5:])
            conversation_context = f"""
Previous conversation context:
- Current topics: {recent_topics}
- Recently discussed sections: {recent_sections}
- This is a follow-up question in an ongoing conversation about FAR regulations.
"""
        
        # Dynamic prompting based on query type
        query_type = query_analysis["type"]
        max_tokens = query_analysis["search_params"]["max_tokens"]
        
        if query_type == "definition":
            instruction_focus = "Provide clear, precise definitions with specific regulatory criteria and requirements."
        elif query_type == "process":
            instruction_focus = "Explain the complete step-by-step process, including all required actions, timelines, and responsible parties."
        elif query_type == "comparison":
            instruction_focus = "Compare and contrast the different approaches, highlighting key differences, similarities, and when each applies."
        elif query_type == "comprehensive":
            instruction_focus = "Provide a comprehensive guide covering all aspects, including background, requirements, procedures, exceptions, and practical considerations."
        elif query_type == "elaboration":
            instruction_focus = "Build upon the previous discussion with additional detail, examples, and related considerations."
        else:
            instruction_focus = "Provide a thorough, practical answer that addresses all aspects of the question."
        
        # Model selection and prompting (use GPT-4 Turbo for now since GPT-5 may not be available)
        model = "gpt-4-turbo" if self.use_gpt5 else "gpt-3.5-turbo"
        
        system_prompt = f"""You are an expert Federal Acquisition Regulation (FAR) consultant with deep knowledge of government contracting. You provide authoritative, practical guidance based on current FAR regulations.

Query Type: {query_type.title()}
Response Focus: {instruction_focus}

Key Principles:
1. Always cite specific FAR sections using [Section] format
2. Provide practical, actionable guidance
3. Explain the regulatory rationale behind requirements
4. Include relevant exceptions, special cases, and cross-references
5. Use clear, professional language appropriate for contracting professionals
6. When multiple sections apply, organize information logically
7. If information is incomplete, clearly state what additional research may be needed"""

        user_prompt = f"""{conversation_context}

FAR Context (Comprehensive):
{context}

User Question: {query}

Please provide a thorough, well-organized response that fully addresses the question using the FAR context provided. Include all relevant citations and practical guidance."""

        try:
            # Use appropriate parameters based on model
            response = self.openai_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=max_tokens,
                temperature=0.2
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logging.error(f"OpenAI API error: {e}")
            if self.use_gpt5:
                # Fallback to GPT-3.5 if GPT-5 fails
                logging.info("Falling back to GPT-3.5-turbo")
                try:
                    response = self.openai_client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        max_tokens=min(max_tokens, 1000),  # Cap for GPT-3.5
                        temperature=0.2
                    )
                    return response.choices[0].message.content.strip()
                except Exception as e2:
                    logging.error(f"GPT-3.5 fallback also failed: {e2}")
            
            logging.info("Falling back to simple response mode")
            return self.generate_simple_response(query, context_texts)
            
    def generate_simple_response(self, query: str, context_texts: List[str]) -> str:
        """
        Generate a comprehensive response without OpenAI (fallback)
        """
        # Analyze query to provide better context
        query_lower = query.lower()
        query_type = "general"
        
        if any(word in query_lower for word in ["how", "process", "procedure", "steps"]):
            query_type = "process"
        elif any(word in query_lower for word in ["what", "definition", "meaning", "requirements"]):
            query_type = "definition"
        elif any(word in query_lower for word in ["when", "timeline", "deadline"]):
            query_type = "timing"
        
        # Start response based on query type
        if query_type == "process":
            response = f"**Process for '{query}':**\n\n"
        elif query_type == "definition":
            response = f"**Definition and Requirements for '{query}':**\n\n"
        elif query_type == "timing":
            response = f"**Timeline and Deadlines for '{query}':**\n\n"
        else:
            response = f"**Information about '{query}':**\n\n"
        
        # Process each relevant section
        for i, text in enumerate(context_texts[:3], 1):
            citation = self.extract_citation(text)
            
            # Show more comprehensive text
            if len(text) > 1200:
                # Try to break at a sentence boundary
                truncated = text[:1200]
                last_period = truncated.rfind('.')
                if last_period > 900:  # If we find a period reasonably close to the end
                    display_text = text[:last_period + 1]
                else:
                    display_text = truncated + "..."
            else:
                display_text = text
                
            response += f"**{i}. FAR Section {citation}:**\n{display_text}\n\n"
            
        # Add contextual summary based on query type
        response += "---\n\n**Key Takeaways:**\n"
        
        if query_type == "process":
            response += "• Follow the procedures outlined in the above FAR sections\n"
            response += "• Ensure all required documentation and approvals are obtained\n"
            response += "• Pay attention to specific timelines and notification requirements\n"
        elif query_type == "definition":
            response += "• Review the specific definitions and criteria in the referenced sections\n"
            response += "• Ensure compliance with all stated requirements\n"
            response += "• Consider any exceptions or special circumstances that may apply\n"
        elif query_type == "timing":
            response += "• Note all deadlines and timeline requirements\n"
            response += "• Plan accordingly to meet all specified timeframes\n"
            response += "• Consider any factors that might affect timing\n"
        else:
            response += "• Review all applicable FAR sections for complete guidance\n"
            response += "• Ensure compliance with federal acquisition regulations\n"
            response += "• Consult with legal or procurement experts for complex situations\n"
            
        response += "\n*For complete details and any additional context, please refer to the full FAR text and consult with procurement professionals.*"
        
        return response
        
    def chat(self, query: str, top_k: int = None) -> Dict[str, any]:
        """
        Enhanced chat function with GPT-5 optimization and dynamic context loading
        
        Args:
            query: User query
            top_k: Number of documents to retrieve (auto-determined if None)
            
        Returns:
            Dictionary containing response, suggestions, metadata, and analysis
        """
        logging.info(f"Processing query: {query}")
        
        # Analyze query complexity and determine optimal parameters
        query_analysis = self.classify_query_complexity(query)
        logging.info(f"Query analysis: {query_analysis['type']} (complexity: {query_analysis['complexity']})")
        
        # Extract topics from the query
        topics = self.extract_topics_from_query(query)
        
        # Search for relevant documents with dynamic context loading
        if top_k is None:
            top_k = query_analysis["search_params"]["top_k"]
        
        results = self.search_similar(query, top_k, use_context=True)
        
        if not results:
            return {
                "response": "I couldn't find any relevant information in the FAR documents. Please try rephrasing your question.",
                "suggestions": [],
                "topics": topics,
                "sections": [],
                "query_analysis": query_analysis
            }
        
        logging.info(f"Retrieved {len(results)} context chunks for {query_analysis['type']} query")
        
        # Extract texts for context
        context_texts = [text for text, _ in results]
        far_sections = self.extract_far_sections(context_texts)
        
        # Generate enhanced response with dynamic token allocation
        response = self.generate_response_with_citations(query, context_texts, query_analysis)
        
        # Generate contextual follow-up suggestions
        all_topics = topics + self.conversation.current_topics
        suggestions = self.conversation.generate_follow_up_suggestions(all_topics)
        
        # Add this turn to conversation history
        self.conversation.add_turn(query, response, topics, far_sections)
        
        return {
            "response": response,
            "suggestions": suggestions,
            "topics": topics,
            "sections": far_sections,
            "search_results": [(self.extract_citation(text), text) for text, _ in results[:5]],
            "query_analysis": query_analysis,
            "context_size": len(context_texts),
            "model_used": "gpt-4-turbo" if self.use_gpt5 else "gpt-3.5-turbo"
        }
        
    def interactive_chat(self):
        """Start an interactive chat session"""
        print("🏛️  FAR Chatbot - Federal Acquisition Regulation Assistant")
        print("Ask me anything about federal acquisition regulations!")
        print("Type 'quit' or 'exit' to end the conversation.\n")
        
        while True:
            try:
                query = input("You: ").strip()
                
                if query.lower() in ['quit', 'exit', 'bye']:
                    print("Goodbye! 👋")
                    break
                    
                if not query:
                    continue
                    
                print("🤖 Searching FAR documents...")
                result = self.chat(query)
                print(f"\nFAR Bot: {result['response']}\n")
                
                # Show enhanced metadata
                analysis = result.get('query_analysis', {})
                print(f"📊 Query Analysis: {analysis.get('type', 'general').title()} (Complexity: {analysis.get('complexity', 0)})")
                print(f"🔍 Context: {result.get('context_size', 0)} chunks | Model: {result.get('model_used', 'unknown')}")
                
                # Show follow-up suggestions
                if result['suggestions']:
                    print("\n💡 You might also want to ask:")
                    for i, suggestion in enumerate(result['suggestions'], 1):
                        print(f"   {i}. {suggestion}")
                    print()
                
                print("-" * 80)
                
            except KeyboardInterrupt:
                print("\n\nGoodbye! 👋")
                break
            except Exception as e:
                print(f"Error: {e}")
                logging.error(f"Chat error: {e}")


def main():
    import os
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Default paths relative to project root
    default_index = os.path.join(script_dir, '..', 'dita_html', 'faiss_index.index')
    default_texts = os.path.join(script_dir, '..', 'dita_html', 'texts.txt')
    
    parser = argparse.ArgumentParser(description='FAR Chatbot')
    parser.add_argument('--faiss-index', 
                       default=default_index,
                       help='Path to FAISS index file')
    parser.add_argument('--texts', 
                       default=default_texts,
                       help='Path to texts file')
    parser.add_argument('--query', 
                       help='Single query mode (non-interactive)')
    parser.add_argument('--top-k', type=int, default=5,
                       help='Number of documents to retrieve')
    
    args = parser.parse_args()
    
    # Initialize chatbot
    try:
        chatbot = FARChatbot(
            faiss_index_path=args.faiss_index,
            texts_path=args.texts
        )
        
        if args.query:
            # Single query mode
            result = chatbot.chat(args.query, args.top_k)
            print(result['response'])
        else:
            # Interactive mode
            chatbot.interactive_chat()
            
    except Exception as e:
        logging.error(f"Failed to initialize chatbot: {e}")
        print(f"Error: {e}")


if __name__ == "__main__":
    main()