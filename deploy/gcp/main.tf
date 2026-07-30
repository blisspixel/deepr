# BLOCKED: reference-only legacy GCP template.
# The impossible Terraform version constraint prevents plan or apply in v2.40.
terraform {
  required_version = "< 0.0.0"
}
