#!/usr/bin/env python3
"""Migration script for expert profiles.

Migrates existing expert profiles to the new format with:
- TemporalState and FreshnessChecker composition
- Monthly spending reset date handling
- Schema version tracking

Usage:
    python scripts/migrate_expert_profiles.py [--dry-run] [--verbose]
    
Options:
    --dry-run   Show what would be migrated without making changes
    --verbose   Show detailed migration information
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# Schema version for migrated profiles
CURRENT_SCHEMA_VERSION = "2.0.0"


def get_experts_dir() -> Path:
    """Get the experts data directory."""
    return Path("data/experts")


def find_expert_profiles(base_dir: Path) -> List[Path]:
    """Find all expert profile files.
    
    Args:
        base_dir: Base experts directory
        
    Returns:
        List of profile.json paths
    """
    profiles = []
    
    if not base_dir.exists():
        return profiles
    
    for expert_dir in base_dir.iterdir():
        if expert_dir.is_dir():
            profile_path = expert_dir / "profile.json"
            if profile_path.exists():
                profiles.append(profile_path)
    
    return profiles


def load_profile(path: Path) -> Optional[Dict]:
    """Load a profile from disk.
    
    Args:
        path: Path to profile.json
        
    Returns:
        Profile dict or None if failed
    """
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"  Error loading {path}: {e}")
        return None


def save_profile(path: Path, data: Dict) -> bool:
    """Save a profile to disk.
    
    Args:
        path: Path to profile.json
        data: Profile data
        
    Returns:
        True if successful
    """
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"  Error saving {path}: {e}")
        return False


def migrate_profile(data: Dict, verbose: bool = False) -> Tuple[Dict, List[str]]:
    """Migrate a profile to the new format.
    
    Args:
        data: Original profile data
        verbose: Show detailed changes
        
    Returns:
        Tuple of (migrated_data, list_of_changes)
    """
    changes = []
    migrated = data.copy()
    
    # Remove any accidentally serialized composed components
    if '_temporal_state' in migrated:
        del migrated['_temporal_state']
        changes.append("Removed _temporal_state (now composed at runtime)")
    
    if '_freshness_checker' in migrated:
        del migrated['_freshness_checker']
        changes.append("Removed _freshness_checker (now composed at runtime)")
    
    # Add missing fields with defaults
    defaults = {
        'description': None,
        'domain': None,
        'source_files': [],
        'research_jobs': [],
        'total_documents': 0,
        'knowledge_cutoff_date': None,
        'last_knowledge_refresh': None,
        'refresh_frequency_days': 90,
        'domain_velocity': 'medium',
        'system_message': None,
        'temperature': 0.7,
        'max_tokens': None,
        'conversations': 0,
        'research_triggered': 0,
        'total_research_cost': 0.0,
        'monthly_learning_budget': 5.0,
        'monthly_spending': 0.0,
        'monthly_spending_reset_date': None,
        'refresh_history': [],
        'provider': 'openai',
        'model': 'gpt-5',
    }
    
    for field, default in defaults.items():
        if field not in migrated:
            migrated[field] = default
            changes.append(f"Added missing field '{field}' with default: {default}")
    
    # Ensure datetime fields are strings (ISO format)
    datetime_fields = [
        'created_at', 'updated_at', 'knowledge_cutoff_date',
        'last_knowledge_refresh', 'monthly_spending_reset_date'
    ]
    
    for field in datetime_fields:
        value = migrated.get(field)
        if value is not None and not isinstance(value, str):
            # Convert datetime to ISO string
            if hasattr(value, 'isoformat'):
                migrated[field] = value.isoformat()
                changes.append(f"Converted {field} to ISO format")
    
    # Add schema version
    if 'schema_version' not in migrated:
        migrated['schema_version'] = CURRENT_SCHEMA_VERSION
        changes.append(f"Added schema_version: {CURRENT_SCHEMA_VERSION}")
    elif migrated['schema_version'] != CURRENT_SCHEMA_VERSION:
        old_version = migrated['schema_version']
        migrated['schema_version'] = CURRENT_SCHEMA_VERSION
        changes.append(f"Updated schema_version: {old_version} -> {CURRENT_SCHEMA_VERSION}")
    
    return migrated, changes


def validate_profile(data: Dict) -> List[str]:
    """Validate a migrated profile.
    
    Args:
        data: Profile data
        
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    # Required fields
    required = ['name', 'vector_store_id', 'created_at', 'updated_at']
    for field in required:
        if field not in data:
            errors.append(f"Missing required field: {field}")
    
    # Validate datetime fields
    datetime_fields = [
        'created_at', 'updated_at', 'knowledge_cutoff_date',
        'last_knowledge_refresh', 'monthly_spending_reset_date'
    ]
    
    for field in datetime_fields:
        value = data.get(field)
        if value is not None:
            try:
                datetime.fromisoformat(value)
            except (ValueError, TypeError):
                errors.append(f"Invalid datetime format for {field}: {value}")
    
    # Validate numeric fields
    numeric_fields = {
        'temperature': (0.0, 2.0),
        'conversations': (0, None),
        'research_triggered': (0, None),
        'total_research_cost': (0.0, None),
        'monthly_learning_budget': (0.0, None),
        'monthly_spending': (0.0, None),
        'total_documents': (0, None),
        'refresh_frequency_days': (1, 365),
    }
    
    for field, (min_val, max_val) in numeric_fields.items():
        value = data.get(field)
        if value is not None:
            if min_val is not None and value < min_val:
                errors.append(f"{field} below minimum: {value} < {min_val}")
            if max_val is not None and value > max_val:
                errors.append(f"{field} above maximum: {value} > {max_val}")
    
    # Validate domain_velocity
    valid_velocities = ['slow', 'medium', 'fast']
    velocity = data.get('domain_velocity')
    if velocity and velocity not in valid_velocities:
        errors.append(f"Invalid domain_velocity: {velocity} (must be one of {valid_velocities})")
    
    return errors


