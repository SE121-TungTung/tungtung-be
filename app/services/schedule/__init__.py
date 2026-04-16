"""
Schedule Package
================
Contains the GA-based schedule optimizer and related services.

Note: The original schedule_service.py remains at app/services/schedule_service.py
and is NOT part of this package to avoid breaking existing imports.
"""
from app.services.schedule.ga_service import ga_schedule_service

__all__ = ["ga_schedule_service"]
