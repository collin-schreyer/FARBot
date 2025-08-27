# FAR Chatbot 🏛️
*Federal Acquisition Regulation Assistant with AI-Powered Search*

---

## 🎯 High-Level Overview (Executive Summary)

The FAR Chatbot is an **intelligent assistant** that helps government procurement professionals navigate the complex Federal Acquisition Regulation (FAR). Instead of manually searching through thousands of pages of regulations, users can ask natural language questions and receive accurate, cited answers in seconds.

**What it does:**
- Answers questions about federal procurement regulations
- Provides proper citations to specific FAR sections
- Explains complex regulatory concepts in plain language
- Maintains conversation context for follow-up questions

**Key Benefits:**
- ⚡ **Fast**: Get answers in 2-5 seconds vs. hours of manual research
- 🎯 **Accurate**: AI-powered search with proper regulatory citations
- 💬 **Conversational**: Ask follow-up questions naturally
- 📱 **Accessible**: Web interface works on any device

**Perfect for:** Contracting officers, procurement specialists, vendors, legal teams, and anyone working with federal acquisitions.

---

## 🔧 Mid-Level Technical Overview

### Architecture & Components

The FAR Chatbot uses a **Retrieval-Augmented Generation (RAG)** architecture that combines:

1. **Semantic Search Engine**: Finds relevant FAR sections using AI embeddings
2. **Vector Database**: FAISS index with 3,893 pre-processed FAR sections
3. **Language Model**: OpenAI GPT-4 Turbo for generating comprehensive responses
4. **Web Interface**: Streamlit-based chat UI with conversation history

### How It Works (5-Step Process)

```
User Question → Query Analysis → Semantic Search → Context Assembly → AI Response → Cited Answer
```

1. **Query Analysis**: Classifies question type (definition, process, comparison, etc.)
2. **Semantic Search**: Uses SentenceTransformers to find 50 most relevant FAR sections
3. **Context Assembly**: Combines relevant sections with conversation history
4. **AI Response**: GPT-4 Turbo generates comprehensive answer with citations
5. **Cited Answer**: Returns formatted response with proper FAR section references

### Key Features

- **Smart Context Loading**: Dynamically adjusts search depth based on query complexity
- **Conversation Memory**: Tracks topics and sections for contextual follow-ups
- **Query Expansion**: Automatically adds synonyms and related regulatory terms
- **Citation Extraction**: Identifies and formats FAR section references
- **Follow-up Suggestions**: Generates relevant next questions based on conversation

### Technology Stack

- **Embeddings**: SentenceTransformer (paraphrase-MiniLM-L6-v2)
- **Vector Database**: FAISS with L2 distance similarity
- **Language Model**: OpenAI GPT-4 Turbo (256k context window)
- **Backend**: Python with sentence-transformers, faiss-cpu, openai
- **Frontend**: Streamlit web framework
- **Data**: 3,893 processed FAR sections from official DITA HTML

---

## ⚙️ Low-Level Implementation Details

### Data Processing Pipeline

#### 1. Document Ingestion
The system processes FAR HTML files into searchable chunks:
```python
# Process FAR HTML files into searchable chunks
for html_file in far_html_files:
    text = extract_text_from_html(html_file)
    chunks = split_into_semantic_chunks(text, max_length=1000)
    embeddings = sentence_transformer.encode(chunks)
    faiss_index.add(embeddings)
```

#### 2. Vector Database Structure
- **Index Type**: FAISS IndexFlatL2 (exact L2 distance search)
- **Dimensions**: 384 (SentenceTransformer output size)
- **Total Vectors**: 3,893 FAR section embeddings
- **Storage**: Binary index file + corresponding text file

#### 3. Search Algorithm
The core search uses semantic similarity with context boosting:
```python
def search_similar(self, query: str, top_k: int = 50):
    # 1. Query expansion with regulatory synonyms
    expanded_query = self.expand_query(query)
    
    # 2. Encode query to vector
    query_embedding = self.model.encode([expanded_query])
    
    # 3. FAISS similarity search
    distances, indices = self.faiss_index.search(
        query_embedding.astype('float32'), top_k
    )
    
    # 4. Convert distances to similarity scores
    results = []
    for distance, idx in zip(distances[0], indices[0]):
        similarity = 1 / (1 + distance)  # Higher = more similar
        results.append((self.texts[idx], similarity))
    
    # 5. Context-aware result boosting
    if self.conversation.current_topics:
        results = self.boost_contextual_results(results)
    
    return results
```

