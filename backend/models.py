from sqlalchemy import Column, Integer, String, Boolean, DECIMAL, TIMESTAMP, Date, ForeignKey
from sqlalchemy.sql import func
from backend.database import Base

class Usuario(Base):
    __tablename__ = "usuario"
    id_usuario = Column(Integer, primary_key=True, autoincrement=True)
    nombre_usuario = Column(String(50), nullable=False, unique=True)
    correo = Column(String(50), nullable=False, unique=True)
    contrasena = Column(String(50), nullable=False)
    rol = Column(String(30), nullable=False)
    estado = Column(String(20), default="Activo")
    fecha_registro = Column(TIMESTAMP, server_default=func.now())

class Proveedor(Base):
    __tablename__ = "proveedor"
    id_proveedor = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(100), nullable=False)
    contacto_nombre = Column(String(100), nullable=True)
    telefono = Column(String(20), nullable=True)
    correo = Column(String(100), nullable=True)
    direccion = Column(String(255), nullable=True)

class Insumo(Base):
    __tablename__ = "insumo"
    id_insumo = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(100), nullable=False)
    categoria = Column(String(50), nullable=False)
    unidad_medida = Column(String(10), nullable=False)
    es_perecedero = Column(Boolean, nullable=False, default=True)
    minimo_reposicion = Column(DECIMAL(10, 2), nullable=False)
    estado = Column(String(20), default="Activo")

class LoteInsumo(Base):
    __tablename__ = "lote_insumo"
    id_lote = Column(Integer, primary_key=True, autoincrement=True)
    id_insumo = Column(Integer, ForeignKey("insumo.id_insumo"), nullable=False)
    id_proveedor = Column(Integer, ForeignKey("proveedor.id_proveedor"), nullable=True)
    cantidad_recibida = Column(DECIMAL(10, 2), nullable=False)
    cantidad_disponible = Column(DECIMAL(10, 2), nullable=False)
    costo_unitario = Column(DECIMAL(10, 2), nullable=False)
    fecha_entrada = Column(TIMESTAMP, server_default=func.now())
    caducidad = Column(Date, nullable=True)
    numero_factura = Column(String(50), nullable=True)

class Producto(Base):
    __tablename__ = "producto"
    id_producto = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(100), nullable=False)
    categoria = Column(String(50), nullable=False)
    precio_venta = Column(DECIMAL(10, 2), nullable=False)
    estado = Column(String(20), default="activo")

class Receta(Base):
    __tablename__ = "receta"
    id_receta = Column(Integer, primary_key=True, autoincrement=True)
    id_producto = Column(Integer, ForeignKey("producto.id_producto", ondelete="CASCADE"), nullable=False)
    id_insumo = Column(Integer, ForeignKey("insumo.id_insumo"), nullable=False)
    cantidad_necesaria = Column(DECIMAL(10, 4), nullable=False)

class Venta(Base):
    __tablename__ = "venta"
    id_venta = Column(Integer, primary_key=True, autoincrement=True)
    id_usuario = Column(Integer, ForeignKey("usuario.id_usuario"), nullable=False)
    total = Column(DECIMAL(10, 2), nullable=False)
    forma_pago = Column(String(30), nullable=False)
    monto_recibido = Column(DECIMAL(10, 2), nullable=False)
    cambio = Column(DECIMAL(10, 2), nullable=False)
    estado = Column(String(20), default="completada")
    fecha_emision_ticket = Column(TIMESTAMP, server_default=func.now())

class DetalleVenta(Base):
    __tablename__ = "detalle_venta"
    id_detalle = Column(Integer, primary_key=True, autoincrement=True)
    id_venta = Column(Integer, ForeignKey("venta.id_venta", ondelete="CASCADE"), nullable=False)
    id_producto = Column(Integer, ForeignKey("producto.id_producto"), nullable=False)
    cantidad = Column(Integer, nullable=False)
    precio_unitario = Column(DECIMAL(10, 2), nullable=False)
    subtotal = Column(DECIMAL(10, 2), nullable=False)

class MovimientoInventario(Base):
    __tablename__ = "movimiento_inventario"
    id_movimiento = Column(Integer, primary_key=True, autoincrement=True)
    id_insumo = Column(Integer, ForeignKey("insumo.id_insumo"), nullable=False)
    id_usuario = Column(Integer, ForeignKey("usuario.id_usuario"), nullable=False)
    tipo_movimiento = Column(String(30), nullable=False)
    cantidad = Column(DECIMAL(10, 2), nullable=False)
    motivo = Column(String(255), nullable=True)
    fecha_movimiento = Column(TIMESTAMP, server_default=func.now())

class Merma(Base):
    __tablename__ = "merma"
    id_merma = Column(Integer, primary_key=True, autoincrement=True)
    id_insumo = Column(Integer, ForeignKey("insumo.id_insumo"), nullable=False)
    id_lote = Column(Integer, ForeignKey("lote_insumo.id_lote"), nullable=True)
    id_usuario = Column(Integer, ForeignKey("usuario.id_usuario"), nullable=False)
    cantidad = Column(DECIMAL(10, 2), nullable=False)
    motivo = Column(String(255), nullable=False)
    fecha = Column(TIMESTAMP, server_default=func.now())

class CorteCaja(Base):
    __tablename__ = "corte_caja"
    id_corte = Column(Integer, primary_key=True, autoincrement=True)
    id_usuario = Column(Integer, ForeignKey("usuario.id_usuario"), nullable=False)
    efectivo_esperado = Column(DECIMAL(10, 2), nullable=False)
    efectivo_fisico = Column(DECIMAL(10, 2), nullable=False)
    diferencia = Column(DECIMAL(10, 2), nullable=False)
    estado = Column(String(20), default="cerrado")
    fecha_inicio = Column(TIMESTAMP, server_default=func.now())
    fecha_cierre = Column(TIMESTAMP, nullable=True)

class AlertaInventario(Base):
    __tablename__ = "alerta_inventario"
    id_alerta = Column(Integer, primary_key=True, autoincrement=True)
    id_insumo = Column(Integer, ForeignKey("insumo.id_insumo"), nullable=False)
    tipo_alerta = Column(String(50), nullable=False)
    mensaje = Column(String(255), nullable=False)
    leida = Column(Boolean, default=False)
    fecha_alerta = Column(TIMESTAMP, server_default=func.now())