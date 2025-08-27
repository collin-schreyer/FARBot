# FAR Chatbot Production Deployment Guide 🏭

## 🎯 Executive Overview

This document outlines the complete migration path from the current development FAR Chatbot to a production-ready system hosted on AWS using government-approved services including GSAI GPT-5, DynamoDB, and enterprise-grade infrastructure.

---

## 🏗️ Production Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              INTERNET / USERS                                   │
└─────────────────────────────┬───────────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────────────────────┐
│                         AWS CLOUDFRONT                                          │
│                    (CDN, Caching, WAF Protection)                              │
└─────────────────────────────┬───────────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────────────────────┐
│                    APPLICATION LOAD BALANCER                                    │
│                  (SSL Termination, Health Checks)                              │
└─────────────────────────────┬───────────────────────────────────────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │                   │
          ┌─────────▼─────────┐ ┌───────▼─────────┐
          │   ECS FARGATE     │ │   ECS FARGATE   │
          │   TASK 1          │ │   TASK 2        │
          │ ┌───────────────┐ │ │ ┌─────────────┐ │
          │ │  Streamlit    │ │ │ │ Streamlit   │ │
          │ │  Web App      │ │ │ │ Web App     │ │
          │ │  (Port 8501)  │ │ │ │(Port 8501)  │ │
          │ └───────────────┘ │ │ └─────────────┘ │
          └─────────┬─────────┘ └───────┬─────────┘
                    │                   │
                    └─────────┬─────────┘
                              │
              ┌───────────────▼───────────────┐
              │        API GATEWAY            │
              │     (Rate Limiting,           │
              │      Authentication)          │
              └───────────────┬───────────────┘
                              │
                    ┌─────────▼─────────┐
                    │                   │
          ┌─────────▼─────────┐ ┌───────▼─────────┐
          │   LAMBDA          │ │   LAMBDA        │
          │   FUNCTION        │ │   FUNCTION      │
          │ ┌───────────────┐ │ │ ┌─────────────┐ │
          │ │ FAR Chatbot   │ │ │ │ Conversation│ │
          │ │ Core Logic    │ │ │ │ Manager     │ │
          │ └───────────────┘ │ │ └─────────────┘ │
          └─────────┬─────────┘ └───────┬─────────┘
                    │                   │
                    └─────────┬─────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────────────────────┐
│                           DATA LAYER                                            │
│                                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐│
│  │   DYNAMODB      │  │   OPENSEARCH    │  │   S3 BUCKET     │  │ SECRETS     ││
│  │                 │  │                 │  │                 │  │ MANAGER     ││
│  │ • Conversations │  │ • Vector Index  │  │ • Static Assets │  │             ││
│  │ • User Sessions │  │ • FAR Sections  │  │ • Logs          │  │ • API Keys  ││
│  │ • Audit Logs    │  │ • Embeddings    │  │ • Backups       │  │ • Configs   ││
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  └─────────────┘│
└─────────────────────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────────────────────┐
│                        EXTERNAL SERVICES                                        │
│                                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                 │
│  │   GSAI GPT-5    │  │   CLOUDWATCH    │  │   AWS XRAY      │                 │
│  │                 │  │                 │  │                 │                 │
│  │ • LLM Endpoint  │  │ • Metrics       │  │ • Tracing       │                 │
│  │ • Gov Approved  │  │ • Logs          │  │ • Performance   │                 │
│  │ • High Security │  │ • Alerts        │  │ • Debugging     │                 │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🎯 High-Level Migration Strategy

### Phase 1: Infrastructure Setup (Weeks 1-2)
**Objective**: Establish AWS foundation and security framework

### Phase 2: Data Migration (Weeks 2-3)
**Objective**: Move vector database and implement new storage layer

### Phase 3: Application Migration (Weeks 3-4)
**Objective**: Containerize and deploy application with GSAI integration

### Phase 4: Testing & Optimization (Weeks 4-5)
**Objective**: Performance testing, security validation, and optimization

### Phase 5: Go-Live (Week 6)
**Objective**: Production deployment with monitoring and support

---

## 📋 Complete Migration Checklist

### 🔐 Pre-Migration Requirements

#### Security & Compliance
- [ ] **FedRAMP Authorization**: Ensure all AWS services are FedRAMP authorized
- [ ] **GSAI Access**: Obtain GSAI GPT-5 API credentials and endpoint access
- [ ] **Security Review**: Complete security assessment and ATO documentation
- [ ] **IAM Setup**: Create service accounts with least-privilege access
- [ ] **Encryption Keys**: Set up AWS KMS keys for data encryption
- [ ] **Network Security**: Design VPC with proper subnet isolation

