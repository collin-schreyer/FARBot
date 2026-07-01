#!/usr/bin/env bash
# Create the pgvector extension, schema, table, and indexes that Bedrock
# Knowledge Bases require on an Aurora PostgreSQL vector store. Invoked by the
# null_resource in main.tf via the RDS Data API (no VPC access needed).
set -euo pipefail

CLUSTER_ARN="$1"; SECRET_ARN="$2"; DB="$3"; PROFILE="$4"; REGION="$5"; DIM="${6:-1024}"

run() {
  aws rds-data execute-statement \
    --resource-arn "$CLUSTER_ARN" \
    --secret-arn "$SECRET_ARN" \
    --database "$DB" --region "$REGION" --profile "$PROFILE" \
    --sql "$1" >/dev/null
}

# Aurora Serverless v2 can take a moment to accept Data API calls after create.
for i in $(seq 1 10); do
  if run "SELECT 1;" 2>/dev/null; then break; fi
  echo "waiting for Data API ($i/10)..."; sleep 15
done

run "CREATE EXTENSION IF NOT EXISTS vector;"
run "CREATE SCHEMA IF NOT EXISTS bedrock_integration;"
run "CREATE TABLE IF NOT EXISTS bedrock_integration.far_kb (
       id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
       embedding vector(${DIM}),
       chunks text,
       metadata jsonb,
       custom_metadata jsonb,
       section text,
       part text,
       subpart text,
       title text,
       cross_refs text,
       source_url text
     );"
run "CREATE INDEX IF NOT EXISTS far_kb_embedding_idx ON bedrock_integration.far_kb
       USING hnsw (embedding vector_cosine_ops);"
run "CREATE INDEX IF NOT EXISTS far_kb_chunks_fts ON bedrock_integration.far_kb
       USING gin (to_tsvector('simple', chunks));"
echo "Aurora pgvector store bootstrapped (dim=${DIM})."
