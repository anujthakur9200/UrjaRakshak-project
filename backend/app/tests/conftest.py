"""
Pytest configuration and shared fixtures.

Tests that need DB use mocked sessions.
Tests that need pure engine logic use the engine directly.
"""
import pytest
import os

# Set test environment before any app imports
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_urjarakshak")
os.environ.setdefault("SECRET_KEY", "test-secret-key-minimum-32-characters-long!!")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DEBUG", "true")
