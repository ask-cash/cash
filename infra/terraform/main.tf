# Cash production infrastructure on GCP:
#   - GKE cluster + autoscaling node pool (runs gateway/worker/connector/cron)
#   - Cloud SQL for PostgreSQL (tenant data under RLS)
#   - GCS bucket (native client + Workload Identity)
#   - Secret Manager entries (DB URL + Fernet encryption key)
#
# Cluster add-ons (ingress-nginx, cert-manager, metrics-server, External
# Secrets Operator) are installed via Helm after the cluster exists — see
# infra/README.md. They are kept out of Terraform here so cluster creation and
# app rollout stay independently reviewable.

locals {
  required_google_apis = toset([
    "compute.googleapis.com",
    "container.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "secretmanager.googleapis.com",
    "servicenetworking.googleapis.com",
    "serviceusage.googleapis.com",
    "sqladmin.googleapis.com",
    "storage.googleapis.com",
    "sts.googleapis.com",
  ])
}

# Manage the APIs this stack requires instead of relying on project-global,
# out-of-band enablement. Keeping them enabled during destroy avoids disrupting
# other workloads that may share the production project.
resource "google_project_service" "required" {
  for_each = local.required_google_apis

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

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

  depends_on = [
    google_project_service.required["compute.googleapis.com"],
  ]
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

# Private Service Access gives managed services such as Cloud SQL an internal
# address on the application VPC. GCP chooses a non-overlapping RFC1918 range
# of the requested size when no explicit address is supplied.
resource "google_compute_global_address" "private_services" {
  name          = "${var.cluster_name}-private-services"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = var.private_services_prefix_length
  network       = google_compute_network.vpc.id
}

resource "google_service_networking_connection" "private_vpc" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_services.name]

  depends_on = [
    google_project_service.required["servicenetworking.googleapis.com"],
  ]
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

  depends_on = [
    google_project_service.required["container.googleapis.com"],
  ]
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
    availability_type = "REGIONAL"
    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
    }
    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.vpc.id
      ssl_mode        = "ENCRYPTED_ONLY"
    }
  }

  deletion_protection = true

  # Cloud SQL does not infer this dependency from private_network. Waiting for
  # the service peering prevents a race that otherwise fails instance creation.
  depends_on = [
    google_project_service.required["sqladmin.googleapis.com"],
    google_service_networking_connection.private_vpc,
  ]
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

  # Retain a short recovery window without accumulating deleted/replaced user
  # media forever. Separate rules make the bounds OR conditions: a noncurrent
  # version is removed when it exceeds either the age or generation limit.
  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      days_since_noncurrent_time = var.uploads_noncurrent_retention_days
      with_state                 = "ARCHIVED"
    }
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      num_newer_versions = var.uploads_noncurrent_version_limit
      with_state         = "ARCHIVED"
    }
  }

  depends_on = [
    google_project_service.required["storage.googleapis.com"],
  ]
}

# Native GCS access for the Kubernetes `cash` ServiceAccount. No static cloud
# credential is stored in a Secret; GKE Workload Identity exchanges the pod
# identity for this narrowly-scoped Google service account.
resource "google_service_account" "cash_workload" {
  account_id   = "cash-workload"
  display_name = "Cash application workload"

  depends_on = [
    google_project_service.required["iam.googleapis.com"],
  ]
}

resource "google_storage_bucket_iam_member" "cash_uploads" {
  bucket = google_storage_bucket.uploads.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.cash_workload.email}"
}

resource "google_service_account_iam_member" "cash_workload_identity" {
  service_account_id = google_service_account.cash_workload.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[${var.kubernetes_namespace}/cash]"
}

# --- Secrets -----------------------------------------------------------------
resource "google_secret_manager_secret" "database_url" {
  secret_id = "cash-database-url"
  replication {
    auto {}
  }

  depends_on = [
    google_project_service.required["secretmanager.googleapis.com"],
  ]
}

resource "google_secret_manager_secret_version" "database_url" {
  secret      = google_secret_manager_secret.database_url.id
  secret_data = "postgresql://${var.postgres_user}:${random_password.postgres.result}@${google_sql_database_instance.postgres.private_ip_address}:5432/${var.postgres_db_name}?sslmode=require&connect_timeout=10"
}

resource "google_secret_manager_secret" "encryption_key" {
  secret_id = "cash-secrets-encryption-key"
  replication {
    auto {}
  }

  depends_on = [
    google_project_service.required["secretmanager.googleapis.com"],
  ]
}

# Fernet keys are 32 url-safe base64 bytes; base64encode of 32 raw bytes fits.
resource "google_secret_manager_secret_version" "encryption_key" {
  secret      = google_secret_manager_secret.encryption_key.id
  secret_data = base64encode(random_password.fernet_seed.result)
}
