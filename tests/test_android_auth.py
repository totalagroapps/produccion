from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from main import app
import os

os.environ["SECRET_KEY"] = "test_secret_key"

client = TestClient(app)

@patch("routers.android.db")
@patch("routers.android.verify_password")
def test_login_android_success(mock_verify, mock_db):
    """Prueba que el login exitoso devuelva un Token Bearer y datos del operario"""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_db.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    
    # Simular la respuesta de PostgreSQL: (id, username, password, role, operario_id, nombre, debe_cambiar)
    mock_cursor.fetchone.return_value = (10, "operador1", "hashed_pwd", "operario", 5, "Operador Juan", False)
    mock_verify.return_value = True

    response = client.post("/android/login", json={"username": "operador1", "password": "123"})
    
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert data["usuario"]["role"] == "operario"
    assert data["operario"]["id"] == 5

@patch("routers.android.db")
def test_login_android_user_not_found(mock_db):
    """Prueba que si el usuario no existe se devuelva 401"""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_db.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    
    # DB vacía
    mock_cursor.fetchone.return_value = None

    response = client.post("/android/login", json={"username": "no_existo", "password": "123"})
    
    assert response.status_code == 401
    assert response.json()["detail"] == "Usuario o password incorrecto"

@patch("routers.android.db")
@patch("routers.android.verify_password")
def test_login_android_invalid_password(mock_verify, mock_db):
    """Prueba de contraseña inválida"""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_db.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    
    mock_cursor.fetchone.return_value = (10, "operador1", "hashed_pwd", "operario", 5, "Operador Juan", False)
    # Simular fallo de bcrypt
    mock_verify.return_value = False

    response = client.post("/android/login", json={"username": "operador1", "password": "bad_password"})
    
    assert response.status_code == 401
    assert response.json()["detail"] == "Usuario o password incorrecto"