#### 4. Response Generation
GPT-4 Turbo generates responses with dynamic token allocation:
```python
def generate_response_with_citations(self, query, context_texts, query_analysis):
    # Dynamic token allocation based on query complexity
    max_tokens = query_analysis["search_params"]["max_tokens"]
    
    # Prepare context with citations
    context_with_citations = []
    for text in context_texts:
        citation = self.extract_citation(text)  # e.g., "32.606"
        context_with_citations.append(f"[{citation}] {text}")
    
    # Enhanced system prompt based on query type
    system_prompt = self.build_dynamic_prompt(query_analysis["type"])
    
    # GPT-4 Turbo API call with conversation context
    response = self.openai_client.chat.completions.create(
        model="gpt-4-turbo",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context: {context}\nQuery: {query}"}
        ],
        max_tokens=max_tokens,
        temperature=0.2  # Low temperature for factual accuracy
    )
    
    return response.choices[0].message.content
```

### Conversation Context Management

The system maintains conversation state for contextual follow-ups:
```python
@dataclass
class ConversationTurn:
    query: str
    response: str
    topics: List[str]          # Extracted topics (e.g., "small business")
    far_sections: List[str]    # Referenced sections (e.g., "19.502")
    timestamp: datetime

class ConversationContext:
    def __init__(self):
        self.turns: List[ConversationTurn] = []
        self.current_topics: List[str] = []      # Last 3 turns
        self.mentioned_sections: List[str] = []  # Recently discussed
    
    def get_context_for_query(self, query: str) -> str:
        # Resolve ambiguous references like "this", "that", "it"
        if self.has_reference_words(query) and self.current_topics:
            return f"In context of {self.current_topics[0]}: {query}"
        return query
```

### Query Classification System

The system analyzes queries to optimize search and response generation:
```python
def classify_query_complexity(self, query: str) -> Dict:
    query_type = "general"
    
    # Pattern matching for query types
    if re.search(r'\b(what is|define|definition)\b', query, re.I):
        query_type = "definition"
    elif re.search(r'\b(how do|how to|process|procedure)\b', query, re.I):
        query_type = "process"
    elif re.search(r'\b(compare|difference|versus)\b', query, re.I):
        query_type = "comparison"
    
    # Complexity scoring
    complexity = 0
    complexity += len(query.split()) // 5  # Length factor
    complexity += 2 if any(term in query.lower() 
                          for term in ["cost accounting", "protest", "termination"])
    
    # Dynamic search parameters
    if query_type == "comprehensive":
        search_params = {"top_k": 50, "max_tokens": 4000}
    elif complexity >= 2:
        search_params = {"top_k": 50, "max_tokens": 2500}
    else:
        search_params = {"top_k": 50, "max_tokens": 1500}
    
    return {"type": query_type, "complexity": complexity, "search_params": search_params}
```

### Performance Optimizations

#### 1. Caching Strategy
- **Model Loading**: SentenceTransformer cached in memory
- **FAISS Index**: Loaded once at startup (50MB memory footprint)
- **Streamlit**: `@st.cache_resource` for chatbot initialization

#### 2. Search Optimizations
- **Query Expansion**: Pre-computed synonym mappings for FAR terms
- **Result Boosting**: Context-aware scoring for follow-up questions
- **Batch Processing**: Vectorize multiple queries simultaneously when possible

#### 3. Memory Management
```python
# Efficient vector operations
query_embedding = self.model.encode([query]).astype('float32')  # Explicit float32
distances, indices = self.faiss_index.search(query_embedding, top_k)

# Conversation history pruning (keep last 10 turns)
if len(self.conversation.turns) > 10:
    self.conversation.turns = self.conversation.turns[-10:]
```

### Error Handling & Fallbacks

The system includes robust error handling with multiple fallback strategies:
```python
def chat(self, query: str) -> Dict:
    try:
        # Primary: GPT-4 Turbo response
        response = self.generate_response_with_citations(query, context, analysis)
    except Exception as e:
        logging.error(f"GPT-4 failed: {e}")
        try:
            # Fallback 1: GPT-3.5 Turbo
            response = self.generate_gpt35_response(query, context)
        except Exception as e2:
            logging.error(f"GPT-3.5 failed: {e2}")
            # Fallback 2: Template-based response
            response = self.generate_simple_response(query, context)
    
    return {"response": response, "suggestions": suggestions, ...}
```

