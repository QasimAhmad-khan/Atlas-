import ssl
from uuid import uuid4

from sqlalchemy.engine import make_url

from atlaspipe.config import Settings
from atlaspipe.db.session import create_engine


def test_database_password_is_encoded_and_tls_verifies_hostname() -> None:
    fixture_value = "a@b/#" + uuid4().hex
    settings = Settings(db_host="database.example", db_password=fixture_value, database_ssl=True)
    url = make_url(settings.database_url)
    assert url.password == fixture_value
    engine = create_engine(settings)
    args, parameters = engine.sync_engine.dialect.create_connect_args(url)
    assert args == []
    assert parameters["password"] == fixture_value
    context = ssl.create_default_context(cafile="certs/global-bundle.pem")
    assert context.check_hostname
    assert context.verify_mode == ssl.CERT_REQUIRED
