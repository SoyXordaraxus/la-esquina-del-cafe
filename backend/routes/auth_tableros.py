from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["Tableros"])

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