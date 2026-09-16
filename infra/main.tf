terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.20"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# 1. Enable Required Google Cloud APIs
locals {
  services = [
    "run.googleapis.com",
    "cloudtasks.googleapis.com",
    "cloudscheduler.googleapis.com",
    "firestore.googleapis.com",
    "bigquery.googleapis.com",
    "storage.googleapis.com",
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
  ]
}

resource "google_project_service" "apis" {
  for_each           = toset(locals.services)
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# 2. Least-Privilege Service Accounts
resource "google_service_account" "api" {
  account_id   = "storeops-api-sa"
  display_name = "StoreOps Public API Service Account"
  project      = var.project_id
}

resource "google_service_account" "worker" {
  account_id   = "storeops-worker-sa"
  display_name = "StoreOps Private Worker Service Account"
  project      = var.project_id
}

resource "google_service_account" "invoker" {
  account_id   = "storeops-invoker-sa"
  display_name = "StoreOps Cloud Tasks / Scheduler Invoker Service Account"
  project      = var.project_id
}

# 3. IAM Bindings for API Service Account
resource "google_project_iam_member" "api_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_project_iam_member" "api_storage" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_project_iam_member" "api_bigquery_data" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_project_iam_member" "api_bigquery_job" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_project_iam_member" "api_tasks_enqueuer" {
  project = var.project_id
  role    = "roles/cloudtasks.enqueuer"
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_service_account_iam_member" "api_acts_as_invoker" {
  service_account_id = google_service_account.invoker.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.api.email}"
}

# 4. IAM Bindings for Worker Service Account
resource "google_project_iam_member" "worker_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.worker.email}"
}

resource "google_project_iam_member" "worker_storage" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.worker.email}"
}

resource "google_project_iam_member" "worker_bigquery_data" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.worker.email}"
}

resource "google_project_iam_member" "worker_bigquery_job" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.worker.email}"
}

resource "google_project_iam_member" "worker_ai" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.worker.email}"
}

# 5. Cloud Storage Private Media Bucket
resource "google_storage_bucket" "media" {
  name                        = "storeops-${var.project_id}-media"
  location                    = var.region
  project                     = var.project_id
  uniform_bucket_level_access = true
  force_destroy               = false

  cors {
    origin          = ["https://${var.project_id}.web.app", "https://${var.project_id}.firebaseapp.com", "http://localhost:3000"]
    method          = ["GET", "PUT", "POST", "HEAD"]
    response_header = ["*"]
    max_age_seconds = 3600
  }

  depends_on = [google_project_service.apis]
}

# 6. BigQuery Analytics Dataset and Tables
resource "google_bigquery_dataset" "analytics" {
  dataset_id  = "storeops_${var.app_env}"
  project     = var.project_id
  location    = var.region
  description = "StoreOps analytical dataset for sales and inventory metrics"

  depends_on = [google_project_service.apis]
}

# 7. Cloud Tasks Queue
resource "google_cloud_tasks_queue" "work_queue" {
  name     = "storeops-work-queue"
  location = var.region
  project  = var.project_id

  rate_limits {
    max_dispatches_per_second = 10
    max_concurrent_dispatches = 5
  }

  retry_config {
    max_attempts       = 5
    min_backoff        = "1s"
    max_backoff        = "30s"
    max_doublings      = 4
    max_retry_duration = "300s"
  }

  depends_on = [google_project_service.apis]
}

# 8. Artifact Registry Repository
resource "google_artifact_registry_repository" "storeops" {
  project       = var.project_id
  location      = var.region
  repository_id = "storeops"
  description   = "Docker container images for StoreOps services"
  format        = "DOCKER"

  depends_on = [google_project_service.apis]
}

# 9. Cloud Run API Service (Public Ingress)
resource "google_cloud_run_v2_service" "api" {
  name     = "storeops-api"
  location = var.region
  project  = var.project_id
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.api.email
    scaling {
      max_instance_count = 3
    }
    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/storeops/storeops-api:latest"
      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }
      env {
        name  = "APP_ENV"
        value = var.app_env
      }
      env {
        name  = "DATA_BACKEND"
        value = "CLOUD"
      }
      env {
        name  = "GCP_PROJECT"
        value = var.project_id
      }
      env {
        name  = "MEDIA_BUCKET"
        value = google_storage_bucket.media.name
      }
      env {
        name  = "BIGQUERY_DATASET"
        value = google_bigquery_dataset.analytics.dataset_id
      }
      env {
        name  = "TASKS_QUEUE"
        value = google_cloud_tasks_queue.work_queue.id
      }
      env {
        name  = "INVOKER_SERVICE_ACCOUNT"
        value = google_service_account.invoker.email
      }
      env {
        name  = "MODEL_ID"
        value = var.gemini_model_id
      }
    }
  }

  depends_on = [google_project_service.apis]
}

# Allow public unauthenticated ingress for API (auth verified via Firebase tokens in FastAPI)
resource "google_cloud_run_v2_service_iam_member" "api_public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# 9. Cloud Run Worker Service (Strictly Private Ingress)
resource "google_cloud_run_v2_service" "worker" {
  name     = "storeops-worker"
  location = var.region
  project  = var.project_id
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  template {
    service_account = google_service_account.worker.email
    scaling {
      max_instance_count = 3
    }
    containers {
      image   = "${var.region}-docker.pkg.dev/${var.project_id}/storeops/storeops-worker:latest"
      command = ["python3", "-m", "scripts.deploy.run_worker"]
      ports {
        container_port = 8001
      }
      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
      }
      env {
        name  = "APP_ENV"
        value = var.app_env
      }
      env {
        name  = "DATA_BACKEND"
        value = "CLOUD"
      }
      env {
        name  = "GCP_PROJECT"
        value = var.project_id
      }
      env {
        name  = "MEDIA_BUCKET"
        value = google_storage_bucket.media.name
      }
      env {
        name  = "BIGQUERY_DATASET"
        value = google_bigquery_dataset.analytics.dataset_id
      }
      env {
        name  = "MODEL_ID"
        value = var.gemini_model_id
      }
    }
  }

  depends_on = [google_project_service.apis]
}

# Private Worker IAM: Only Invoker SA can invoke the worker
resource "google_cloud_run_v2_service_iam_member" "worker_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.worker.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.invoker.email}"
}

# 10. Cloud Scheduler Outbox Draining Job
# Targets GET /health as a 1-minute system heartbeat until foundation/coordinator integrates internal /outbox/drain route
resource "google_cloud_scheduler_job" "outbox_drain" {
  name        = "storeops-outbox-drain"
  description = "Scheduled heartbeat and outbox dispatcher (targets /health pending foundation /outbox/drain integration)"
  schedule    = "* * * * *"
  time_zone   = "Etc/UTC"
  project     = var.project_id
  region      = var.region

  http_target {
    http_method = "GET"
    uri         = "${google_cloud_run_v2_service.api.uri}/health"

    headers = {
      "User-Agent" = "StoreOps-CloudScheduler/1.0"
    }

    oidc_token {
      service_account_email = google_service_account.invoker.email
      audience              = google_cloud_run_v2_service.api.uri
    }
  }

  retry_config {
    retry_count = 2
  }

  depends_on = [google_project_service.apis]
}
