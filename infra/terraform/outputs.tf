output "cluster_name" {
  value = google_container_cluster.primary.name
}

output "cluster_endpoint" {
  value     = google_container_cluster.primary.endpoint
  sensitive = true
}

output "get_credentials_command" {
  description = "Run this to point kubectl at the new cluster."
  value       = "gcloud container clusters get-credentials ${google_container_cluster.primary.name} --region ${var.region} --project ${var.project_id}"
}

output "postgres_connection_name" {
  value = google_sql_database_instance.postgres.connection_name
}

output "postgres_private_ip" {
  description = "Private VPC address used by the application DATABASE_URL."
  value       = google_sql_database_instance.postgres.private_ip_address
}

output "private_services_range" {
  description = "RFC1918 range reserved for Private Service Access."
  value       = "${google_compute_global_address.private_services.address}/${google_compute_global_address.private_services.prefix_length}"
}

output "uploads_bucket" {
  value = google_storage_bucket.uploads.name
}

output "workload_service_account" {
  value = google_service_account.cash_workload.email
}

output "helm_workload_identity_annotation" {
  description = "Pass this value as serviceAccount.annotations.iam.gke.io/gcp-service-account."
  value       = google_service_account.cash_workload.email
}

output "database_url_secret" {
  value = google_secret_manager_secret.database_url.secret_id
}

output "encryption_key_secret" {
  value = google_secret_manager_secret.encryption_key.secret_id
}
