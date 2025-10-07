#!/usr/bin/env python3
"""
Azure Environment Setup Script

Sets up Azure cloud resources for Deepr:
- Azure Storage Account (for blob storage)
- Azure Service Bus (for queue)
- Azure App Service (optional, for web app)
- Validates Azure credentials
- Creates required containers and queues
"""

import sys
import os
from pathlib import Path
import json


def check_azure_cli():
    """Check if Azure CLI is installed and user is logged in."""
    import subprocess

    try:
        result = subprocess.run(
            ["az", "--version"],
            capture_output=True,
            text=True,
            check=True
        )
        print("✓ Azure CLI installed")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("✗ Azure CLI not found")
        print("  Install from: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli")
        return False

    try:
        result = subprocess.run(
            ["az", "account", "show"],
            capture_output=True,
            text=True,
            check=True
        )
        account = json.loads(result.stdout)
        print(f"✓ Logged in as: {account['user']['name']}")
        print(f"  Subscription: {account['name']}")
        return True
    except subprocess.CalledProcessError:
        print("✗ Not logged in to Azure")
        print("  Run: az login")
        return False


def create_resource_group(name, location):
    """Create Azure resource group."""
    import subprocess

    print(f"\nCreating resource group '{name}' in {location}...")

    try:
        subprocess.run(
            [
                "az", "group", "create",
                "--name", name,
                "--location", location
            ],
            check=True,
            capture_output=True
        )
        print(f"  ✓ Resource group created")
        return True
    except subprocess.CalledProcessError as e:
        if "already exists" in e.stderr.decode():
            print(f"  ✓ Resource group already exists")
            return True
        print(f"  ✗ Failed to create resource group: {e.stderr.decode()}")
        return False


def create_storage_account(resource_group, name, location):
    """Create Azure Storage Account."""
    import subprocess

    print(f"\nCreating storage account '{name}'...")

    try:
        subprocess.run(
            [
                "az", "storage", "account", "create",
                "--name", name,
                "--resource-group", resource_group,
                "--location", location,
                "--sku", "Standard_LRS",
                "--kind", "StorageV2"
            ],
            check=True,
            capture_output=True
        )
        print(f"  ✓ Storage account created")
        return True
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode()
        if "already exists" in error_msg:
            print(f"  ✓ Storage account already exists")
            return True
        print(f"  ✗ Failed: {error_msg}")
        return False


def get_storage_connection_string(resource_group, account_name):
    """Get storage account connection string."""
    import subprocess

    try:
        result = subprocess.run(
            [
                "az", "storage", "account", "show-connection-string",
                "--name", account_name,
                "--resource-group", resource_group,
                "--output", "json"
            ],
            check=True,
            capture_output=True,
            text=True
        )
        data = json.loads(result.stdout)
        return data["connectionString"]
    except subprocess.CalledProcessError as e:
        print(f"  ✗ Failed to get connection string: {e.stderr.decode()}")
        return None


def create_storage_containers(connection_string):
    """Create required blob containers."""
    import subprocess

    containers = ["results", "uploads"]

    print("\nCreating blob containers...")
    for container in containers:
        try:
            subprocess.run(
                [
                    "az", "storage", "container", "create",
                    "--name", container,
                    "--connection-string", connection_string
                ],
                check=True,
                capture_output=True
            )
            print(f"  ✓ {container}")
        except subprocess.CalledProcessError:
            print(f"  ✓ {container} (already exists)")


def create_service_bus(resource_group, namespace, location):
    """Create Azure Service Bus namespace."""
    import subprocess

    print(f"\nCreating Service Bus namespace '{namespace}'...")

    try:
        subprocess.run(
            [
                "az", "servicebus", "namespace", "create",
                "--name", namespace,
                "--resource-group", resource_group,
                "--location", location,
                "--sku", "Standard"
            ],
            check=True,
            capture_output=True
        )
        print(f"  ✓ Service Bus namespace created")
        return True
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode()
        if "already exists" in error_msg:
            print(f"  ✓ Service Bus namespace already exists")
            return True
        print(f"  ✗ Failed: {error_msg}")
        return False


def create_service_bus_queue(resource_group, namespace, queue_name):
    """Create Service Bus queue."""
    import subprocess

    print(f"\nCreating Service Bus queue '{queue_name}'...")

    try:
        subprocess.run(
            [
                "az", "servicebus", "queue", "create",
                "--name", queue_name,
                "--namespace-name", namespace,
                "--resource-group", resource_group
            ],
            check=True,
            capture_output=True
        )
        print(f"  ✓ Queue created")
        return True
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode()
        if "already exists" in error_msg:
            print(f"  ✓ Queue already exists")
            return True
        print(f"  ✗ Failed: {error_msg}")
        return False