def main():
    parser = argparse.ArgumentParser(description='Migrate expert profiles to new format')
    parser.add_argument('--dry-run', action='store_true', help='Show changes without applying')
    parser.add_argument('--verbose', action='store_true', help='Show detailed information')
    args = parser.parse_args()
    
    experts_dir = get_experts_dir()
    
    print(f"Expert Profile Migration Script")
    print(f"================================")
    print(f"Target schema version: {CURRENT_SCHEMA_VERSION}")
    print(f"Experts directory: {experts_dir}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print()
    
    # Find profiles
    profiles = find_expert_profiles(experts_dir)
    
    if not profiles:
        print("No expert profiles found.")
        return 0
    
    print(f"Found {len(profiles)} expert profile(s)")
    print()
    
    # Process each profile
    migrated_count = 0
    error_count = 0
    skipped_count = 0
    
    for profile_path in profiles:
        expert_name = profile_path.parent.name
        print(f"Processing: {expert_name}")
        
        # Load profile
        data = load_profile(profile_path)
        if data is None:
            error_count += 1
            continue
        
        # Check if already migrated
        if data.get('schema_version') == CURRENT_SCHEMA_VERSION:
            if args.verbose:
                print(f"  Already at schema version {CURRENT_SCHEMA_VERSION}")
            skipped_count += 1
            continue
        
        # Migrate
        migrated, changes = migrate_profile(data, args.verbose)
        
        if args.verbose or args.dry_run:
            for change in changes:
                print(f"  - {change}")
        
        # Validate
        errors = validate_profile(migrated)
        if errors:
            print(f"  Validation errors:")
            for error in errors:
                print(f"    ! {error}")
            error_count += 1
            continue
        
        # Save (unless dry run)
        if not args.dry_run:
            if save_profile(profile_path, migrated):
                print(f"  Migrated successfully ({len(changes)} changes)")
                migrated_count += 1
            else:
                error_count += 1
        else:
            print(f"  Would migrate ({len(changes)} changes)")
            migrated_count += 1
    
    # Summary
    print()
    print(f"Summary")
    print(f"-------")
    print(f"Total profiles: {len(profiles)}")
    print(f"Migrated: {migrated_count}")
    print(f"Skipped (already current): {skipped_count}")
    print(f"Errors: {error_count}")
    
    if args.dry_run:
        print()
        print("This was a dry run. Run without --dry-run to apply changes.")
    
    return 0 if error_count == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
