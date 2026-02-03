# Deepr GCP Deployment - Security Hardened
# Deploy with: terraform init && terraform apply

terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.0"
    }
  }
}

variable "project_id" {
  description = "GCP Project ID"
  type        = string

  validation {
    condition     = length(var.project_id) > 0
    error_message = "Project ID is required."
  }
}

variable "region" {
  description = "GCP Region"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "prod"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "openai_api_key" {
  description = "OpenAI API Key"
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.openai_api_key) > 0
    error_message = "OpenAI API key is required."
  }
}

variable "google_api_key" {
  description = "Google API Key for Gemini (optional)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "xai_api_key" {
  description = "xAI API Key for Grok (optional)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "daily_budget" {
  description = "Daily spending limit in USD"
  type        = number
  default     = 50

  validation {
    condition     = var.daily_budget >= 1 && var.daily_budget <= 10000
    error_message = "Daily budget must be between 1 and 10000."
  }
}

variable "monthly_budget" {
  description = "Monthly spending limit in USD"
  type        = number
  default     = 500

  validation {
    condition     = var.monthly_budget >= 1 && var.monthly_budget <= 100000
    error_message = "Monthly budget must be between 1 and 100000."
  }
}

variable "enable_cloud_armor" {
  description = "Enable Cloud Armor WAF protection"
  type        = bool
  default     = true
}

variable "allowed_ip_ranges" {
  description = "List of allowed CIDR ranges for API access"
  type        = list(string)
  default     = []
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

locals {
  prefix = "deepr-${var.environment}"
}

# ============================================================================
# Enable APIs
# ============================================================================
resource "google_project_service" "apis" {
  for_each = toset([
    "cloudfunctions.googleapis.com",
    "run.googleapis.com",
    "pubsub.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudkms.googleapis.com",
    "vpcaccess.googleapis.com",
    "compute.googleapis.com",
    "firestore.googleapis.com",
    "apigateway.googleapis.com",
    "servicecontrol.googleapis.com",
    "servicemanagement.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
  ])

  service            = each.value
  disable_on_destroy = false
}

# ============================================================================
# VPC Network
# ============================================================================
resource "google_compute_network" "deepr" {
  name                    = "${local.prefix}-vpc"
  auto_create_subnetworks = false

  depends_on = [google_project_service.apis]
}

resource "google_compute_subnetwork" "private" {
  name          = "${local.prefix}-private-subnet"
  ip_cidr_range = "10.0.0.0/24"
  region        = var.region
  network       = google_compute_network.deepr.id

  private_ip_google_access = true

  log_config {
    aggregation_interval = "INTERVAL_5_SEC"
    flow_sampling        = 0.5
    metadata             = "INCLUDE_ALL_METADATA"
  }
}

resource "google_compute_subnetwork" "connector" {
  name          = "${local.prefix}-connector-subnet"
  ip_cidr_range = "10.0.1.0/28"
  region        = var.region
  network       = google_compute_network.deepr.id
}

# Serverless VPC Access Connector
resource "google_vpc_access_connector" "connector" {
  name          = "${local.prefix}-connector"
  region        = var.region
  ip_cidr_range = "10.8.0.0/28"
  network       = google_compute_network.deepr.id
  min_instances = 2
  max_instances = 10

  depends_on = [google_project_service.apis]
}

# Cloud NAT for outbound internet access
resource "google_compute_router" "router" {
  name    = "${local.prefix}-router"
  region  = var.region
  network = google_compute_network.deepr.id
}

resource "google_compute_router_nat" "nat" {
  name                               = "${local.prefix}-nat"
  router                             = google_compute_router.router.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"

  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }
}

# Firewall rules
resource "google_compute_firewall" "allow_internal" {
  name    = "${local.prefix}-allow-internal"
  network = google_compute_network.deepr.id

  allow {
    protocol = "tcp"
    ports    = ["443", "8080"]
  }

  source_ranges = ["10.0.0.0/8"]
  direction     = "INGRESS"
}

resource "google_compute_firewall" "deny_all_ingress" {
  name     = "${local.prefix}-deny-all-ingress"
  network  = google_compute_network.deepr.id
  priority = 65534

  deny {
    protocol = "all"
  }

  source_ranges = ["0.0.0.0/0"]
  direction     = "INGRESS"
}

# ============================================================================
# Cloud KMS for Encryption
# ============================================================================
resource "google_kms_key_ring" "deepr" {
  name     = "${local.prefix}-keyring"
  location = var.region

  depends_on = [google_project_service.apis]
}

