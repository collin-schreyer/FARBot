variable "aws_profile" {
  type        = string
  description = "AWS CLI profile for the Pulse commercial account"
  default     = "farbot"
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "name" {
  type        = string
  description = "Resource name prefix"
  default     = "far-kb"
}

variable "embedding_model_id" {
  type        = string
  description = "Bedrock embedding model (Titan Text v2 = 1024-dim)"
  default     = "amazon.titan-embed-text-v2:0"
}

variable "embedding_dim" {
  type    = number
  default = 1024
}

variable "min_acu" {
  type        = number
  description = "Aurora Serverless v2 min capacity (0.5 = ~$43/mo floor)"
  default     = 0.5
}

variable "max_acu" {
  type    = number
  default = 2.0
}
