"""Connection pool manager for PostgreSQL with TimescaleDB."""
import os
import logging
from sqlalchemy import create_engine, pool
from sqlalchemy.orm import sessionmaker, scoped_session

logger = logging.getLogger(__name__)

def get_engine(database_url: str = None):
    """Create SQLAlchemy engine with connection pooling."""
    if database_url is None:
        database_url = os.environ.get('DATABASE_URL', 'sqlite:///fuel_tank.db')
    
    pool_size = int(os.environ.get('DB_POOL_SIZE', '20'))
    max_overflow = int(os.environ.get('DB_MAX_OVERFLOW', '40'))
    pool_timeout = int(os.environ.get('DB_POOL_TIMEOUT', '30'))
    pool_recycle = int(os.environ.get('DB_POOL_RECYCLE', '3600'))
    
    engine = create_engine(
        database_url,
        poolclass=pool.QueuePool if not database_url.startswith('sqlite') else pool.NullPool,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_recycle=pool_recycle,
        echo=False,
        connect_args={
            'sslmode': os.environ.get('DB_SSLMODE', 'prefer'),
            'sslrootcert': os.environ.get('DB_SSLROOTCERT', None),
        } if database_url.startswith('postgresql') else {}
    )
    
    logger.info(f"Database engine created with pool_size={pool_size}, max_overflow={max_overflow}")
    return engine

def get_session_factory(engine):
    """Create scoped session factory."""
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return scoped_session(session_factory)

def init_db(db):
    """Initialize database with connection pooling."""
    engine = get_engine()
    db.init_app(current_app) if hasattr(db, 'init_app') else None
    return engine, get_session_factory(engine)
