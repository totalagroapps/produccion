from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from main import app
from routers.android import generar_token_android
import os

os.environ["SECRET_KEY"] = "test_secret_key"
client = TestClient(app)

def get_auth_header():
    token = generar_token_android(user_id=10, username="operador1", role="operario", operario_id=5)
    return {"Authorization": f"Bearer {token}"}

@patch("routers.android.db")
def test_registro_produccion_success(mock_db):
    """Prueba que un operario pueda registrar producción correctamente"""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_db.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor

    # Auth: usuario actual (devuelve row de BD)
    mock_cursor.fetchone.return_value = (10, "operador1", "operario", 5, "Operador Juan", False)

    # Datos que enviaría la app de Android
    payload = {
        "orden_id": 20,
        "actividad_id": 100,
        "cantidad": 50,
        "tiempo": 120, # segundos
        "inicio": "2026-07-07 10:00:00",
        "fin": "2026-07-07 10:02:00"
    }

    # El registro hace varias consultas: INSERT y UPDATE. 
    # fetchone en la última línea trae SUM(cantidad_realizada), SUM(cantidad_total) para recalcular el porcentaje de la orden.
    mock_cursor.fetchone.side_effect = [
        (10, "operador1", "operario", 5, "Operador Juan", False), # Auth
        (50, 100) # SUMs de cantidades
    ]

    response = client.post("/registro_android", json=payload, headers=get_auth_header())
    
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    
    # Verificar que hizo los execute correctamente (al menos 3 veces: INSERT, UPDATE orden_actividades, UPDATE ordenes)
    assert mock_cursor.execute.call_count >= 3

@patch("routers.android.db")
def test_registro_produccion_invalid_data(mock_db):
    """Prueba que el sistema rechace datos no numéricos (evitando errores 500)"""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_db.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor

    # Auth
    mock_cursor.fetchone.return_value = (10, "operador1", "operario", 5, "Operador Juan", False)

    # Payload inválido: 'cantidad' es un string de texto
    payload = {
        "orden_id": 20,
        "actividad_id": 100,
        "cantidad": "cincuenta_y_tres", 
        "tiempo": 120
    }

    response = client.post("/registro_android", json=payload, headers=get_auth_header())
    
    assert response.status_code == 400
    assert response.json()["detail"] == "Campos numericos invalidos"
