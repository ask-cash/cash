terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.6"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.6"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Configure a remote backend (GCS) for shared state in real deployments:
  # backend "gcs" {
  #   bucket = "cash-tfstate"
  #   prefix = "cash/prod"
  # }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}