resource "google_kms_crypto_key" "deepr" {
  name            = "${local.prefix}-key"
  key_ring        = google_kms_key_ring.deepr.id
  rotation_period = "7776000s"  # 90 days

  lifecycle {
    prevent_destroy = true
  }
}

# ============================================================================
# Secret Manager with KMS Encryption
# ============================================================================
resource "google_secret_manager_secret" "openai_key" {
  secret_id = "${local.prefix}-openai-key"

  replication {
    user_managed {
      replicas {
        location = var.region
        customer_managed_encryption {
          kms_key_name = google_kms_crypto_key.deepr.id
        }
      }
    }
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "openai_key" {
  secret      = google_secret_manager_secret.openai_key.id
  secret_data = var.openai_api_key
}

resource "google_secret_manager_secret" "google_key" {
  count     = var.google_api_key != "" ? 1 : 0
  secret_id = "${local.prefix}-google-key"

  replication {
    user_managed {
      replicas {
        location = var.region
        customer_managed_encryption {
          kms_key_name = google_kms_crypto_key.deepr.id
        }
      }
    }
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "google_key" {
  count       = var.google_api_key != "" ? 1 : 0
  secret      = google_secret_manager_secret.google_key[0].id
  secret_data = var.google_api_key
}

resource "google_secret_manager_secret" "xai_key" {
  count     = var.xai_api_key != "" ? 1 : 0
  secret_id = "${local.prefix}-xai-key"

  replication {
    user_managed {
      replicas {
        location = var.region
        customer_managed_encryption {
          kms_key_name = google_kms_crypto_key.deepr.id
        }
      }
    }
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "xai_key" {
  count       = var.xai_api_key != "" ? 1 : 0
  secret      = google_secret_manager_secret.xai_key[0].id
  secret_data = var.xai_api_key
}

# API Key for authenticated access
resource "google_secret_manager_secret" "api_key" {
  secret_id = "${local.prefix}-api-key"

  replication {
    user_managed {
      replicas {
        location = var.region
        customer_managed_encryption {
          kms_key_name = google_kms_crypto_key.deepr.id
        }
      }
    }
  }

  depends_on = [google_project_service.apis]
}

resource "random_password" "api_key" {
  length  = 64
  special = false
}

resource "google_secret_manager_secret_version" "api_key" {
  secret      = google_secret_manager_secret.api_key.id
  secret_data = random_password.api_key.result
}

# ============================================================================
# Cloud Storage (Results) with Encryption
# ============================================================================
resource "google_storage_bucket" "results" {
  name          = "${local.prefix}-results-${var.project_id}"
  location      = var.region
  force_destroy = false

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  encryption {
    default_kms_key_name = google_kms_crypto_key.deepr.id
  }

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type = "Delete"
    }
  }

  lifecycle_rule {
    condition {
      num_newer_versions = 3
    }
    action {
      type = "Delete"
    }
  }

  logging {
    log_bucket        = google_storage_bucket.logs.name
    log_object_prefix = "results-access/"
  }
}

resource "google_storage_bucket" "logs" {
  name          = "${local.prefix}-logs-${var.project_id}"
  location      = var.region
  force_destroy = false

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  lifecycle_rule {
    condition {
      age = 365
    }
    action {
      type = "Delete"
    }
  }
}

# ============================================================================
# Firestore (Job Metadata - O(1) lookups)
# ============================================================================
resource "google_firestore_database" "deepr" {
  project     = var.project_id
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"

  depends_on = [google_project_service.apis]
}

# ============================================================================
# Pub/Sub (Job Queue) with Encryption
# ============================================================================
resource "google_pubsub_topic" "jobs" {
  name         = "${local.prefix}-jobs"
  kms_key_name = google_kms_crypto_key.deepr.id

  depends_on = [google_project_service.apis]
}

resource "google_pubsub_subscription" "jobs" {
  name  = "${local.prefix}-jobs-sub"
  topic = google_pubsub_topic.jobs.name

  ack_deadline_seconds       = 600  # 10 minutes
  message_retention_duration = "604800s"  # 7 days
  retain_acked_messages      = false
  expiration_policy {
    ttl = ""  # Never expire
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dlq.id
    max_delivery_attempts = 5
  }
}

resource "google_pubsub_topic" "dlq" {
  name         = "${local.prefix}-jobs-dlq"
  kms_key_name = google_kms_crypto_key.deepr.id

  depends_on = [google_project_service.apis]
}

resource "google_pubsub_subscription" "dlq" {
  name  = "${local.prefix}-jobs-dlq-sub"
  topic = google_pubsub_topic.dlq.name

  message_retention_duration = "604800s"
}

# ============================================================================
# Service Accounts with Least Privilege
# ============================================================================

# API Service Account
resource "google_service_account" "api" {
  account_id   = "${local.prefix}-api-sa"
  display_name = "Deepr API Service Account"
}

# Worker Service Account
resource "google_service_account" "worker" {
  account_id   = "${local.prefix}-worker-sa"
  display_name = "Deepr Worker Service Account"
}

# KMS permissions for service accounts
resource "google_kms_crypto_key_iam_member" "api_kms" {
  crypto_key_id = google_kms_crypto_key.deepr.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${google_service_account.api.email}"
}

resource "google_kms_crypto_key_iam_member" "worker_kms" {
  crypto_key_id = google_kms_crypto_key.deepr.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${google_service_account.worker.email}"
}

# API service account - specific bucket permissions
resource "google_storage_bucket_iam_member" "api_storage_jobs" {
  bucket = google_storage_bucket.results.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.api.email}"

  condition {
    title       = "jobs-prefix-only"
    description = "Access only to jobs/ prefix"
    expression  = "resource.name.startsWith(\"projects/_/buckets/${google_storage_bucket.results.name}/objects/jobs/\")"
  }
}

# API service account - Pub/Sub publisher only
resource "google_pubsub_topic_iam_member" "api_pubsub" {
  topic  = google_pubsub_topic.jobs.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${google_service_account.api.email}"
}

# API service account - Firestore access
resource "google_project_iam_member" "api_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.api.email}"
}

# API service account - Secret access (read only)
resource "google_secret_manager_secret_iam_member" "api_openai" {
  secret_id = google_secret_manager_secret.openai_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api.email}"
}

resource "google_secret_manager_secret_iam_member" "api_apikey" {
  secret_id = google_secret_manager_secret.api_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api.email}"
}