def get_service_bus_connection_string(resource_group, namespace):
    """Get Service Bus connection string."""
    import subprocess

    try:
        result = subprocess.run(
            [
                "az", "servicebus", "namespace", "authorization-rule", "keys", "list",
                "--name", "RootManageSharedAccessKey",
                "--namespace-name", namespace,
                "--resource-group", resource_group,
                "--output", "json"
            ],
            check=True,
            capture_output=True,
            text=True
        )
        data = json.loads(result.stdout)
        return data["primaryConnectionString"]
    except subprocess.CalledProcessError as e:
        print(f"  ✗ Failed to get connection string: {e.stderr.decode()}")
        return None


def save_azure_config(config_data):
    """Save Azure configuration to .env.azure file."""
    env_path = Path(".env.azure")

    config_text = f"""# Deepr Azure Configuration
# Generated by setup_azure.py

# Provider Configuration
DEEPR_PROVIDER=azure

# Azure OpenAI Configuration
AZURE_OPENAI_API_KEY=YOUR_AZURE_OPENAI_KEY_HERE
AZURE_OPENAI_ENDPOINT=YOUR_AZURE_OPENAI_ENDPOINT_HERE
AZURE_OPENAI_API_VERSION=2024-05-01-preview

# Storage Configuration
DEEPR_STORAGE=blob
AZURE_STORAGE_CONNECTION_STRING={config_data.get('storage_connection_string', 'YOUR_CONNECTION_STRING')}
AZURE_STORAGE_ACCOUNT_NAME={config_data.get('storage_account_name', 'YOUR_ACCOUNT_NAME')}

# Queue Configuration
DEEPR_QUEUE=azure
AZURE_SERVICE_BUS_CONNECTION_STRING={config_data.get('servicebus_connection_string', 'YOUR_CONNECTION_STRING')}
AZURE_SERVICE_BUS_QUEUE_NAME={config_data.get('queue_name', 'research-jobs')}

# Cost Limits (USD)
DEEPR_MAX_COST_PER_JOB=10.00
DEEPR_MAX_COST_PER_DAY=100.00
DEEPR_MAX_COST_PER_MONTH=1000.00

# Model Configuration
DEEPR_DEFAULT_MODEL=o4-mini-deep-research
DEEPR_ENABLE_WEB_SEARCH=true
"""

    env_path.write_text(config_text)
    print(f"\n✓ Configuration saved to {env_path}")
    print("  IMPORTANT: Edit this file to add your Azure OpenAI credentials")


def main():
    """Run Azure setup."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Set up Azure resources for Deepr"
    )
    parser.add_argument(
        "--resource-group",
        default="deepr-resources",
        help="Resource group name (default: deepr-resources)"
    )
    parser.add_argument(
        "--location",
        default="eastus",
        help="Azure region (default: eastus)"
    )
    parser.add_argument(
        "--storage-account",
        default="deeprstorage",
        help="Storage account name (default: deeprstorage)"
    )
    parser.add_argument(
        "--servicebus-namespace",
        default="deepr-bus",
        help="Service Bus namespace (default: deepr-bus)"
    )
    parser.add_argument(
        "--queue-name",
        default="research-jobs",
        help="Queue name (default: research-jobs)"
    )

    args = parser.parse_args()

    print("="*60)
    print("Deepr Azure Environment Setup")
    print("="*60)

    # Check prerequisites
    if not check_azure_cli():
        return 1

    print("\nConfiguration:")
    print(f"  Resource Group: {args.resource_group}")
    print(f"  Location: {args.location}")
    print(f"  Storage Account: {args.storage_account}")
    print(f"  Service Bus: {args.servicebus_namespace}")
    print(f"  Queue: {args.queue_name}")

    response = input("\nProceed with setup? (y/N): ")
    if response.lower() != 'y':
        print("Cancelled")
        return 0

    # Create resources
    if not create_resource_group(args.resource_group, args.location):
        return 1

    if not create_storage_account(args.resource_group, args.storage_account, args.location):
        return 1

    storage_conn_str = get_storage_connection_string(args.resource_group, args.storage_account)
    if not storage_conn_str:
        return 1

    create_storage_containers(storage_conn_str)

    if not create_service_bus(args.resource_group, args.servicebus_namespace, args.location):
        return 1

    if not create_service_bus_queue(args.resource_group, args.servicebus_namespace, args.queue_name):
        return 1

    servicebus_conn_str = get_service_bus_connection_string(args.resource_group, args.servicebus_namespace)
    if not servicebus_conn_str:
        return 1

    # Save configuration
    config_data = {
        'storage_connection_string': storage_conn_str,
        'storage_account_name': args.storage_account,
        'servicebus_connection_string': servicebus_conn_str,
        'queue_name': args.queue_name,
    }

    save_azure_config(config_data)

    print("\n" + "="*60)
    print("✓ Azure setup complete!")
    print()
    print("Next steps:")
    print("  1. Edit .env.azure with your Azure OpenAI credentials")
    print("  2. Deploy worker: See docs/deployment/azure-worker.md")
    print("  3. Deploy web app: See docs/deployment/azure-webapp.md")
    print("="*60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
