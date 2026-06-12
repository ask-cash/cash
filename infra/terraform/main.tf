# Cash production infrastructure on GCP:
#   - GKE cluster + autoscaling node pool (runs gateway/worker/connector/cron)
#   - Cloud SQL for PostgreSQL (tenant data under RLS)
#   - GCS bucket (S3-compatible uploads via the storage abstraction)
#   - Secret Manager entries (DB URL + Fernet encryption key)
#
# Cluster add-ons (ingress-nginx, cert-manager, metrics-server, External
# Secrets Operator) are installed via Helm after the cluster exists — see
# infra/README.md. They are kept out of Terraform here so cluster creation and
# app rollout stay independently reviewable.

resource "random_password" "postgres" {
  length  = 24
  special = false
}

resource "random_password" "fernet_seed" {
  length  = 32
  special = false
}

# --- Network -----------------------------------------------------------------
resource "google_compute_network" "vpc" {
  name                    = "${var.cluster_name}-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "subnet" {
  name          = "${var.cluster_name}-subnet"
  ip_cidr_range = "10.10.0.0/20"
  region        = var.region
  network       = google_compute_network.vpc.id

  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = "10.20.0.0/16"
  }
  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = "10.30.0.0/20"
  }
}

# --- GKE cluster -------------------------------------------------------------
resource "google_container_cluster" "primary" {
  name     = var.cluster_name
  location = var.region

  remove_default_node_pool = true
  initial_node_count       = 1

  network    = google_compute_network.vpc.id
  subnetwork = google_compute_subnetwork.subnet.id

  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  release_channel {
    channel = "REGULAR"
  }

  resource_labels = var.labels
}

resource "google_container_node_pool" "primary" {
  name     = "${var.cluster_name}-pool"
  location = var.region
  cluster  = google_container_cluster.primary.name

  autoscaling {
    min_node_count = var.node_min_count
    max_node_count = var.node_max_count
  }

  node_config {
    machine_type = var.node_machine_type
    oauth_scopes = ["https://www.googleapis.com/auth/cloud-platform"]
    labels       = var.labels

    workload_metadata_config {
      mode = "GKE_METADATA"
    }
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }
}

# --- Cloud SQL (Postgres) ----------------------------------------------------
resource "google_sql_database_instance" "postgres" {
  name             = "${var.cluster_name}-pg"
  database_version = "POSTGRES_16"
  region           = var.region

  settings {
    tier              = var.postgres_tier
    availability_type = "ZONAL"
    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
    }
    ip_configuration {
      ipv4_enabled = true
    }
  }

  deletion_protection = true
}

resource "google_sql_database" "cash" {
  name     = var.postgres_db_name
  instance = google_sql_database_instance.postgres.name
}

resource "google_sql_user" "cash" {
  name     = var.postgres_user
  instance = google_sql_database_instance.postgres.name
  password = random_password.postgres.result
}

# --- Object storage (uploads) ------------------------------------------------
resource "google_storage_bucket" "uploads" {
  name                        = var.uploads_bucket_name
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = false
  labels                      = var.labels

  versioning {
    enabled = true
  }
}

# --- Secrets -----------------------------------------------------------------
resource "google_secret_manager_secret" "database_url" {
  secret_id = "cash-database-url"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "database_url" {
  secret      = google_secret_manager_secret.database_url.id
  secret_data = "postgresql://${var.postgres_user}:${random_password.postgres.result}@${google_sql_database_instance.postgres.public_ip_address}:5432/${var.postgres_db_name}"
}

resource "google_secret_manager_secret" "encryption_key" {
  secret_id = "cash-secrets-encryption-key"
  replication {
    auto {}
  }
}

# Fernet keys are 32 url-safe base64 bytes; base64encode of 32 raw bytes fits.
resource "google_secret_manager_secret_version" "encryption_key" {
  secret      = google_secret_manager_secret.encryption_key.id
  secret_data = base64encode(random_password.fernet_seed.result)
}
