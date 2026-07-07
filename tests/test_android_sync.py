from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from main import app
import os

os.environ["SECRET_KEY"] = "test_secret_key"
client = TestClient(app)

@patch("routers.android.db")
def test_get_maquinas(mock_db):
    """Prueba que el endpoint devuelva las maquinas en el formato JSON esperado"""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_db.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor

    # Setup para la query principal de maquinas
    mock_cursor.fetchall.return_value = [
        (1, "Máquina A"),
        (2, "Máquina B")
    ]

    response = client.get("/maquinas")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0] == {"id": 1, "nombre": "Máquina A"}
    assert data[1] == {"id": 2, "nombre": "Máquina B"}

@patch("routers.android.db")
def test_get_procesos(mock_db):
    """Prueba que el endpoint de procesos devuelva la lista correcta"""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_db.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor

    mock_cursor.fetchall.return_value = [
        (1, "Proceso 1"),
        (2, "Proceso 2")
    ]

    response = client.get("/procesos/10") # id de orden = 10
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0] == {"id": 1, "nombre": "Proceso 1"}
    assert data[1] == {"id": 2, "nombre": "Proceso 2"}