#### AWS Account Setup
- [ ] **AWS Account**: Provision dedicated AWS account for production
- [ ] **Billing**: Set up cost monitoring and budget alerts
- [ ] **Regions**: Select primary (us-east-1) and backup (us-west-2) regions
- [ ] **Service Limits**: Request service limit increases if needed
- [ ] **Support Plan**: Ensure appropriate AWS support level

### 🏗️ Phase 1: Infrastructure Setup

#### Network Infrastructure
- [ ] **VPC Creation**: Create production VPC with CIDR planning
  ```bash
  # VPC: 10.0.0.0/16
  # Public Subnets: 10.0.1.0/24, 10.0.2.0/24
  # Private Subnets: 10.0.10.0/24, 10.0.20.0/24
  # Database Subnets: 10.0.100.0/24, 10.0.200.0/24
  ```
- [ ] **Internet Gateway**: Configure internet access for public subnets
- [ ] **NAT Gateways**: Set up NAT gateways for private subnet internet access
- [ ] **Route Tables**: Configure routing for all subnet types
- [ ] **Security Groups**: Create security groups with minimal required access
- [ ] **NACLs**: Configure network ACLs for additional security layer

#### Load Balancing & CDN
- [ ] **Application Load Balancer**: Deploy ALB in public subnets
- [ ] **Target Groups**: Configure health checks and routing rules
- [ ] **SSL Certificates**: Obtain and configure SSL certificates via ACM
- [ ] **CloudFront**: Set up CDN with WAF protection
- [ ] **Route 53**: Configure DNS and health checks

#### Container Infrastructure
- [ ] **ECS Cluster**: Create Fargate cluster for container orchestration
- [ ] **ECR Repository**: Set up container registry for application images
- [ ] **Task Definitions**: Define container specifications and resource limits
- [ ] **Service Definitions**: Configure auto-scaling and deployment strategies

### 🗄️ Phase 2: Data Layer Setup

#### DynamoDB Configuration
- [ ] **Conversations Table**: Create table for chat history
  ```python
  TableName: "far-conversations"
  PartitionKey: "session_id" (String)
  SortKey: "timestamp" (String)
  TTL: "expires_at" (7 days)
  Billing: Pay-per-request
  ```
- [ ] **User Sessions Table**: Create table for user session management
  ```python
  TableName: "far-user-sessions"
  PartitionKey: "user_id" (String)
  SortKey: "session_id" (String)
  GSI: "session_id-index"
  ```
- [ ] **Audit Logs Table**: Create table for compliance logging
  ```python
  TableName: "far-audit-logs"
  PartitionKey: "date" (String, YYYY-MM-DD)
  SortKey: "timestamp" (String)
  ```

#### OpenSearch Setup
- [ ] **Domain Creation**: Create OpenSearch domain for vector storage
  ```yaml
  Domain: far-vectors-prod
  Version: OpenSearch 2.3
  Instance: r6g.large.search (2 nodes)
  Storage: 100GB EBS per node
  Encryption: At rest and in transit
  ```
- [ ] **Index Mapping**: Define vector field mappings
  ```json
  {
    "mappings": {
      "properties": {
        "chunk_id": {"type": "keyword"},
        "vector": {"type": "dense_vector", "dims": 384},
        "text_content": {"type": "text"},
        "far_section": {"type": "keyword"},
        "created_at": {"type": "date"}
      }
    }
  }
  ```

#### S3 Configuration
- [ ] **Application Bucket**: Create bucket for static assets and logs
- [ ] **Backup Bucket**: Create bucket for data backups
- [ ] **Lifecycle Policies**: Configure data retention and archival
- [ ] **Versioning**: Enable versioning for critical data
- [ ] **Cross-Region Replication**: Set up backup region replication

### 🔄 Phase 3: Data Migration

#### Vector Database Migration
- [ ] **Export Current Data**: Extract FAISS index and text files
  ```python
  # Migration script
  python migrate_vectors_to_opensearch.py \
    --faiss-index faiss_index.index \
    --texts texts.txt \
    --opensearch-endpoint https://search-far-vectors.us-east-1.es.amazonaws.com
  ```
- [ ] **Batch Upload**: Upload vectors to OpenSearch in batches
- [ ] **Validation**: Verify data integrity and search functionality
- [ ] **Performance Testing**: Test search performance with production data

