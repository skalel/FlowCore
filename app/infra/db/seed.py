from app.infra.db.seeds.seed_users import seed_default_user
from app.infra.db.session import SessionLocal


def main():
    print("🌱 Iniciando o processo de Seed no banco de dados...")
    db = SessionLocal()

    try:
        system_user = seed_default_user(db)
        print(f"Usuário de Sistema: {system_user.name} ({system_user.email})")

        print("Seed finalizado com sucesso!")

    except Exception as e:
        print(f"Erro crítico ao rodar os seeds: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()
