import os
import uuid

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# 1. SOBRESCREVE A VARIÁVEL DE AMBIENTE ANTES DE TUDO!
# Substitua "DATABASE_URL" pelo nome exato da variável que você usa no seu .env
TEST_DATABASE_URL = (
    "postgresql://flowspace:T3st%40FlowSp4ce@localhost:5433/flowspace_test"
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

# 2. Só agora importamos a aplicação, garantindo que o Pydantic/Settings leia a URL de teste
from app.api.auth_deps import get_current_user
from app.api.deps import get_db
from app.infra.db.orm_models import Base, User
from main import app

engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session")
def setup_database():
    """Roda as migrações do Alembic num banco de testes perfeitamente limpo."""

    # 1. "Nuke" total: Apaga o schema public com CASCADE (destrói todas as tabelas e ENUMs de uma vez)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE;"))
        conn.execute(text("CREATE SCHEMA public;"))

    # 2. Configura o Alembic para a URL de testes
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL.replace("%", "%%"))

    # 3. Roda as migrações (incluindo a criação dos ENUMs e os Seads)
    command.upgrade(alembic_cfg, "head")

    yield  # Os testes rodam aqui

    # 4. Limpa o banco após o fim de todos os testes para não deixar lixo
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE;"))
        conn.execute(text("CREATE SCHEMA public;"))


@pytest.fixture
def db_session(setup_database):
    """Garante transações limpas para cada teste isolado."""
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def test_user(db_session):
    """Cria um usuário falso para injetarmos nas rotas protegidas."""
    user = User(
        id=uuid.uuid4(),
        name="Usuário de Teste",
        email="teste@flowspace.com",
        password_hash="fake_hash",
        plan_tier="free",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def client(db_session, test_user):
    """Cria o cliente HTTP burlando a autenticação."""

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    def override_get_current_user():
        return test_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