# Worker service account - specific bucket permissions
resource "google_storage_bucket_iam_member" "worker_storage_results" {
  bucket = google_storage_bucket.results.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.worker.email}"

  condition {
    title       = "results-prefix-only"
    description = "Access only to results/ prefix"
    expression  = "resource.name.startsWith(\"projects/_/buckets/${google_storage_bucket.results.name}/objects/results/\")"
  }
}

resource "google_storage_bucket_iam_member" "worker_storage_jobs_read" {
  bucket = google_storage_bucket.results.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.worker.email}"

  condition {
    title       = "jobs-read-only"
    description = "Read access to jobs/ prefix"
    expression  = "resource.name.startsWith(\"projects/_/buckets/${google_storage_bucket.results.name}/objects/jobs/\")"
  }
}

# Worker service account - Pub/Sub subscriber only
resource "google_pubsub_subscription_iam_member" "worker_pubsub" {
  subscription = google_pubsub_subscription.jobs.name
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:${google_service_account.worker.email}"
}

# Worker service account - Firestore access
resource "google_project_iam_member" "worker_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.worker.email}"
}

# Worker service account - Secret access
resource "google_secret_manager_secret_iam_member" "worker_openai" {
  secret_id = google_secret_manager_secret.openai_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.worker.email}"
}

# ============================================================================
# Cloud Functions (API)
# ============================================================================
resource "google_storage_bucket" "functions_source" {
  name          = "${local.prefix}-functions-${var.project_id}"
  location      = var.region
  force_destroy = true

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
}

resource "google_storage_bucket_object" "functions_source" {
  name   = "function-source-${filemd5("${path.module}/functions/main.py")}.zip"
  bucket = google_storage_bucket.functions_source.name
  source = "${path.module}/functions/function-source.zip"
}

