from datetime import date, timedelta
from backend.database import SessionLocal
from backend.models import Usuario, Proveedor, Insumo, LoteInsumo, Producto, Venta, Merma

def poblar_base():
    db = SessionLocal()
    try:
        # Evitar duplicar registros si ya se ejecutó antes
        if db.query(Usuario).first():
            print("La base de datos ya contiene registros iniciales.")
            return

        # 1. Usuarios
        admin = Usuario(
            nombre_usuario="Andres Mosso",
            correo="admin@esquinadelcafe.mx",
            contrasena="admin123",
            rol="Administrador",
            estado="Activo"
        )
        cajero = Usuario(
            nombre_usuario="Osvaldo Vazquez",
            correo="osvaldo@esquinadelcafe.mx",
            contrasena="cajero123",
            rol="Cajero",
            estado="Activo"
        )
        db.add_all([admin, cajero])
        db.commit()
        db.refresh(admin)

        # 2. Proveedor
        prov = Proveedor(
            nombre="Distribuidora Café y Lácteos del Centro",
            contacto_nombre="Carlos Méndez",
            telefono="5512345678",
            correo="ventas@distribuidoracafe.mx",
            direccion="Av. Central 450, CDMX"
        )
        db.add(prov)
        db.commit()
        db.refresh(prov)

        # 3. Insumos (coinciden con los diseños de Figma de Panel y Semáforo)
        insumos = [
            Insumo(nombre="Arroz a granel", categoria="Abarrotes", unidad_medida="kg", es_perecedero=False, minimo_reposicion=100),
            Insumo(nombre="Frijol negro a granel", categoria="Abarrotes", unidad_medida="kg", es_perecedero=False, minimo_reposicion=100),
            Insumo(nombre="Leche entera 1 L", categoria="Lácteos", unidad_medida="unidades", es_perecedero=True, minimo_reposicion=100),
            Insumo(nombre="Aceite vegetal 1 L", categoria="Abarrotes", unidad_medida="unidades", es_perecedero=False, minimo_reposicion=100),
            Insumo(nombre="Azúcar a granel", categoria="Abarrotes", unidad_medida="kg", es_perecedero=False, minimo_reposicion=50),
            Insumo(nombre="Yogur natural 150 g", categoria="Lácteos", unidad_medida="unidades", es_perecedero=True, minimo_reposicion=40),
            Insumo(nombre="Café en grano 1 kg", categoria="Café", unidad_medida="kg", es_perecedero=True, minimo_reposicion=3),
            Insumo(nombre="Queso crema", categoria="Lácteos", unidad_medida="kg", es_perecedero=True, minimo_reposicion=2),
        ]
        db.add_all(insumos)
        db.commit()
        for ins in insumos:
            db.refresh(ins)

        hoy = date.today()

        # 4. Lotes PEPS (cantidades disponibles y fechas de caducidad)
        lotes = [
            LoteInsumo(id_insumo=insumos[0].id_insumo, id_proveedor=prov.id_proveedor, cantidad_recibida=200, cantidad_disponible=180, costo_unitario=24.00, caducidad=hoy + timedelta(days=180), numero_factura="AB-001"),
            LoteInsumo(id_insumo=insumos[1].id_insumo, id_proveedor=prov.id_proveedor, cantidad_recibida=150, cantidad_disponible=110, costo_unitario=32.00, caducidad=hoy + timedelta(days=150), numero_factura="AB-002"),
            LoteInsumo(id_insumo=insumos[2].id_insumo, id_proveedor=prov.id_proveedor, cantidad_recibida=120, cantidad_disponible=100, costo_unitario=22.50, caducidad=hoy - timedelta(days=2), numero_factura="LA-001"),
            LoteInsumo(id_insumo=insumos[3].id_insumo, id_proveedor=prov.id_proveedor, cantidad_recibida=160, cantidad_disponible=150, costo_unitario=38.00, caducidad=hoy + timedelta(days=200), numero_factura="AB-003"),
            LoteInsumo(id_insumo=insumos[4].id_insumo, id_proveedor=prov.id_proveedor, cantidad_recibida=80, cantidad_disponible=60, costo_unitario=26.00, caducidad=hoy + timedelta(days=240), numero_factura="AB-004"),
            LoteInsumo(id_insumo=insumos[5].id_insumo, id_proveedor=prov.id_proveedor, cantidad_recibida=50, cantidad_disponible=24, costo_unitario=14.00, caducidad=hoy - timedelta(days=1), numero_factura="LA-002"),
            LoteInsumo(id_insumo=insumos[6].id_insumo, id_proveedor=prov.id_proveedor, cantidad_recibida=10, cantidad_disponible=1.5, costo_unitario=210.00, caducidad=hoy + timedelta(days=90), numero_factura="CA-281026"),
            LoteInsumo(id_insumo=insumos[7].id_insumo, id_proveedor=prov.id_proveedor, cantidad_recibida=5, cantidad_disponible=2.5, costo_unitario=65.00, caducidad=hoy + timedelta(days=4), numero_factura="QC-101126"),
        ]
        db.add_all(lotes)
        db.commit()
        for l in lotes:
            db.refresh(l)

        # 5. Productos de menú
        productos = [
            Producto(nombre="Latte Vainilla", categoria="Bebidas Calientes", precio_venta=65.00),
            Producto(nombre="Americano", categoria="Bebidas Calientes", precio_venta=45.00),
            Producto(nombre="Capuchino", categoria="Bebidas Calientes", precio_venta=55.00),
            Producto(nombre="Croissant Mantequilla", categoria="Panadería", precio_venta=40.00),
        ]
        db.add_all(productos)
        db.commit()

        # 6. Ventas del turno
        ventas = [
            Venta(id_usuario=admin.id_usuario, total=1850.00, forma_pago="Efectivo", monto_recibido=2000.00, cambio=150.00),
            Venta(id_usuario=admin.id_usuario, total=1620.00, forma_pago="Tarjeta", monto_recibido=1620.00, cambio=0.00),
            Venta(id_usuario=admin.id_usuario, total=1380.00, forma_pago="Efectivo", monto_recibido=1400.00, cambio=20.00),
        ]
        db.add_all(ventas)
        db.commit()

        # 7. Mermas del mes
        mermas = [
            Merma(id_insumo=insumos[2].id_insumo, id_lote=lotes[2].id_lote, id_usuario=admin.id_usuario, cantidad=8, motivo="Caducidad en refrigerador"),
            Merma(id_insumo=insumos[5].id_insumo, id_lote=lotes[5].id_lote, id_usuario=admin.id_usuario, cantidad=10, motivo="Empaque dañado / caducado"),
        ]
        db.add_all(mermas)
        db.commit()

        print("¡Base de datos la_esquina_del_cafe poblada con éxito!")
    finally:
        db.close()

if __name__ == "__main__":
    poblar_base()