#### Conversation History Migration
- [ ] **Schema Design**: Design DynamoDB schema for conversation storage
- [ ] **Migration Script**: Create script to migrate existing conversations
- [ ] **Data Validation**: Verify migrated conversation data

### 🚀 Phase 4: Application Migration

#### GSAI Integration
- [ ] **API Client**: Implement GSAI GPT-5 client
  ```python
  class GSAIClient:
      def __init__(self, endpoint_url, api_key):
          self.endpoint_url = endpoint_url
          self.api_key = api_key
      
      def chat_completions_create(self, model, messages, max_tokens):
          # Implementation for GSAI API calls
  ```
- [ ] **Authentication**: Implement secure API key management
- [ ] **Error Handling**: Add robust error handling and fallbacks
- [ ] **Rate Limiting**: Implement client-side rate limiting

#### Application Containerization
- [ ] **Dockerfile**: Create optimized production Dockerfile
- [ ] **Multi-stage Build**: Implement multi-stage build for smaller images
- [ ] **Health Checks**: Add comprehensive health check endpoints
- [ ] **Logging**: Configure structured logging for CloudWatch
- [ ] **Metrics**: Add application metrics collection

#### Lambda Functions
- [ ] **Core Logic Lambda**: Migrate chatbot logic to Lambda
- [ ] **Conversation Manager**: Create Lambda for conversation management
- [ ] **Vector Search**: Create Lambda for OpenSearch queries
- [ ] **API Gateway**: Configure API Gateway with proper authentication

### 🔧 Phase 5: Configuration & Secrets

#### Secrets Management
- [ ] **GSAI Credentials**: Store GSAI API keys in Secrets Manager
- [ ] **Database Credentials**: Store database connection strings
- [ ] **Application Secrets**: Store application-specific secrets
- [ ] **Rotation Policies**: Set up automatic secret rotation

#### Environment Configuration
- [ ] **Parameter Store**: Configure application parameters
- [ ] **Environment Variables**: Set up environment-specific configurations
- [ ] **Feature Flags**: Implement feature flag system for gradual rollout

### 📊 Phase 6: Monitoring & Observability

#### CloudWatch Setup
- [ ] **Log Groups**: Create log groups for all services
- [ ] **Metrics**: Set up custom metrics for application performance
- [ ] **Dashboards**: Create operational dashboards
- [ ] **Alarms**: Configure alerts for critical metrics

#### X-Ray Tracing
- [ ] **Service Map**: Enable X-Ray tracing for request flow visibility
- [ ] **Performance Analysis**: Set up performance monitoring
- [ ] **Error Tracking**: Configure error rate monitoring

#### Cost Monitoring
- [ ] **Cost Explorer**: Set up cost tracking and analysis
- [ ] **Budget Alerts**: Configure budget alerts and notifications
- [ ] **Resource Tagging**: Implement comprehensive resource tagging

### 🧪 Phase 7: Testing & Validation

#### Performance Testing
- [ ] **Load Testing**: Test with expected production load
  ```bash
  # Load test with 1000 concurrent users
  artillery run load-test-config.yml
  ```
- [ ] **Stress Testing**: Test system limits and failure modes
- [ ] **Latency Testing**: Verify response time requirements
- [ ] **Scalability Testing**: Test auto-scaling behavior

#### Security Testing
- [ ] **Penetration Testing**: Conduct security assessment
- [ ] **Vulnerability Scanning**: Run automated security scans
- [ ] **Compliance Validation**: Verify FedRAMP compliance requirements
- [ ] **Access Control Testing**: Validate IAM policies and permissions

#### Functional Testing
- [ ] **End-to-End Testing**: Test complete user workflows
- [ ] **Integration Testing**: Test all service integrations
- [ ] **Regression Testing**: Ensure existing functionality works
- [ ] **User Acceptance Testing**: Validate with actual users

### 🚀 Phase 8: Deployment & Go-Live

#### Deployment Pipeline
- [ ] **CI/CD Pipeline**: Set up automated deployment pipeline
  ```yaml
  # GitHub Actions workflow
  name: Deploy to Production
  on:
    push:
      branches: [main]
  jobs:
    deploy:
      runs-on: ubuntu-latest
      steps:
        - name: Deploy to ECS
          run: aws ecs update-service --force-new-deployment
  ```
- [ ] **Blue/Green Deployment**: Implement zero-downtime deployment
- [ ] **Rollback Strategy**: Prepare rollback procedures
- [ ] **Deployment Validation**: Automated post-deployment testing