### File Structure & Data Flow

```
FAR_BOT/
├── dita_html/
│   ├── faiss_index.index      # 3,893 x 384 float32 vectors
│   ├── texts.txt              # Corresponding text chunks (1 per line)
│   └── chunks/                # Original processed HTML chunks
├── python/
│   ├── far_chatbot.py         # Core FARChatbot class (747 lines)
│   ├── streamlit_app.py       # Web UI with conversation management
│   └── vectorize_text.py      # Data processing pipeline
└── .env                       # OPENAI_API_KEY configuration
```

### API Integration Points

#### OpenAI API Usage
- **Model**: `gpt-4-turbo` (primary) with `gpt-3.5-turbo` fallback
- **Context Window**: Up to 256k tokens (50+ FAR sections)
- **Temperature**: 0.2 for factual accuracy
- **Max Tokens**: Dynamic allocation (1500-4000 based on query complexity)

#### Rate Limiting & Costs
- **Requests**: ~1 per user query
- **Token Usage**: 2000-8000 tokens per request (input + output)
- **Cost**: ~$0.02-0.08 per query at current OpenAI pricing

---

## 🏭 Production Deployment

### Moving to AWS Production Environment

The current development setup can be migrated to a production AWS environment with the following architecture changes:

#### 1. Database Migration: Local Files → DynamoDB

**Current State:**
- FAISS index: Local binary file (`faiss_index.index`)
- Text chunks: Local text file (`texts.txt`)
- Conversation history: In-memory storage

**Production Migration:**

```python
# DynamoDB Table Structure
FAR_VECTORS_TABLE = {
    "TableName": "far-vectors",
    "KeySchema": [
        {"AttributeName": "chunk_id", "KeyType": "HASH"}
    ],
    "AttributeDefinitions": [
        {"AttributeName": "chunk_id", "AttributeType": "S"}
    ],
    "BillingMode": "PAY_PER_REQUEST"
}

FAR_CONVERSATIONS_TABLE = {
    "TableName": "far-conversations", 
    "KeySchema": [
        {"AttributeName": "session_id", "KeyType": "HASH"},
        {"AttributeName": "timestamp", "KeyType": "RANGE"}
    ],
    "AttributeDefinitions": [
        {"AttributeName": "session_id", "AttributeType": "S"},
        {"AttributeName": "timestamp", "AttributeType": "S"}
    ],
    "BillingMode": "PAY_PER_REQUEST"
}
```

**Migration Script:**
```python
import boto3
import json
import numpy as np
from decimal import Decimal

def migrate_to_dynamodb():
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    
    # Create tables
    vectors_table = dynamodb.create_table(**FAR_VECTORS_TABLE)
    conversations_table = dynamodb.create_table(**FAR_CONVERSATIONS_TABLE)
    
    # Migrate FAISS vectors and texts
    faiss_index = faiss.read_index('faiss_index.index')
    with open('texts.txt', 'r') as f:
        texts = f.readlines()
    
    # Store vectors in DynamoDB (alternative: use Amazon OpenSearch)
    for i, text in enumerate(texts):
        vector = faiss_index.reconstruct(i)  # Get original vector
        
        vectors_table.put_item(Item={
            'chunk_id': str(i),
            'text_content': text.strip(),
            'vector': json.dumps(vector.tolist()),  # Store as JSON
            'far_section': extract_section_number(text),
            'created_at': datetime.utcnow().isoformat()
        })
```

#### 2. LLM Migration: OpenAI → GSAI GPT-5

**Current Configuration:**
```python
# Current OpenAI setup
self.openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
response = self.openai_client.chat.completions.create(
    model="gpt-4-turbo",
    messages=messages,
    max_tokens=max_tokens
)
```

