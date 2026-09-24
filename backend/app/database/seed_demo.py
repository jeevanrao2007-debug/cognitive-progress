from app.database.engine import create_session_factory
from app.database.seed import seed_demo_data


def main() -> None:
    session_factory = create_session_factory()
    with session_factory() as session:
        project = seed_demo_data(session)
        print(f"Seeded project: {project.name} ({project.project_id})")


if __name__ == "__main__":
    main()