#### Go-Live Checklist
- [ ] **DNS Cutover**: Update DNS to point to production
- [ ] **Traffic Monitoring**: Monitor traffic patterns and performance
- [ ] **Error Monitoring**: Watch for errors and issues
- [ ] **User Communication**: Notify users of new system availability
- [ ] **Support Readiness**: Ensure support team is ready

### 📈 Phase 9: Post-Deployment

#### Monitoring & Maintenance
- [ ] **24/7 Monitoring**: Set up continuous monitoring
- [ ] **Incident Response**: Establish incident response procedures
- [ ] **Backup Verification**: Verify backup and recovery procedures
- [ ] **Performance Optimization**: Ongoing performance tuning

#### Documentation & Training
- [ ] **Operations Manual**: Create comprehensive operations documentation
- [ ] **User Training**: Provide user training and documentation
- [ ] **Support Procedures**: Document support and troubleshooting procedures
- [ ] **Disaster Recovery**: Document disaster recovery procedures

---

## 💰 Cost Estimation

### Monthly Production Costs (1000 queries/day)

| Service | Configuration | Monthly Cost |
|---------|---------------|--------------|
| **ECS Fargate** | 2 tasks (0.5 vCPU, 1GB RAM) | $50 |
| **Application Load Balancer** | Standard ALB | $20 |
| **CloudFront** | 1TB data transfer | $85 |
| **DynamoDB** | Pay-per-request (30K reads/writes) | $15 |
| **OpenSearch** | r6g.large.search (2 nodes) | $180 |
| **Lambda** | 30K invocations, 512MB, 5s avg | $25 |
| **S3** | 100GB storage, 10GB transfer | $10 |
| **CloudWatch** | Logs and metrics | $30 |
| **Secrets Manager** | 10 secrets | $4 |
| **Route 53** | Hosted zone + health checks | $5 |
| **GSAI GPT-5** | Government rates (variable) | TBD |
| **Total Infrastructure** | | **$424/month** |

### Cost Optimization Strategies
- Use Spot instances for non-critical workloads
- Implement intelligent caching to reduce API calls
- Set up automated scaling based on usage patterns
- Use Reserved Instances for predictable workloads

---

## 🔒 Security & Compliance

### FedRAMP Compliance Requirements
- [ ] **Data Encryption**: All data encrypted at rest and in transit
- [ ] **Access Control**: Multi-factor authentication and role-based access
- [ ] **Audit Logging**: Comprehensive audit trail for all actions
- [ ] **Network Security**: VPC isolation and security group restrictions
- [ ] **Incident Response**: Documented incident response procedures
- [ ] **Vulnerability Management**: Regular security assessments and patching

### Security Best Practices
- [ ] **Least Privilege**: IAM roles with minimal required permissions
- [ ] **Network Isolation**: Private subnets for application and data layers
- [ ] **WAF Protection**: Web Application Firewall rules for common attacks
- [ ] **DDoS Protection**: CloudFront and AWS Shield protection
- [ ] **Secret Rotation**: Automatic rotation of API keys and passwords
- [ ] **Security Monitoring**: Real-time security event monitoring

---

## 📞 Support & Maintenance

### Support Structure
- **Tier 1**: Basic user support and common issues
- **Tier 2**: Technical issues and system administration
- **Tier 3**: Complex technical issues and development support
- **On-Call**: 24/7 on-call rotation for critical issues

### Maintenance Windows
- **Regular Maintenance**: Monthly maintenance window (2nd Sunday, 2-6 AM EST)
- **Emergency Maintenance**: As needed for critical security updates
- **Planned Upgrades**: Quarterly feature releases and updates

### Backup & Recovery
- **Data Backups**: Daily automated backups with 30-day retention
- **Cross-Region Replication**: Real-time replication to backup region
- **Disaster Recovery**: RTO: 4 hours, RPO: 1 hour
- **Testing**: Monthly disaster recovery testing

---

## 🎯 Success Metrics

### Performance KPIs
- **Response Time**: < 3 seconds for 95% of queries
- **Availability**: 99.9% uptime SLA
- **Accuracy**: > 90% user satisfaction with answers
- **Scalability**: Handle 10x traffic spikes without degradation

### Business KPIs
- **User Adoption**: 80% of procurement staff using system within 6 months
- **Time Savings**: 75% reduction in FAR research time
- **Cost Savings**: ROI positive within 12 months
- **Compliance**: 100% audit compliance for FAR-related decisions

This comprehensive deployment guide provides everything needed to successfully migrate the FAR Chatbot from development to a production-ready, government-compliant system on AWS.