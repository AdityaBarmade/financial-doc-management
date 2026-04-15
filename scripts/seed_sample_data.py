"""
scripts/seed_sample_data.py — Sample Data Seeder

Creates sample users, roles, and documents for testing.
Run: python scripts/seed_sample_data.py
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import AsyncSessionLocal, init_db
from app.services.auth_service import AuthService
from app.schemas.auth import UserRegisterRequest


# ─── Sample Users ─────────────────────────────────────────────────────────────
SAMPLE_USERS = [
    {
        "email": "admin@financial.com",
        "full_name": "System Administrator",
        "password": "AdminPass123",
        "company": "Financial Systems Inc.",
    },
    {
        "email": "analyst@acmecorp.com",
        "full_name": "Alice Analyst",
        "password": "AnalystPass123",
        "company": "Acme Corp",
    },
    {
        "email": "auditor@regulator.gov",
        "full_name": "Bob Auditor",
        "password": "AuditorPass123",
        "company": "Regulatory Office",
    },
    {
        "email": "client@investco.com",
        "full_name": "Carol Client",
        "password": "ClientPass123",
        "company": "Invest Co Ltd",
    },
]

# Sample role assignments (email → role)
ROLE_ASSIGNMENTS = {
    "admin@financial.com": "admin",
    "analyst@acmecorp.com": "analyst",
    "auditor@regulator.gov": "auditor",
    "client@investco.com": "client",
}


async def seed():
    """Seed database with sample data."""
    print("🌱 Initializing database...")
    await init_db()

    async with AsyncSessionLocal() as db:
        # Seed default roles first
        print("🔑 Seeding default roles and permissions...")
        await AuthService.seed_default_roles(db)

        # Create sample users
        from sqlalchemy import select
        from app.models.user import User
        from app.models.role import Role
        from app.services.user_service import UserService

        service = AuthService(db)
        user_service = UserService(db)

        for user_data in SAMPLE_USERS:
            # Check if already exists
            exists = (await db.execute(
                select(User).where(User.email == user_data["email"])
            )).scalar_one_or_none()

            if exists:
                print(f"   ⚠️  User {user_data['email']} already exists, skipping")
                continue

            user = await service.register(UserRegisterRequest(**user_data))
            print(f"   ✅ Created user: {user.email} (id={user.id})")

            # Assign role
            target_role = ROLE_ASSIGNMENTS.get(user_data["email"])
            if target_role:
                try:
                    await user_service.assign_role(user.id, target_role)
                    print(f"      → Assigned role: {target_role}")
                except Exception as e:
                    print(f"      ⚠️  Could not assign role: {e}")

        print("\n🎉 Sample data seeded successfully!")
        print("\n📋 Test Credentials:")
        for user_data in SAMPLE_USERS:
            role = ROLE_ASSIGNMENTS.get(user_data["email"], "client")
            print(f"   [{role.upper():8}] {user_data['email']} / {user_data['password']}")


if __name__ == "__main__":
    asyncio.run(seed())
