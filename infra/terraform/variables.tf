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

variable "private_services_prefix_length" {
  type        = number
  description = "Prefix length reserved for Private Service Access. /16 leaves room for regional managed-service growth."
  default     = 16

  validation {
    condition = (
      floor(var.private_services_prefix_length) == var.private_services_prefix_length
      && var.private_services_prefix_length >= 16
      && var.private_services_prefix_length <= 24
    )
    error_message = "private_services_prefix_length must be a whole number between 16 and 24."
  }
}

variable "postgres_tier" {
  type        = string
  description = "Cloud SQL machine tier."
  default     = "db-custom-2-7680"
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

variable "uploads_noncurrent_retention_days" {
  type        = number
  description = "Maximum days to retain a noncurrent upload object version."
  default     = 30

  validation {
    condition = (
      floor(var.uploads_noncurrent_retention_days) == var.uploads_noncurrent_retention_days
      && var.uploads_noncurrent_retention_days >= 1
      && var.uploads_noncurrent_retention_days <= 3650
    )
    error_message = "uploads_noncurrent_retention_days must be a whole number between 1 and 3650."
  }
}

variable "uploads_noncurrent_version_limit" {
  type        = number
  description = "Delete an archived upload generation once this many newer generations exist."
  default     = 3

  validation {
    condition = (
      floor(var.uploads_noncurrent_version_limit) == var.uploads_noncurrent_version_limit
      && var.uploads_noncurrent_version_limit >= 1
    )
    error_message = "uploads_noncurrent_version_limit must be a positive whole number."
  }
}

variable "kubernetes_namespace" {
  type        = string
  description = "Namespace containing the Helm chart's cash ServiceAccount."
  default     = "cash"
}

variable "labels" {
  type = map(string)
  default = {
    app = "cash"
    env = "prod"
  }
}