**GSAI GPT-5 Integration:**
```python
import requests
import json

class GSAIClient:
    def __init__(self, endpoint_url, api_key):
        self.endpoint_url = endpoint_url
        self.api_key = api_key
        self.headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
    
    def chat_completions_create(self, model, messages, max_tokens, temperature=0.2):
        payload = {
            'model': model,
            'messages': messages,
            'max_tokens': max_tokens,
            'temperature': temperature
        }
        
        response = requests.post(
            f"{self.endpoint_url}/v1/chat/completions",
            headers=self.headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"GSAI API error: {response.status_code} - {response.text}")

# Updated FARChatbot initialization
def __init__(self, use_gsai=True):
    if use_gsai:
        self.llm_client = GSAIClient(
            endpoint_url=os.getenv('GSAI_ENDPOINT_URL'),
            api_key=os.getenv('GSAI_API_KEY')
        )
        self.model_name = "gpt-5"  # GSAI GPT-5 model
    else:
        # Fallback to OpenAI
        self.llm_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.model_name = "gpt-4-turbo"
```

#### 3. AWS Hosting Architecture

**Recommended Production Architecture:**

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   CloudFront    │────│   Application    │────│   Amazon        │
│   (CDN/WAF)     │    │   Load Balancer  │    │   OpenSearch    │
└─────────────────┘    └──────────────────┘    │   (Vector DB)   │
                                │               └─────────────────┘
                                │               
                       ┌──────────────────┐    ┌─────────────────┐
                       │   ECS Fargate    │────│   DynamoDB      │
                       │   (Streamlit)    │    │   (Metadata)    │
                       └──────────────────┘    └─────────────────┘
                                │               
                       ┌──────────────────┐    ┌─────────────────┐
                       │   Lambda         │────│   GSAI GPT-5    │
                       │   (API Gateway)  │    │   Endpoint      │
                       └──────────────────┘    └─────────────────┘
```

**Infrastructure as Code (Terraform):**
```hcl
# main.tf
resource "aws_ecs_cluster" "far_chatbot" {
  name = "far-chatbot-cluster"
  
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_service" "streamlit_app" {
  name            = "far-chatbot-streamlit"
  cluster         = aws_ecs_cluster.far_chatbot.id
  task_definition = aws_ecs_task_definition.streamlit.arn
  desired_count   = 2
  launch_type     = "FARGATE"
  
  network_configuration {
    subnets         = var.private_subnet_ids
    security_groups = [aws_security_group.ecs_tasks.id]
  }
  
  load_balancer {
    target_group_arn = aws_lb_target_group.streamlit.arn
    container_name   = "streamlit"
    container_port   = 8501
  }
}

resource "aws_opensearch_domain" "far_vectors" {
  domain_name    = "far-vectors"
  engine_version = "OpenSearch_2.3"
  
  cluster_config {
    instance_type  = "t3.small.search"
    instance_count = 2
  }
  
  ebs_options {
    ebs_enabled = true
    volume_size = 20
  }
}

resource "aws_dynamodb_table" "conversations" {
  name           = "far-conversations"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "session_id"
  range_key      = "timestamp"
  
  attribute {
    name = "session_id"
    type = "S"
  }
  
  attribute {
    name = "timestamp"
    type = "S"
  }
  
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}
```

#### 4. Container Configuration

**Dockerfile:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY python/ ./python/
COPY .env .

# Expose Streamlit port
EXPOSE 8501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Run Streamlit
CMD ["python", "-m", "streamlit", "run", "python/streamlit_app.py", \
     "--server.port=8501", "--server.address=0.0.0.0", \
     "--server.headless=true", "--server.enableCORS=false"]
```

**docker-compose.yml (for local testing):**
```yaml
version: '3.8'
services:
  far-chatbot:
    build: .
    ports:
      - "8501:8501"
    environment:
      - GSAI_ENDPOINT_URL=${GSAI_ENDPOINT_URL}
      - GSAI_API_KEY=${GSAI_API_KEY}
      - AWS_REGION=us-east-1
      - DYNAMODB_CONVERSATIONS_TABLE=far-conversations
      - OPENSEARCH_ENDPOINT=${OPENSEARCH_ENDPOINT}
    volumes:
      - ~/.aws:/root/.aws:ro
```

#### 5. Environment Configuration

**Production Environment Variables:**
```bash
# GSAI Configuration
GSAI_ENDPOINT_URL=https://api.gsai.gov/v1
GSAI_API_KEY=your_gsai_api_key

# AWS Configuration
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=123456789012

# DynamoDB Tables
DYNAMODB_CONVERSATIONS_TABLE=far-conversations
DYNAMODB_VECTORS_TABLE=far-vectors

# OpenSearch
OPENSEARCH_ENDPOINT=https://search-far-vectors-xxx.us-east-1.es.amazonaws.com

# Application Settings
ENVIRONMENT=production
LOG_LEVEL=INFO
MAX_CONCURRENT_REQUESTS=100
```

