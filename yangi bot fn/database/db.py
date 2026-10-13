from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import inspect, select, text

from config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    from database.models import User, UserSequence

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.run_sync(_upgrade_existing_schema)
    async with SessionLocal() as session:
        users = (await session.scalars(select(User).where(User.public_id.is_(None)))).all()
        for user in users:
            user.telegram_id = user.id
            identity = UserSequence(telegram_id=user.id)
            session.add(identity)
            await session.flush()
            user.public_id = identity.id
        await session.commit()


def _upgrade_existing_schema(connection) -> None:
    inspector = inspect(connection)
    if "users" in inspector.get_table_names():
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        if "language" not in user_columns:
            connection.execute(
                text("ALTER TABLE users ADD COLUMN language VARCHAR(12) NOT NULL DEFAULT 'uz_latn'")
            )
        if "telegram_id" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN telegram_id BIGINT"))
        if "public_id" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN public_id INTEGER"))
        if "has_started" not in user_columns:
            connection.execute(
                text("ALTER TABLE users ADD COLUMN has_started BOOLEAN NOT NULL DEFAULT 1")
            )
        connection.execute(text("UPDATE users SET telegram_id = id WHERE telegram_id IS NULL"))
        connection.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_telegram_id ON users (telegram_id)")
        )
        connection.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_public_id ON users (public_id)")
        )
    if "order_details" in inspector.get_table_names():
        order_detail_columns = {column["name"] for column in inspector.get_columns("order_details")}
        new_columns = {
            "total_amount": "INTEGER NOT NULL DEFAULT 0",
            "customer_name": "VARCHAR(160)",
            "customer_phone": "VARCHAR(40)",
            "customer_address": "VARCHAR(500)",
            "event_type": "VARCHAR(160)",
            "service_name": "VARCHAR(160)",
            "balance_used": "INTEGER NOT NULL DEFAULT 0",
            "invoice_number": "VARCHAR(40)",
            "paid_at": "TIMESTAMP",
        }
        for name, definition in new_columns.items():
            if name not in order_detail_columns:
                connection.execute(
                    text(f"ALTER TABLE order_details ADD COLUMN {name} {definition}")
                )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "ix_order_details_invoice_number ON order_details (invoice_number)"
            )
        )
