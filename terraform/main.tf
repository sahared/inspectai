# InspectAI — Google Cloud Infrastructure
# Deploy with: terraform init && terraform apply

terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# =============================================================================
# ENABLE REQUIRED APIs
# =============================================================================

resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "firestore.googleapis.com",
    "storage.googleapis.com",
    "aiplatform.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
  ])

  service            = each.value
  disable_on_destroy = false
}

# =============================================================================
# ARTIFACT REGISTRY — Store Docker images
# =============================================================================

resource "google_artifact_registry_repository" "inspectai" {
  location      = var.region
  repository_id = "inspectai"
  format        = "DOCKER"
  description   = "InspectAI Docker images"

  depends_on = [google_project_service.apis]
}

# =============================================================================
# CLOUD STORAGE — Evidence photos and reports
# =============================================================================

resource "google_storage_bucket" "evidence" {
  name          = "${var.project_id}-inspectai-evidence"
  location      = var.region
  force_destroy = true

  uniform_bucket_level_access = true

  cors {
    origin          = ["*"]
    method          = ["GET", "PUT", "POST"]
    response_header = ["Content-Type"]
    max_age_seconds = 3600
  }

  depends_on = [google_project_service.apis]
}

# Make bucket publicly readable (for demo — restrict in production)
resource "google_storage_bucket_iam_member" "public_read" {
  bucket = google_storage_bucket.evidence.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

# =============================================================================
# FIRESTORE — Session and findings database
# =============================================================================

resource "google_firestore_database" "inspectai" {
  project     = var.project_id
  name        = "(default)"
  location_id = var.firestore_location
  type        = "FIRESTORE_NATIVE"

  depends_on = [google_project_service.apis]
}

# =============================================================================
# SECRET MANAGER — API Keys
# =============================================================================

resource "google_secret_manager_secret" "gemini_api_key" {
  secret_id = "gemini-api-key"

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

# =============================================================================
# CLOUD RUN — Backend service
# =============================================================================

resource "google_cloud_run_v2_service" "backend" {
  name     = "inspectai-backend"
  location = var.region

  template {
    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/inspectai/backend:latest"

      ports {
        container_port = 8080
      }

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GCS_BUCKET_NAME"
        value = google_storage_bucket.evidence.name
      }
      env {
        name  = "FRONTEND_URL"
        value = var.frontend_url
      }
      env {
        name  = "USE_MEMORY_STORE"
        value = "false"
      }
      env {
        name = "GOOGLE_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.gemini_api_key.secret_id
            version = "latest"
          }
        }
      }

      resources {
        limits = {
          cpu    = "2"
          memory = "1Gi"
        }
      }
    }

    scaling {
      min_instance_count = 0
      max_instance_count = 5
    }

    # WebSockets need longer timeout
    timeout = "3600s"
  }

  depends_on = [
    google_project_service.apis,
    google_artifact_registry_repository.inspectai,
  ]
}

# Allow unauthenticated access (for demo)
resource "google_cloud_run_v2_service_iam_member" "public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.backend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# =============================================================================
# OUTPUTS
# =============================================================================

output "backend_url" {
  value       = google_cloud_run_v2_service.backend.uri
  description = "Backend Cloud Run URL"
}

output "storage_bucket" {
  value       = google_storage_bucket.evidence.name
  description = "Evidence storage bucket name"
}
