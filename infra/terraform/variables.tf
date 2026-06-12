variable "project_id" {
  type        = string
  description = "GCP project id."
}

variable "region" {
  type        = string
  description = "GCP region for the cluster and regional resources."
  default     = "us-central1"
}

variable "cluster_name" {
  type    = string
  default = "cash-prod"
}

variable "node_machine_type" {
  type    = string
  default = "e2-standard-2"
}

variable "node_min_count" {
  type    = number
  default = 1
}

variable "node_max_count" {
  type    = number
  default = 5
}

variable "postgres_tier" {
  type        = string
  description = "Cloud SQL machine tier."
  default     = "db-custom-1-3840"
}

variable "postgres_db_name" {
  type    = string
  default = "cash"
}

variable "postgres_user" {
  type    = string
  default = "cash"
}

variable "uploads_bucket_name" {
  type        = string
  description = "Globally-unique GCS bucket name for user uploads."
}

variable "labels" {
  type    = map(string)
  default = {
    app = "cash"
    env = "prod"
  }
}
