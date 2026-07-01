# FAR Bot — AWS RAG layer (Terraform)

Managed retrieval for the FAR bot rebuild: **Amazon Bedrock Knowledge Base** over an
**Aurora PostgreSQL Serverless v2 + pgvector** vector store, fed from an **S3** corpus.
Commercial AWS, same account as Pulse. Hosting (Next.js on App Runner/CloudFront) is a
separate stack added once retrieval parity is proven.

## What this creates
- S3 bucket for the ingestion corpus (`kb_corpus/` from `python/build_kb_corpus.py`)
- Aurora PostgreSQL Serverless v2 cluster (Data API on) + pgvector schema/table/indexes
- Secrets Manager secret (DB creds), IAM role for the Bedrock KB service
- Bedrock Knowledge Base (Titan Text v2 embeddings, 1024-dim) + S3 data source

## Cost (rough, us-east-1)
- Aurora Serverless v2 floor ~0.5 ACU ≈ **$43/mo** (scales up under load only)
- Bedrock embeddings: one-time ingest of ~3,500 docs ≈ a few cents; queries pay per token
- S3: negligible (30 MB)
This is the cheap path chosen over OpenSearch Serverless (~$700/mo floor).

## Apply sequence (requires the Pulse-account profile)
```bash
# 1. configure creds (do NOT paste keys in chat):
aws configure --profile farbot          # or reuse an existing profile via -var
aws sts get-caller-identity --profile farbot   # confirm = Pulse account

# 2. provision (review the plan first):
cd infra/aws
terraform init
terraform plan -var aws_profile=farbot
terraform apply -var aws_profile=farbot

# 3. upload the corpus and ingest:
aws s3 sync ../../kb_corpus "s3://$(terraform output -raw corpus_bucket)" --profile farbot
aws bedrock-agent start-ingestion-job \
  --knowledge-base-id "$(terraform output -raw knowledge_base_id)" \
  --data-source-id   "$(terraform output -raw data_source_id)" \
  --profile farbot --region us-east-1

# 4. parity eval (task #6): point the eval at RetrieveAndGenerate and confirm it
#    matches/beats the local baseline (recall@10 >= 0.72, top-3 rel > 49%).
```

> Note: requires Bedrock model access for Titan Embed Text v2 (and Claude for generation)
> enabled in the account/region — enable once in the Bedrock console if not already.
