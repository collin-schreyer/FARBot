data "aws_caller_identity" "current" {}

locals {
  table_name = "bedrock_integration.far_kb"
}

# ---------------------------------------------------------------------------
# S3 corpus bucket  (upload kb_corpus/ here with `aws s3 sync` — see README)
# ---------------------------------------------------------------------------
resource "aws_s3_bucket" "corpus" {
  bucket = "${var.name}-corpus-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_public_access_block" "corpus" {
  bucket                  = aws_s3_bucket.corpus.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ---------------------------------------------------------------------------
# Aurora PostgreSQL Serverless v2 + pgvector (the "cheap" Bedrock KB store).
# Data API (http endpoint) is how Bedrock KB talks to it — no VPC wiring needed.
# ---------------------------------------------------------------------------
resource "random_password" "db" {
  length           = 24
  special          = true
  override_special = "!#$%&*-_=+"
}

resource "aws_secretsmanager_secret" "db" {
  name = "${var.name}-db-credentials"
}

resource "aws_secretsmanager_secret_version" "db" {
  secret_id     = aws_secretsmanager_secret.db.id
  secret_string = jsonencode({ username = "far_admin", password = random_password.db.result })
}

resource "aws_rds_cluster" "far" {
  cluster_identifier   = var.name
  engine               = "aurora-postgresql"
  engine_mode          = "provisioned"
  engine_version       = "16.6"
  database_name        = "far"
  master_username      = "far_admin"
  master_password      = random_password.db.result
  enable_http_endpoint = true # RDS Data API — required by Bedrock KB on Aurora
  skip_final_snapshot  = true

  serverlessv2_scaling_configuration {
    min_capacity = var.min_acu
    max_capacity = var.max_acu
  }
}

resource "aws_rds_cluster_instance" "far" {
  cluster_identifier = aws_rds_cluster.far.id
  instance_class     = "db.serverless"
  engine             = aws_rds_cluster.far.engine
  engine_version     = aws_rds_cluster.far.engine_version
}

# Create the pgvector extension, schema, table, and indexes Bedrock KB expects.
resource "null_resource" "bootstrap_db" {
  depends_on = [aws_rds_cluster_instance.far, aws_secretsmanager_secret_version.db]
  triggers   = { table = local.table_name, dim = var.embedding_dim }

  provisioner "local-exec" {
    command = join(" ", [
      "${path.module}/bootstrap_db.sh",
      aws_rds_cluster.far.arn,
      aws_secretsmanager_secret.db.arn,
      aws_rds_cluster.far.database_name,
      var.aws_profile,
      var.region,
      var.embedding_dim,
    ])
  }
}

# ---------------------------------------------------------------------------
# IAM role assumed by the Bedrock Knowledge Base service
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "kb_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "kb" {
  name               = "${var.name}-kb-role"
  assume_role_policy = data.aws_iam_policy_document.kb_assume.json
}

data "aws_iam_policy_document" "kb" {
  statement {
    sid       = "Embeddings"
    actions   = ["bedrock:InvokeModel"]
    resources = ["arn:aws:bedrock:${var.region}::foundation-model/${var.embedding_model_id}"]
  }
  statement {
    sid       = "S3Read"
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = [aws_s3_bucket.corpus.arn, "${aws_s3_bucket.corpus.arn}/*"]
  }
  statement {
    sid       = "AuroraDataApi"
    actions   = ["rds-data:ExecuteStatement", "rds-data:BatchExecuteStatement", "rds:DescribeDBClusters"]
    resources = [aws_rds_cluster.far.arn]
  }
  statement {
    sid       = "Secret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.db.arn]
  }
}

resource "aws_iam_role_policy" "kb" {
  role   = aws_iam_role.kb.id
  policy = data.aws_iam_policy_document.kb.json
}

# ---------------------------------------------------------------------------
# Bedrock Knowledge Base (managed hybrid retrieval) + S3 data source
# ---------------------------------------------------------------------------
resource "aws_bedrockagent_knowledge_base" "far" {
  name       = var.name
  role_arn   = aws_iam_role.kb.arn
  depends_on = [null_resource.bootstrap_db, aws_iam_role_policy.kb]

  knowledge_base_configuration {
    type = "VECTOR"
    vector_knowledge_base_configuration {
      embedding_model_arn = "arn:aws:bedrock:${var.region}::foundation-model/${var.embedding_model_id}"
    }
  }

  storage_configuration {
    type = "RDS"
    rds_configuration {
      resource_arn           = aws_rds_cluster.far.arn
      credentials_secret_arn = aws_secretsmanager_secret.db.arn
      database_name          = aws_rds_cluster.far.database_name
      table_name             = local.table_name
      field_mapping {
        primary_key_field = "id"
        vector_field      = "embedding"
        text_field        = "chunks"
        metadata_field    = "metadata"
      }
    }
  }
}

resource "aws_bedrockagent_data_source" "far" {
  knowledge_base_id = aws_bedrockagent_knowledge_base.far.id
  name              = "${var.name}-s3-corpus"

  data_source_configuration {
    type = "S3"
    s3_configuration {
      bucket_arn = aws_s3_bucket.corpus.arn
    }
  }
}