resource "google_cloudfunctions2_function" "api" {
  name     = "${local.prefix}-api"
  location = var.region

  build_config {
    runtime     = "python311"
    entry_point = "handle_request"
    source {
      storage_source {
        bucket = google_storage_bucket.functions_source.name
        object = google_storage_bucket_object.functions_source.name
      }
    }
  }

  service_config {
    max_instance_count               = 100
    min_instance_count               = 0
    available_memory                 = "512M"
    timeout_seconds                  = 60
    service_account_email            = google_service_account.api.email
    ingress_settings                 = "ALLOW_INTERNAL_AND_GCLB"  # Only from load balancer
    all_traffic_on_latest_revision   = true
    vpc_connector                    = google_vpc_access_connector.connector.id
    vpc_connector_egress_settings    = "PRIVATE_RANGES_ONLY"

    environment_variables = {
      PROJECT_ID       = var.project_id
      PUBSUB_TOPIC     = google_pubsub_topic.jobs.name
      RESULTS_BUCKET   = google_storage_bucket.results.name
      FIRESTORE_DB     = google_firestore_database.deepr.name
      DAILY_BUDGET     = var.daily_budget
      MONTHLY_BUDGET   = var.monthly_budget
      LOG_LEVEL        = "INFO"
    }

    secret_environment_variables {
      key        = "OPENAI_API_KEY"
      project_id = var.project_id
      secret     = google_secret_manager_secret.openai_key.secret_id
      version    = "latest"
    }

    secret_environment_variables {
      key        = "API_KEY"
      project_id = var.project_id
      secret     = google_secret_manager_secret.api_key.secret_id
      version    = "latest"
    }
  }

  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret_version.openai_key,
    google_secret_manager_secret_version.api_key,
    google_vpc_access_connector.connector,
  ]
}

# ============================================================================
# Cloud Armor WAF Policy
# ============================================================================
resource "google_compute_security_policy" "deepr" {
  count = var.enable_cloud_armor ? 1 : 0
  name  = "${local.prefix}-security-policy"

  # Default rule - allow
  rule {
    action   = "allow"
    priority = "2147483647"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    description = "Default rule"
  }

  # Rate limiting rule
  rule {
    action   = "rate_based_ban"
    priority = "1000"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      rate_limit_threshold {
        count        = 1000
        interval_sec = 60
      }
      ban_duration_sec = 600
    }
    description = "Rate limit - 1000 requests per minute"
  }

  # Block common attack patterns (XSS, SQLi)
  rule {
    action   = "deny(403)"
    priority = "100"
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('xss-v33-stable')"
      }
    }
    description = "Block XSS attacks"
  }

  rule {
    action   = "deny(403)"
    priority = "101"
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('sqli-v33-stable')"
      }
    }
    description = "Block SQL injection"
  }

  # Block known bad IPs
  rule {
    action   = "deny(403)"
    priority = "102"
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('cve-canary')"
      }
    }
    description = "Block known CVE exploits"
  }

  # Allow specific IP ranges if configured
  dynamic "rule" {
    for_each = length(var.allowed_ip_ranges) > 0 ? [1] : []
    content {
      action   = "allow"
      priority = "50"
      match {
        versioned_expr = "SRC_IPS_V1"
        config {
          src_ip_ranges = var.allowed_ip_ranges
        }
      }
      description = "Allow specific IP ranges"
    }
  }
}

# ============================================================================
# Load Balancer with Cloud Armor
# ============================================================================
resource "google_compute_global_address" "api" {
  name = "${local.prefix}-api-ip"
}

resource "google_compute_region_network_endpoint_group" "api" {
  name                  = "${local.prefix}-api-neg"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  cloud_function {
    function = google_cloudfunctions2_function.api.name
  }
}

resource "google_compute_backend_service" "api" {
  name                  = "${local.prefix}-api-backend"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTPS"

  backend {
    group = google_compute_region_network_endpoint_group.api.id
  }

  security_policy = var.enable_cloud_armor ? google_compute_security_policy.deepr[0].id : null

  log_config {
    enable      = true
    sample_rate = 1.0
  }
}

resource "google_compute_url_map" "api" {
  name            = "${local.prefix}-api-urlmap"
  default_service = google_compute_backend_service.api.id
}

resource "google_compute_managed_ssl_certificate" "api" {
  name = "${local.prefix}-api-cert"

  managed {
    domains = ["${local.prefix}-api.endpoints.${var.project_id}.cloud.goog"]
  }
}

resource "google_compute_target_https_proxy" "api" {
  name             = "${local.prefix}-api-https-proxy"
  url_map          = google_compute_url_map.api.id
  ssl_certificates = [google_compute_managed_ssl_certificate.api.id]
}

resource "google_compute_global_forwarding_rule" "api" {
  name                  = "${local.prefix}-api-forwarding"
  ip_address            = google_compute_global_address.api.address
  ip_protocol           = "TCP"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  port_range            = "443"
  target                = google_compute_target_https_proxy.api.id
}

