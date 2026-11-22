from datetime import date, datetime, timedelta
from database import SessionLocal, engine, Base
from models import Usuario, Proveedor, Insumo, LoteInsumo, Producto, Receta, Venta, Merma, Bitacora

def poblar_base():
    Base.metadata.create_all(engine)   # crea las tablas si no existen
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
        # Convención del catálogo (RF 2): unidad_medida = unidad base (g, ml, pza);
        # unidad_compra + factor_conversion = cómo se compra (1 kg = 1000 g).
        # Las cantidades de lote y el mínimo van en unidad base; costo_unitario va
        # por unidad de compra (almacen.py calcula costo base = costo / factor).
        insumos = [
            Insumo(nombre="Arroz a granel", categoria="Abarrotes", unidad_medida="g", unidad_compra="kg", factor_conversion=1000, es_perecedero=False, minimo_reposicion=100000),
            Insumo(nombre="Frijol negro a granel", categoria="Abarrotes", unidad_medida="g", unidad_compra="kg", factor_conversion=1000, es_perecedero=False, minimo_reposicion=100000),
            Insumo(nombre="Leche entera 1 L", categoria="Lácteos", unidad_medida="pza", unidad_compra="pza", factor_conversion=1, es_perecedero=True, minimo_reposicion=100),
            Insumo(nombre="Aceite vegetal 1 L", categoria="Abarrotes", unidad_medida="pza", unidad_compra="pza", factor_conversion=1, es_perecedero=False, minimo_reposicion=100),
            Insumo(nombre="Azúcar a granel", categoria="Abarrotes", unidad_medida="g", unidad_compra="kg", factor_conversion=1000, es_perecedero=False, minimo_reposicion=50000),
            Insumo(nombre="Yogur natural 150 g", categoria="Lácteos", unidad_medida="pza", unidad_compra="pza", factor_conversion=1, es_perecedero=True, minimo_reposicion=40),
            Insumo(nombre="Café en grano 1 kg", categoria="Café", unidad_medida="g", unidad_compra="kg", factor_conversion=1000, es_perecedero=True, minimo_reposicion=3000),
            Insumo(nombre="Queso crema", categoria="Lácteos", unidad_medida="g", unidad_compra="kg", factor_conversion=1000, es_perecedero=True, minimo_reposicion=2000),
        ]
        db.add_all(insumos)
        db.commit()
        for ins in insumos:
            db.refresh(ins)

        hoy = date.today()

        # 4. Lotes PEPS (cantidades en unidad base; los vencidos quedan 'Caducado')
        lotes = [
            LoteInsumo(id_insumo=insumos[0].id_insumo, id_proveedor=prov.id_proveedor, cantidad_recibida=200000, cantidad_disponible=180000, costo_unitario=24.00, caducidad=hoy + timedelta(days=180), numero_factura="AB-001", estado="Disponible"),
            LoteInsumo(id_insumo=insumos[1].id_insumo, id_proveedor=prov.id_proveedor, cantidad_recibida=150000, cantidad_disponible=110000, costo_unitario=32.00, caducidad=hoy + timedelta(days=150), numero_factura="AB-002", estado="Disponible"),
            LoteInsumo(id_insumo=insumos[2].id_insumo, id_proveedor=prov.id_proveedor, cantidad_recibida=120, cantidad_disponible=100, costo_unitario=22.50, caducidad=hoy - timedelta(days=2), numero_factura="LA-001", estado="Caducado"),
            LoteInsumo(id_insumo=insumos[3].id_insumo, id_proveedor=prov.id_proveedor, cantidad_recibida=160, cantidad_disponible=150, costo_unitario=38.00, caducidad=hoy + timedelta(days=200), numero_factura="AB-003", estado="Disponible"),
            LoteInsumo(id_insumo=insumos[4].id_insumo, id_proveedor=prov.id_proveedor, cantidad_recibida=80000, cantidad_disponible=60000, costo_unitario=26.00, caducidad=hoy + timedelta(days=240), numero_factura="AB-004", estado="Disponible"),
            LoteInsumo(id_insumo=insumos[5].id_insumo, id_proveedor=prov.id_proveedor, cantidad_recibida=50, cantidad_disponible=24, costo_unitario=14.00, caducidad=hoy - timedelta(days=1), numero_factura="LA-002", estado="Caducado"),
            LoteInsumo(id_insumo=insumos[6].id_insumo, id_proveedor=prov.id_proveedor, cantidad_recibida=10000, cantidad_disponible=1500, costo_unitario=210.00, caducidad=hoy + timedelta(days=90), numero_factura="CA-281026", estado="Disponible"),
            LoteInsumo(id_insumo=insumos[7].id_insumo, id_proveedor=prov.id_proveedor, cantidad_recibida=5000, cantidad_disponible=2500, costo_unitario=65.00, caducidad=hoy + timedelta(days=4), numero_factura="QC-101126", estado="Disponible"),
        ]
        db.add_all(lotes)
        db.commit()
        for l in lotes:
            db.refresh(l)

        # 5. Insumos de cafetería, productos y recetas
        cafe    = Insumo(nombre="Café molido",        categoria="Café",      unidad_medida="g",   unidad_compra="kg",  factor_conversion=1000, es_perecedero=False, minimo_reposicion=1000)
        leche   = Insumo(nombre="Leche entera",       categoria="Lácteos",   unidad_medida="ml",  unidad_compra="L",   factor_conversion=1000, es_perecedero=True,  minimo_reposicion=3000)
        jarabe  = Insumo(nombre="Jarabe de vainilla", categoria="Abarrotes", unidad_medida="ml",  unidad_compra="L",   factor_conversion=1000, es_perecedero=False, minimo_reposicion=500)
        pan     = Insumo(nombre="Pan para panini",    categoria="Panadería", unidad_medida="pza", unidad_compra="paq", factor_conversion=10,   es_perecedero=True,  minimo_reposicion=10)
        queso   = Insumo(nombre="Queso para panini",  categoria="Lácteos",   unidad_medida="g",   unidad_compra="kg",  factor_conversion=1000, es_perecedero=True,  minimo_reposicion=500)
        pastel  = Insumo(nombre="Rebanada de pastel", categoria="Panadería", unidad_medida="pza", unidad_compra="pza", factor_conversion=1,    es_perecedero=True,  minimo_reposicion=5)
        db.add_all([cafe, leche, jarabe, pan, queso, pastel])
        db.commit()
        for i in (cafe, leche, jarabe, pan, queso, pastel):
            db.refresh(i)

        ahora = datetime.now()
        db.add_all([
            # costo_unitario por unidad de compra: $350/kg de café, $20/L de leche, etc.
            LoteInsumo(id_insumo=cafe.id_insumo,   id_proveedor=prov.id_proveedor, cantidad_recibida=5000, cantidad_disponible=5000, costo_unitario=350.00, caducidad=hoy + timedelta(days=120), numero_factura="CF-001", estado="Disponible"),
            # Dos lotes de leche para ver el PEPS: se gasta primero el que caduca antes
            LoteInsumo(id_insumo=leche.id_insumo,  id_proveedor=prov.id_proveedor, cantidad_recibida=6000, cantidad_disponible=2000, costo_unitario=20.00, fecha_entrada=ahora - timedelta(days=3), caducidad=hoy + timedelta(days=3),  numero_factura="LE-001", estado="Disponible"),
            LoteInsumo(id_insumo=leche.id_insumo,  id_proveedor=prov.id_proveedor, cantidad_recibida=8000, cantidad_disponible=8000, costo_unitario=20.00, fecha_entrada=ahora,                      caducidad=hoy + timedelta(days=10), numero_factura="LE-002", estado="Disponible"),
            LoteInsumo(id_insumo=jarabe.id_insumo, id_proveedor=prov.id_proveedor, cantidad_recibida=2000, cantidad_disponible=2000, costo_unitario=100.00, caducidad=hoy + timedelta(days=200), numero_factura="JV-001", estado="Disponible"),
            LoteInsumo(id_insumo=pan.id_insumo,    id_proveedor=prov.id_proveedor, cantidad_recibida=40,   cantidad_disponible=40,   costo_unitario=60.00,  caducidad=hoy + timedelta(days=5),   numero_factura="PN-001", estado="Disponible"),
            LoteInsumo(id_insumo=queso.id_insumo,  id_proveedor=prov.id_proveedor, cantidad_recibida=2000, cantidad_disponible=2000, costo_unitario=160.00, caducidad=hoy + timedelta(days=15),  numero_factura="QP-001", estado="Disponible"),
            # Pastel: lote ya agotado a propósito -> aparece "Sin stock" en Caja
            LoteInsumo(id_insumo=pastel.id_insumo, id_proveedor=prov.id_proveedor, cantidad_recibida=12,   cantidad_disponible=0,    costo_unitario=18.00,  caducidad=hoy + timedelta(days=2),   numero_factura="PS-001", estado="Agotado"),
        ])
        db.commit()

        americano = Producto(nombre="Café americano", categoria="Bebidas calientes", precio_venta=35.00)
        capuchino = Producto(nombre="Capuchino",      categoria="Bebidas calientes", precio_venta=45.00)
        latte     = Producto(nombre="Latte",          categoria="Bebidas calientes", precio_venta=50.00)
        frappe    = Producto(nombre="Frappé",         categoria="Bebidas frías",     precio_venta=60.00)
        panini    = Producto(nombre="Panini",         categoria="Alimentos",         precio_venta=55.00)
        pastel_p  = Producto(nombre="Pastel",         categoria="Alimentos",         precio_venta=40.00)
        productos = [americano, capuchino, latte, frappe, panini, pastel_p]
        db.add_all(productos)
        db.commit()
        for p in productos:
            db.refresh(p)

        # Recetas (cantidad por 1 unidad vendida, en unidad base)
        db.add_all([
            Receta(id_producto=americano.id_producto, id_insumo=cafe.id_insumo,   cantidad_necesaria=18),
            Receta(id_producto=capuchino.id_producto, id_insumo=cafe.id_insumo,   cantidad_necesaria=18),
            Receta(id_producto=capuchino.id_producto, id_insumo=leche.id_insumo,  cantidad_necesaria=150),
            Receta(id_producto=latte.id_producto,     id_insumo=cafe.id_insumo,   cantidad_necesaria=18),
            Receta(id_producto=latte.id_producto,     id_insumo=leche.id_insumo,  cantidad_necesaria=200),
            Receta(id_producto=frappe.id_producto,    id_insumo=cafe.id_insumo,   cantidad_necesaria=18),
            Receta(id_producto=frappe.id_producto,    id_insumo=leche.id_insumo,  cantidad_necesaria=150),
            Receta(id_producto=frappe.id_producto,    id_insumo=jarabe.id_insumo, cantidad_necesaria=30),
            Receta(id_producto=panini.id_producto,    id_insumo=pan.id_insumo,    cantidad_necesaria=1),
            Receta(id_producto=panini.id_producto,    id_insumo=queso.id_insumo,  cantidad_necesaria=50),
            Receta(id_producto=pastel_p.id_producto,  id_insumo=pastel.id_insumo, cantidad_necesaria=1),
        ])
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
            Merma(id_insumo=insumos[2].id_insumo, id_lote=lotes[2].id_lote, id_usuario=admin.id_usuario, autorizado_por=admin.id_usuario,
                  cantidad=8, costo_perdida=180.00, motivo="Caducidad", notas="Caducidad en refrigerador"),
            Merma(id_insumo=insumos[5].id_insumo, id_lote=lotes[5].id_lote, id_usuario=admin.id_usuario, autorizado_por=admin.id_usuario,
                  cantidad=10, costo_perdida=140.00, motivo="Daño en empaque", notas="Empaque dañado / caducado"),
        ]
        db.add_all(mermas)
        db.add(Bitacora(id_usuario=admin.id_usuario, accion="SISTEMA_INICIALIZADO", detalle="Carga de datos iniciales (seed.py)"))
        db.commit()

        print("¡Base de datos la_esquina_del_cafe poblada con éxito!")
    finally:
        db.close()

if __name__ == "__main__":
    poblar_base()