#### 6. Deployment Pipeline

**GitHub Actions Workflow (.github/workflows/deploy.yml):**
```yaml
name: Deploy FAR Chatbot

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Configure AWS credentials
      uses: aws-actions/configure-aws-credentials@v2
      with:
        aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
        aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
        aws-region: us-east-1
    
    - name: Build and push Docker image
      run: |
        aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com
        docker build -t far-chatbot .
        docker tag far-chatbot:latest $AWS_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/far-chatbot:latest
        docker push $AWS_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/far-chatbot:latest
    
    - name: Deploy to ECS
      run: |
        aws ecs update-service --cluster far-chatbot-cluster --service far-chatbot-streamlit --force-new-deployment
```

#### 7. Monitoring & Observability

**CloudWatch Integration:**
```python
import boto3
import logging
from datetime import datetime

class ProductionLogger:
    def __init__(self):
        self.cloudwatch = boto3.client('cloudwatch')
        
    def log_query_metrics(self, query_type, response_time, tokens_used):
        self.cloudwatch.put_metric_data(
            Namespace='FARChatbot',
            MetricData=[
                {
                    'MetricName': 'ResponseTime',
                    'Dimensions': [{'Name': 'QueryType', 'Value': query_type}],
                    'Value': response_time,
                    'Unit': 'Seconds'
                },
                {
                    'MetricName': 'TokensUsed',
                    'Value': tokens_used,
                    'Unit': 'Count'
                }
            ]
        )
```

#### 8. Security Considerations

**Production Security Checklist:**
- ✅ **API Keys**: Store in AWS Secrets Manager, not environment variables
- ✅ **Network**: Deploy in private subnets with NAT Gateway
- ✅ **WAF**: Configure AWS WAF rules for DDoS protection
- ✅ **IAM**: Use least-privilege IAM roles for ECS tasks
- ✅ **Encryption**: Enable encryption at rest for DynamoDB and OpenSearch
- ✅ **Logging**: Enable VPC Flow Logs and CloudTrail
- ✅ **Compliance**: Ensure FedRAMP compliance for government use

#### 9. Cost Optimization

**Estimated Monthly Costs (1000 queries/day):**
- ECS Fargate (2 tasks): ~$50/month
- DynamoDB (pay-per-request): ~$10/month
- OpenSearch (t3.small): ~$60/month
- ALB: ~$20/month
- GSAI GPT-5: Variable (government rates)
- **Total Infrastructure**: ~$140/month + GSAI costs

#### 10. Migration Checklist

**Pre-Migration:**
- [ ] Set up AWS accounts and IAM roles
- [ ] Obtain GSAI GPT-5 API access
- [ ] Create DynamoDB tables
- [ ] Set up OpenSearch domain
- [ ] Configure VPC and security groups

**Migration Steps:**
- [ ] Export current FAISS index and texts
- [ ] Run migration script to populate DynamoDB
- [ ] Update application code for GSAI integration
- [ ] Build and test Docker container
- [ ] Deploy infrastructure with Terraform
- [ ] Run integration tests
- [ ] Configure monitoring and alerts
- [ ] Perform load testing
- [ ] Go live with gradual traffic shift

This production architecture provides enterprise-grade scalability, security, and reliability suitable for government deployment while leveraging your existing AWS infrastructure and GSAI GPT-5 capabilities.

---

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Set Up Environment
Create a `.env` file with your OpenAI API key:
```
OPENAI_API_KEY=your_api_key_here
```

### 3. Launch Web UI
```bash
python run_chatbot_ui.py
```

The web interface will open at `http://localhost:8501`

## 💬 Sample Questions

- "What are small business set-asides?"
- "What is the simplified acquisition threshold?"
- "How do I protest a contract award?"
- "What are cost accounting standards?"
- "When can I use sole source procurement?"

## 🛠️ Command Line Usage

### Interactive Chat
```bash
cd python
python far_chatbot.py
```

### Single Query
```bash
cd python
python far_chatbot.py --query "What are small business set-asides?"
```

### Run Tests
```bash
cd python
python test_chatbot.py
```

---

This implementation provides a production-ready FAR assistance system with robust error handling, conversation context, and optimized performance for government procurement use cases.