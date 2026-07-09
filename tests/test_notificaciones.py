import pytest
from datetime import date
from unittest.mock import patch, MagicMock
from notificaciones import (
    construir_mensaje_ausencias, 
    calcular_fecha_dia_habil_anterior,
    notificar_ausencias_operarios
)

def test_construir_mensaje_vacio():
    # Cuando la lista esta vacia, debe devolver None
    res = construir_mensaje_ausencias(date(2026, 7, 9), [])
    assert res is None

def test_construir_mensaje_con_operarios():
    operarios = [{'id': 1, 'nombre': 'Juan Perez'}, {'id': 2, 'nombre': 'Maria Lopez'}]
    res = construir_mensaje_ausencias(date(2026, 7, 9), operarios)
    
    assert res is not None
    assert "09/07/2026" in res
    assert "Juan Perez" in res
    assert "Maria Lopez" in res
    assert "Total: 2" in res

@patch('notificaciones.datetime')
def test_calcular_fecha_dia_habil_anterior_lunes(mock_datetime):
    # Simular que "hoy" es lunes 13 de Julio de 2026 (0 es lunes en Python)
    import zoneinfo
    from datetime import datetime
    
    # Crear un mock de fecha que actúe como lunes
    mock_now = datetime(2026, 7, 13, 12, 0, 0, tzinfo=zoneinfo.ZoneInfo("America/Bogota"))
    mock_datetime.now.return_value = mock_now
    
    fecha = calcular_fecha_dia_habil_anterior()
    
    # El viernes anterior al 13 de Julio es el 10 de Julio
    assert fecha == date(2026, 7, 10)

@patch('notificaciones.datetime')
def test_calcular_fecha_dia_habil_anterior_martes(mock_datetime):
    # Simular que "hoy" es martes 14 de Julio de 2026
    import zoneinfo
    from datetime import datetime
    
    mock_now = datetime(2026, 7, 14, 12, 0, 0, tzinfo=zoneinfo.ZoneInfo("America/Bogota"))
    mock_datetime.now.return_value = mock_now
    
    fecha = calcular_fecha_dia_habil_anterior()
    
    # El lunes anterior al 14 de Julio es el 13 de Julio
    assert fecha == date(2026, 7, 13)

@patch('notificaciones.enviar_whatsapp_background')
@patch('notificaciones.obtener_telefonos_jefe_tickets')
@patch('notificaciones.obtener_operarios_sin_registro')
@patch('notificaciones.calcular_fecha_dia_habil_anterior')
def test_notificar_ausencias_operarios_mock(mock_fecha, mock_ops, mock_tels, mock_wpp):
    mock_fecha.return_value = date(2026, 7, 9)
    mock_ops.return_value = [{'id': 1, 'nombre': 'Juan Perez'}]
    mock_tels.return_value = ['+573001234567']
    
    res = notificar_ausencias_operarios()
    
    assert res['enviado'] is True
    assert res['operarios_sin_registro'] == 1
    mock_wpp.assert_called_once()
