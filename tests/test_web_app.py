import web.auth.database as database
import web.auth.routes as auth_routes
import web.app as web_app
from werkzeug.security import check_password_hash


def test_account_analysis_and_history_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "users.sqlite3")
    database.init_database()
    monkeypatch.setattr(auth_routes, "smtp_configuration_error", lambda: None)
    monkeypatch.setattr(web_app, "scrape_products", lambda _url, pages=1: [{
        "product_name": "Demo kettle", "price": "49.50", "currency": "USD",
        "rating": 4.5, "availability": "InStock", "category": "Kitchen",
        "product_link": "https://shop.example/product/1", "website_name": "shop.example",
    }])
    client = web_app.app.test_client()

    signup = client.post("/api/auth/signup", json={
        "name": "Alex Example", "email": "alex@example.test", "password": "secure-pass-123",
    })
    assert signup.status_code == 201
    connection = database.get_connection()
    password_hash = connection.execute("SELECT password_hash FROM users WHERE email=?", ("alex@example.test",)).fetchone()["password_hash"]
    connection.close()
    assert password_hash != "secure-pass-123"
    assert check_password_hash(password_hash, "secure-pass-123")
    assert client.post("/api/auth/login", json={
        "email": "alex@example.test", "password": "secure-pass-123",
    }).status_code == 200

    analysis = client.post("/api/analyze", json={
        "url": "https://shop.example/category/kitchen", "pages": 1,
    })
    assert analysis.status_code == 200
    body = analysis.get_json()
    assert body["statistics"]["average_price"] == 49.5
    assert body["products"][0]["currency"] == "USD"
    assert body["source_url"] == "https://shop.example/category/kitchen"

    history = client.get("/api/history").get_json()["history"]
    assert len(history) == 1
    assert history[0]["products_found"] == 1
    analysis_id = analysis.get_json()["analysis_id"]
    detail = client.get(f"/api/history/{analysis_id}")
    assert detail.status_code == 200
    assert detail.get_json()["products"][0]["product_link"] == "https://shop.example/product/1"
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/history").status_code == 401


def test_analysis_requires_auth_and_page_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "users.sqlite3")
    database.init_database()
    client = web_app.app.test_client()
    assert client.post("/api/analyze", json={"url": "https://example.com"}).status_code == 401
    connection = database.get_connection()
    cursor = connection.execute(
        "INSERT INTO users(name, email, password_hash) VALUES (?, ?, ?)",
        ("Test User", "test@example.test", "unused"),
    )
    connection.commit()
    user_id = cursor.lastrowid
    connection.close()
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["session_version"] = 0
    response = client.post("/api/analyze", json={"url": "https://example.com", "pages": 21})
    assert response.status_code == 400




def test_dashboard_redirects_unauthenticated_visitors_to_login(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "users.sqlite3")
    database.init_database()
    response = web_app.app.test_client().get("/dashboard")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_import_page_requires_auth_and_renders_import_flow(tmp_path, monkeypatch):
    client = web_app.app.test_client()
    response = client.get("/import")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")

    client = _authenticated_client(tmp_path, monkeypatch)
    response = client.get("/import")
    assert response.status_code == 200
    assert b"Choose a product file" in response.data
    assert b"Import data" in response.data




def test_password_recovery_hides_otp_and_invalidates_sessions(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "users.sqlite3")
    database.init_database()
    monkeypatch.setattr(auth_routes, "smtp_configuration_error", lambda: None)
    delivered = {}
    monkeypatch.setattr(auth_routes, "send_otp_email", lambda email, code: delivered.update(email=email, code=code))
    client = web_app.app.test_client()
    assert client.post("/api/auth/signup", json={
        "name": "Alex Example", "email": "alex@example.test", "password": "old-secure-pass",
    }).status_code == 201
    client.post("/api/auth/login", json={"email": "alex@example.test", "password": "old-secure-pass"})
    response = client.post("/api/auth/forgot-password", json={"email": "alex@example.test"})
    assert response.status_code == 202
    assert "code" not in response.get_json()
    assert len(delivered["code"]) == 6

    connection = database.get_connection()
    otp_row = connection.execute("SELECT otp_hash FROM password_reset_requests").fetchone()
    assert otp_row["otp_hash"] != delivered["code"]
    connection.close()

    verify = client.post("/api/auth/verify-otp", json={"email": delivered["email"], "otp": delivered["code"]})
    assert verify.status_code == 200
    reset_token = verify.get_json()["reset_token"]
    assert client.post("/api/auth/reset-password", json={
        "reset_token": reset_token, "new_password": "new-secure-pass", "confirm_password": "mismatch-pass",
    }).status_code == 400
    reset = client.post("/api/auth/reset-password", json={
        "reset_token": reset_token, "new_password": "new-secure-pass", "confirm_password": "new-secure-pass",
    })
    assert reset.status_code == 200
    assert client.get("/api/auth/profile").status_code == 401
    assert client.post("/api/auth/login", json={"email": "alex@example.test", "password": "new-secure-pass"}).status_code == 200


