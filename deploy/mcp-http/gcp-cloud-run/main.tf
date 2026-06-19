# Hosted Deepr MCP HTTP endpoint on GCP Cloud Run.
# This template does not create provider API secrets. Add provider keys only
# when a scoped key mode and budget intentionally allow paid research tools.

terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

variable "project_id" {
  description = "GCP project ID."
  type        = string

  validation {
    condition     = length(var.project_id) > 0
    error_message = "project_id is required."
  }
}

variable "region" {
  description = "GCP region."
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Environment name used in resource names."
  type        = string
  default     = "prod"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging, or prod."
  }
}

variable "container_image" {
  description = "Container image built from deploy/mcp-http/Dockerfile."
  type        = string

  validation {
    condition     = length(var.container_image) > 0
    error_message = "container_image is required."
  }
}

variable "data_bucket_name" {
  description = "Optional existing-compatible bucket name for Deepr data. Leave empty to derive one from project and environment."
  type        = string
  default     = ""
}

variable "allow_public_invoker" {
  description = "Grant allUsers run.invoker. Keep false until scoped keys are present and ingress policy is intentional."
  type        = bool
  default     = false
}

variable "min_instances" {
  description = "Minimum Cloud Run instances."
  type        = number
  default     = 0

  validation {
    condition     = var.min_instances >= 0 && var.min_instances <= 1
    error_message = "min_instances must be 0 or 1 for the single-writer GCS FUSE default."
  }
}

variable "max_instances" {
  description = "Maximum Cloud Run instances. Keep 1 while scoped keys and audit logs live on the object-backed /data mount."
  type        = number
  default     = 1

  validation {
    condition     = var.max_instances == 1
    error_message = "max_instances must stay 1 unless key and audit state move to a writer-safe store."
  }
}

variable "max_concurrent_requests" {
  description = "Maximum simultaneous HTTP POST requests per Deepr MCP instance before returning 429."
  type        = number
  default     = 1

  validation {
    condition     = var.max_concurrent_requests == 1
    error_message = "max_concurrent_requests must stay 1 while using the object-backed /data mount."
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  prefix           = "deepr-mcp-${var.environment}"
  data_bucket_name = var.data_bucket_name != "" ? var.data_bucket_name : "${local.prefix}-data-${var.project_id}"
}

resource "google_project_service" "apis" {
  for_each = toset([
    "iam.googleapis.com",
    "logging.googleapis.com",
    "run.googleapis.com",
    "storage.googleapis.com",
  ])

  service            = each.value
  disable_on_destroy = false
}

resource "google_service_account" "mcp" {
  account_id   = "${local.prefix}-sa"
  display_name = "Deepr hosted MCP HTTP"

  depends_on = [google_project_service.apis]
}

resource "google_storage_bucket" "data" {
  name                        = local.data_bucket_name
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true
  }

  labels = {
    environment = var.environment
    app         = "deepr-mcp-http"
  }

  depends_on = [google_project_service.apis]
}

resource "google_storage_bucket_iam_member" "mcp_data_writer" {
  bucket = google_storage_bucket.data.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.mcp.email}"
}

resource "google_cloud_run_v2_service" "mcp" {
  name     = "${local.prefix}-http"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account                  = google_service_account.mcp.email
    max_instance_request_concurrency = var.max_concurrent_requests

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    containers {
      image = var.container_image
      args = [
        "mcp",
        "serve",
        "--http",
        "--host",
        "0.0.0.0",
        "--port",
        "8765",
        "--path",
        "/mcp",
        "--keys-path",
        "/data/security/mcp_keys.json",
        "--max-concurrency",
        tostring(var.max_concurrent_requests),
      ]

      ports {
        container_port = 8765
      }

      env {
        name  = "DEEPR_DATA_DIR"
        value = "/data"
      }
      env {
        name  = "DEEPR_REPORTS_PATH"
        value = "/data/reports"
      }
      env {
        name  = "DEEPR_MCP_KEYS_PATH"
        value = "/data/security/mcp_keys.json"
      }
      env {
        name  = "DEEPR_MCP_HTTP_MAX_CONCURRENCY"
        value = tostring(var.max_concurrent_requests)
      }
      env {
        name  = "DEEPR_COST_TRACKING_STRICT"
        value = "1"
      }
      env {
        name  = "LOG_LEVEL"
        value = "INFO"
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "2Gi"
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }

      startup_probe {
        http_get {
          path = "/mcp/health"
          port = 8765
        }
        initial_delay_seconds = 10
        timeout_seconds       = 3
        period_seconds        = 10
        failure_threshold     = 3
      }

      liveness_probe {
        http_get {
          path = "/mcp/health"
          port = 8765
        }
        timeout_seconds   = 3
        period_seconds    = 30
        failure_threshold = 3
      }

      volume_mounts {
        name       = "deepr-data"
        mount_path = "/data"
      }
    }

    volumes {
      name = "deepr-data"
      gcs {
        bucket    = google_storage_bucket.data.name
        read_only = false
      }
    }
  }

  depends_on = [
    google_project_service.apis,
    google_storage_bucket_iam_member.mcp_data_writer,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  count = var.allow_public_invoker ? 1 : 0

  location = google_cloud_run_v2_service.mcp.location
  name     = google_cloud_run_v2_service.mcp.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

output "service_name" {
  description = "Cloud Run service name."
  value       = google_cloud_run_v2_service.mcp.name
}

output "data_bucket_name" {
  description = "Cloud Storage bucket mounted at /data."
  value       = google_storage_bucket.data.name
}

output "mcp_endpoint" {
  description = "Hosted MCP endpoint on the Cloud Run HTTPS URL."
  value       = "${google_cloud_run_v2_service.mcp.uri}/mcp"
}
