#!/usr/bin/env python3
"""
Azure Environment Teardown Script

Destroys Azure cloud resources for Deepr:
- Service Bus queue and namespace
- Storage containers and account
- Resource group (optional)

CAUTION: This will DELETE all data in Azure resources.
"""

import sys
import json


def check_azure_cli():
    """Check if Azure CLI is installed and user is logged in."""
    import subprocess

    try:
        subprocess.run(
            ["az", "--version"],
            capture_output=True,
            check=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("✗ Azure CLI not found")
        return False

    try:
        result = subprocess.run(
            ["az", "account", "show"],
            capture_output=True,
            text=True,
            check=True
        )
        account = json.loads(result.stdout)
        print(f"Logged in as: {account['user']['name']}")
        print(f"Subscription: {account['name']}")
        return True
    except subprocess.CalledProcessError:
        print("✗ Not logged in to Azure")
        return False


def delete_resource_group(name, force=False):
    """Delete entire resource group."""
    import subprocess

    if not force:
        print(f"\n⚠  WARNING: This will DELETE the entire resource group '{name}'")
        print("   All resources in this group will be permanently deleted!")
        response = input("Type the resource group name to confirm: ")
        if response != name:
            print("Cancelled")
            return False

    print(f"\nDeleting resource group '{name}'...")
    print("This may take several minutes...")

    try:
        subprocess.run(
            [
                "az", "group", "delete",
                "--name", name,
                "--yes",
                "--no-wait"
            ],
            check=True
        )
        print(f"  ✓ Deletion started (running in background)")
        print(f"  Check status: az group show --name {name}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ✗ Failed: {e.stderr.decode() if e.stderr else 'Unknown error'}")
        return False


def delete_service_bus_queue(resource_group, namespace, queue_name):
    """Delete Service Bus queue."""
    import subprocess

    print(f"\nDeleting Service Bus queue '{queue_name}'...")

    try:
        subprocess.run(
            [
                "az", "servicebus", "queue", "delete",
                "--name", queue_name,
                "--namespace-name", namespace,
                "--resource-group", resource_group
            ],
            check=True,
            capture_output=True
        )
        print(f"  ✓ Queue deleted")
        return True
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode()
        if "not found" in error_msg.lower():
            print(f"  Queue not found (already deleted?)")
            return True
        print(f"  ✗ Failed: {error_msg}")
        return False


def delete_service_bus_namespace(resource_group, namespace):
    """Delete Service Bus namespace."""
    import subprocess

    print(f"\nDeleting Service Bus namespace '{namespace}'...")

    try:
        subprocess.run(
            [
                "az", "servicebus", "namespace", "delete",
                "--name", namespace,
                "--resource-group", resource_group
            ],
            check=True,
            capture_output=True
        )
        print(f"  ✓ Namespace deleted")
        return True
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode()
        if "not found" in error_msg.lower():
            print(f"  Namespace not found (already deleted?)")
            return True
        print(f"  ✗ Failed: {error_msg}")
        return False


def delete_storage_containers(connection_string):
    """Delete blob containers."""
    import subprocess

    containers = ["results", "uploads"]

    print("\nDeleting blob containers...")
    for container in containers:
        try:
            subprocess.run(
                [
                    "az", "storage", "container", "delete",
                    "--name", container,
                    "--connection-string", connection_string
                ],
                check=True,
                capture_output=True
            )
            print(f"  ✓ {container}")
        except subprocess.CalledProcessError:
            print(f"  Container '{container}' not found (already deleted?)")


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
    except subprocess.CalledProcessError:
        return None


def delete_storage_account(resource_group, account_name):
    """Delete storage account."""
    import subprocess

    print(f"\nDeleting storage account '{account_name}'...")

    try:
        subprocess.run(
            [
                "az", "storage", "account", "delete",
                "--name", account_name,
                "--resource-group", resource_group,
                "--yes"
            ],
            check=True,
            capture_output=True
        )
        print(f"  ✓ Storage account deleted")
        return True
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode()
        if "not found" in error_msg.lower():
            print(f"  Storage account not found (already deleted?)")
            return True
        print(f"  ✗ Failed: {error_msg}")
        return False


def main():
    """Run Azure teardown."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Destroy Azure resources for Deepr"
    )
    parser.add_argument(
        "--resource-group",
        default="deepr-resources",
        help="Resource group name (default: deepr-resources)"
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
    parser.add_argument(
        "--delete-resource-group",
        action="store_true",
        help="Delete entire resource group (deletes ALL resources)"
    )
    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Skip confirmation prompts"
    )

    args = parser.parse_args()

    print("="*60)
    print("Deepr Azure Environment Teardown")
    print("="*60)
    print()

    if not check_azure_cli():
        return 1

    if args.delete_resource_group:
        # Delete entire resource group (simplest)
        return 0 if delete_resource_group(args.resource_group, args.force) else 1

    # Delete individual resources
    print("\nConfiguration:")
    print(f"  Resource Group: {args.resource_group}")
    print(f"  Storage Account: {args.storage_account}")
    print(f"  Service Bus: {args.servicebus_namespace}")
    print(f"  Queue: {args.queue_name}")

    if not args.force:
        print("\n⚠  WARNING: This will DELETE Azure resources and all data")
        response = input("Continue? (y/N): ")
        if response.lower() != 'y':
            print("Cancelled")
            return 0

    # Delete Service Bus queue
    delete_service_bus_queue(args.resource_group, args.servicebus_namespace, args.queue_name)

    # Delete Service Bus namespace
    delete_service_bus_namespace(args.resource_group, args.servicebus_namespace)

    # Delete storage containers
    conn_str = get_storage_connection_string(args.resource_group, args.storage_account)
    if conn_str:
        delete_storage_containers(conn_str)

    # Delete storage account
    delete_storage_account(args.resource_group, args.storage_account)

    print("\n" + "="*60)
    print("✓ Teardown complete")
    print()
    print("Note: Resource group still exists (but should be empty)")
    print(f"To delete resource group: python scripts/destroy_azure.py --delete-resource-group")
    print("="*60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