def test_forgot_password_response_does_not_reveal_unknown_email(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "users.sqlite3")
    database.init_database()
    monkeypatch.setattr(auth_routes, "smtp_configuration_error", lambda: None)
    delivered = []
    monkeypatch.setattr(auth_routes, "send_otp_email", lambda *_args: delivered.append(True))
    response = web_app.app.test_client().post("/api/auth/forgot-password", json={"email": "nobody@example.test"})
    assert response.status_code == 202
    assert response.get_json() == auth_routes.RESET_RESPONSE
    assert delivered == []


def test_missing_smtp_configuration_returns_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "users.sqlite3")
    database.init_database()
    monkeypatch.setattr(auth_routes, "smtp_configuration_error", lambda: "SMTP is not configured.")
    response = web_app.app.test_client().post("/api/auth/forgot-password", json={"email": "alex@example.test"})
    assert response.status_code == 503
    assert response.get_json() == {"error": "SMTP is not configured."}


def test_failed_smtp_delivery_invalidates_otp(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "users.sqlite3")
    database.init_database()
    monkeypatch.setattr(auth_routes, "smtp_configuration_error", lambda: None)
    monkeypatch.setattr(auth_routes, "send_otp_email", lambda *_args: (_ for _ in ()).throw(OSError("offline")))
    client = web_app.app.test_client()
    client.post("/api/auth/signup", json={"name": "Alex", "email": "alex@example.test", "password": "secure-pass-123"})
    response = client.post("/api/auth/forgot-password", json={"email": "alex@example.test"})
    assert response.status_code == 202
    connection = database.get_connection()
    record = connection.execute("SELECT otp_hash, expires_at FROM password_reset_requests").fetchone()
    connection.close()
    assert record["otp_hash"] is None
    assert record["expires_at"] <= int(__import__("time").time())



def _authenticated_client(tmp_path, monkeypatch):
    from werkzeug.security import generate_password_hash
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "users.sqlite3")
    database.init_database()
    connection = database.get_connection()
    cursor = connection.execute(
        "INSERT INTO users(name, email, password_hash) VALUES (?, ?, ?)",
        ("Import User", "import@example.test", generate_password_hash("password")),
    )
    connection.commit()
    user_id = cursor.lastrowid
    connection.close()
    client = web_app.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["session_version"] = 0
    return client


def test_csv_import_uses_cleaning_and_saved_analysis_export(tmp_path, monkeypatch):
    from io import BytesIO
    client = _authenticated_client(tmp_path, monkeypatch)
    upload = BytesIO(
        b"product_name,price,currency,product_link\n"
        b"Kettle,49.50,USD,https://shop.example/kettle\n"
        b"Invalid,not-a-price,USD,https://shop.example/invalid\n"
    )
    response = client.post(
        "/api/import",
        data={"file": (upload, "products.csv")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    result = response.get_json()
    assert result["products"][0]["product_name"] == "Kettle"
    assert result["statistics"]["average_price"] == 49.5
    assert result["products"][0]["product_link"] == "https://shop.example/kettle"

    exported = client.get(f"/api/history/{result['analysis_id']}/export/csv")
    assert exported.status_code == 200
    assert b"Kettle" in exported.data
    assert b"product_link" in exported.data


def test_excel_import_and_export_routes(tmp_path, monkeypatch):
    from io import BytesIO
    import pandas as pd
    client = _authenticated_client(tmp_path, monkeypatch)
    monkeypatch.setattr(web_app.pd, "read_excel", lambda *_args, **_kwargs: pd.DataFrame([
        {"product_name": "Desk", "price": 125, "currency": "USD"},
    ]))
    imported = client.post(
        "/api/import",
        data={"file": (BytesIO(b"workbook"), "products.xlsx")},
        content_type="multipart/form-data",
    )
    assert imported.status_code == 200

    monkeypatch.setattr(pd.DataFrame, "to_excel", lambda self, output, **_kwargs: output.write(b"xlsx-data"))
    exported = client.get(f"/api/history/{imported.get_json()['analysis_id']}/export/xlsx")
    assert exported.status_code == 200
    assert exported.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert exported.data == b"xlsx-data"


def test_import_rejects_unsupported_format_and_requires_auth(tmp_path, monkeypatch):
    from io import BytesIO
    client = web_app.app.test_client()
    assert client.post("/api/import").status_code == 401
    client = _authenticated_client(tmp_path, monkeypatch)
    response = client.post(
        "/api/import",
        data={"file": (BytesIO(b"data"), "products.xls")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400



def test_analysis_saves_actual_pages_when_requested_pages_are_unavailable(tmp_path, monkeypatch):
    from scraper.scraper import ScrapeResult
    client = _authenticated_client(tmp_path, monkeypatch)
    monkeypatch.setattr(web_app, "scrape_products", lambda *_args, **_kwargs: ScrapeResult([{
        "product_name": "Kettle", "price": "20", "currency": "USD",
        "product_link": "https://shop.example/kettle", "website_name": "shop.example",
    }], pages_scraped=2, pages_requested=5))

    response = client.post("/api/analyze", json={"url": "https://shop.example/search", "pages": 5})
    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "PARTIAL"
    assert body["pages_scraped"] == 2
    assert body["pages_requested"] == 5
    history = client.get("/api/history").get_json()["history"]
    assert history[0]["pages_scraped"] == 2
