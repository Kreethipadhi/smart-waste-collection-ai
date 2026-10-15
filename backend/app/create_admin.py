from getpass import getpass

from .config import Settings
from .repository import Repository
from .security import hash_password


def main():
    settings = Settings.from_environment()
    repo = Repository(settings.database_url)
    try:
        if settings.environment == 'development':
            repo.initialize_schema()
        else:
            repo.check_connection(require_migrations=True)
        if repo.user_count():
            raise SystemExit('An account already exists. No default or reset administrator is created by this command.')

        username = input('Administrator username: ').strip().lower()
        if not username or len(username) > 254:
            raise SystemExit('Username must contain 1 to 254 characters.')
        password = getpass('Administrator password (12+ characters): ')
        confirmation = getpass('Confirm password: ')
        if password != confirmation:
            raise SystemExit('Passwords did not match; no account was created.')
        password_hash = hash_password(password)
        user_id = repo.create_user(username, password_hash, 'admin')
        repo.save_audit(user_id, 'administrator_created', 'user', str(user_id), {'username': username})
        print('Administrator created. The password was not stored in plain text.')
    finally:
        repo.dispose()


if __name__ == '__main__':
    main()
