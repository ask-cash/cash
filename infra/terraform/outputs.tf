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

output "postgres_public_ip" {
  value = google_sql_database_instance.postgres.public_ip_address
}

output "uploads_bucket" {
  value = google_storage_bucket.uploads.name
}

output "database_url_secret" {
  value = google_secret_manager_secret.database_url.secret_id
}

output "encryption_key_secret" {
  value = google_secret_manager_secret.encryption_key.secret_id
}
