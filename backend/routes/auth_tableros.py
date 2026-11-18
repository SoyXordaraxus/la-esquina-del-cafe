from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["Tableros"])

# ==========================================
# 1. RUTA DEL PANEL PRINCIPAL (02_Panel)
# ==========================================
@router.get("/dashboard/resumen")
def obtener_resumen_dia():
    return {
        "estado_turno": "Regla PEPS activa",
        "metricas": {
            "ventas_dia": 4850.00,
            "tickets_dia": 28,
            "insumos_bajo_minimo": 3,
            "lotes_proximos_caducar": 4,
            "mermas_mes": 320.00,
            "registros_mermas": 2
        },
        "alertas": [
            {
                "insumo": "Leche entera 1 L",
                "lote": "LA-041126",
                "vencimiento": "Venció hace 2 días",
                "vencimiento_tipo": "rojo",
                "cantidad_restante": "12 L",
                "estado": "Caducado",
                "estado_tipo": "rojo",
                "accion": "Registrar merma"
            },
            {
                "insumo": "Yogur natural 150 g",
                "lote": "YO-051126",
                "vencimiento": "Venció ayer",
                "vencimiento_tipo": "rojo",
                "cantidad_restante": "18 piezas",
                "estado": "Caducado",
                "estado_tipo": "rojo",
                "accion": "Registrar merma"
            },
            {
                "insumo": "Café en grano 1 kg",
                "lote": "CA-281026",
                "vencimiento": "Mínimo: 3 kg",
                "vencimiento_tipo": "neutro",
                "cantidad_restante": "1.5 kg",
                "estado": "Stock bajo",
                "estado_tipo": "rojo",
                "accion": "Reabastecer"
            },
            {
                "insumo": "Queso crema",
                "lote": "QC-101126",
                "vencimiento": "Vence en 4 días",
                "vencimiento_tipo": "amarillo",
                "cantidad_restante": "2.5 kg",
                "estado": "Por vencer",
                "estado_tipo": "amarillo",
                "accion": "Ver lote"
            }
        ]
    }


# ==========================================
# 2. LÓGICA Y RUTA DEL SEMÁFORO (06_Inventario)
# ==========================================
def calcular_estado_semaforo(existencia_actual: float, existencia_minima: float) -> dict:
    porcentaje = round((existencia_actual / existencia_minima) * 100) if existencia_minima > 0 else 100

    if porcentaje > 120:
        return {
            "color": "verde",
            "etiqueta": "Existencias suficientes",
            "porcentaje": porcentaje
        }
    elif porcentaje > 100:
        return {
            "color": "amarillo",
            "etiqueta": "Existencias bajas",
            "porcentaje": porcentaje
        }
    else:
        return {
            "color": "rojo",
            "etiqueta": "Existencias críticas",
            "porcentaje": porcentaje
        }


@router.get("/inventario/semaforo")
def obtener_inventario_semaforo():
    # Productos mock idénticos al boceto de Figma (listos para conectar a MySQL)
    productos_mock = [
        {"id": 1, "codigo": "AB-001", "nombre": "Arroz a granel", "categoria": "Abarrotes", "subcategoria": "Granos", "unidad": "kg", "existencia_actual": 180, "existencia_minima": 100},
        {"id": 2, "codigo": "AB-002", "nombre": "Frijol negro a granel", "categoria": "Abarrotes", "subcategoria": "Granos", "unidad": "kg", "existencia_actual": 110, "existencia_minima": 100},
        {"id": 3, "codigo": "LA-001", "nombre": "Leche entera 1 L", "categoria": "Lácteos", "subcategoria": "Leches", "unidad": "unidades", "existencia_actual": 100, "existencia_minima": 100},
        {"id": 4, "codigo": "AB-003", "nombre": "Aceite vegetal 1 L", "categoria": "Abarrotes", "subcategoria": "Aceites", "unidad": "unidades", "existencia_actual": 150, "existencia_minima": 100},
        {"id": 5, "codigo": "AB-004", "nombre": "Azúcar a granel", "categoria": "Abarrotes", "subcategoria": "Endulzantes", "unidad": "kg", "existencia_actual": 60, "existencia_minima": 50},
        {"id": 6, "codigo": "LA-002", "nombre": "Yogur natural 150 g", "categoria": "Lácteos", "subcategoria": "Derivados", "unidad": "unidades", "existencia_actual": 24, "existencia_minima": 40},
    ]

    resultado = []
    resumen = {"verde": 0, "amarillo": 0, "rojo": 0}

    for prod in productos_mock:
        estado = calcular_estado_semaforo(prod["existencia_actual"], prod["existencia_minima"])
        resumen[estado["color"]] += 1
        resultado.append({
            **prod,
            "semaforo": estado
        })

    return {
        "resumen": resumen,
        "total": len(resultado),
        "productos": resultado
    }