# ============================================================================
# Artifact Registry (Container Images)
# ============================================================================
resource "google_artifact_registry_repository" "deepr" {
  location      = var.region
  repository_id = "${local.prefix}-repo"
  format        = "DOCKER"

  docker_config {
    immutable_tags = true
  }

  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 10
    }
  }

  depends_on = [google_project_service.apis]
}

# ============================================================================
# Cloud Run (Worker)
# ============================================================================
resource "google_cloud_run_v2_service" "worker" {
  name     = "${local.prefix}-worker"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  template {
    service_account = google_service_account.worker.email

    vpc_access {
      connector = google_vpc_access_connector.connector.id
      egress    = "PRIVATE_RANGES_ONLY"
    }

    scaling {
      min_instance_count = 0
      max_instance_count = 10
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.deepr.repository_id}/deepr-worker:latest"

      resources {
        limits = {
          cpu    = "2"
          memory = "4Gi"
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }

      env {
        name  = "PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "PUBSUB_SUBSCRIPTION"
        value = google_pubsub_subscription.jobs.name
      }
      env {
        name  = "RESULTS_BUCKET"
        value = google_storage_bucket.results.name
      }
      env {
        name  = "FIRESTORE_DB"
        value = google_firestore_database.deepr.name
      }
      env {
        name  = "LOG_LEVEL"
        value = "INFO"
      }
      env {
        name = "OPENAI_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.openai_key.secret_id
            version = "latest"
          }
        }
      }

      startup_probe {
        http_get {
          path = "/health"
          port = 8080
        }
        initial_delay_seconds = 10
        timeout_seconds       = 3
        period_seconds        = 10
        failure_threshold     = 3
      }

      liveness_probe {
        http_get {
          path = "/health"
          port = 8080
        }
        timeout_seconds   = 3
        period_seconds    = 30
        failure_threshold = 3
      }
    }

    timeout = "3600s"  # 1 hour max per request
  }

  depends_on = [
    google_project_service.apis,
    google_artifact_registry_repository.deepr,
    google_vpc_access_connector.connector,
  ]
}

# ============================================================================
# Monitoring and Alerting
# ============================================================================
resource "google_monitoring_alert_policy" "high_error_rate" {
  display_name = "${local.prefix}-high-error-rate"
  combiner     = "OR"

  conditions {
    display_name = "Cloud Function 5xx Error Rate"
    condition_threshold {
      filter          = "resource.type=\"cloud_function\" AND resource.labels.function_name=\"${google_cloudfunctions2_function.api.name}\" AND metric.type=\"cloudfunctions.googleapis.com/function/execution_count\" AND metric.labels.status!=\"ok\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 10

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }

  notification_channels = []  # Add notification channels in production
}

resource "google_monitoring_alert_policy" "dlq_messages" {
  display_name = "${local.prefix}-dlq-messages"
  combiner     = "OR"

  conditions {
    display_name = "Dead Letter Queue Messages"
    condition_threshold {
      filter          = "resource.type=\"pubsub_subscription\" AND resource.labels.subscription_id=\"${google_pubsub_subscription.dlq.name}\" AND metric.type=\"pubsub.googleapis.com/subscription/num_undelivered_messages\""
      duration        = "60s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MEAN"
      }
    }
  }

  notification_channels = []
}

# ============================================================================
# Audit Logging
# ============================================================================
resource "google_project_iam_audit_config" "deepr" {
  project = var.project_id
  service = "allServices"

  audit_log_config {
    log_type = "ADMIN_READ"
  }

  audit_log_config {
    log_type = "DATA_READ"
  }

  audit_log_config {
    log_type = "DATA_WRITE"
  }
}

# ============================================================================
# Outputs
# ============================================================================
output "api_url" {
  description = "Cloud Function API URL (direct)"
  value       = google_cloudfunctions2_function.api.url
}

output "api_url_lb" {
  description = "API URL via Load Balancer (recommended)"
  value       = "https://${google_compute_global_address.api.address}"
}

output "results_bucket" {
  description = "Results storage bucket"
  value       = google_storage_bucket.results.name
}

output "pubsub_topic" {
  description = "Job queue topic"
  value       = google_pubsub_topic.jobs.name
}

output "worker_url" {
  description = "Cloud Run worker URL"
  value       = google_cloud_run_v2_service.worker.uri
}

output "vpc_id" {
  description = "VPC Network ID"
  value       = google_compute_network.deepr.id
}

output "artifact_registry" {
  description = "Artifact Registry repository"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.deepr.repository_id}"
}
