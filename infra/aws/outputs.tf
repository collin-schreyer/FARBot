output "corpus_bucket" {
  value       = aws_s3_bucket.corpus.bucket
  description = "S3 bucket to sync kb_corpus/ into"
}

output "knowledge_base_id" {
  value       = aws_bedrockagent_knowledge_base.far.id
  description = "Bedrock Knowledge Base ID (use with RetrieveAndGenerate)"
}

output "data_source_id" {
  value = aws_bedrockagent_data_source.far.data_source_id
}

output "aurora_cluster_arn" {
  value = aws_rds_cluster.far.arn
}
