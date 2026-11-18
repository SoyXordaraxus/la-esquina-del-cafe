CREATE DATABASE IF NOT EXISTS la_esquina_del_cafe CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE la_esquina_del_cafe;
SHOW DATABASES;
SHOW TABLES;

CREATE TABLE usuario (
    id_usuario INT AUTO_INCREMENT PRIMARY KEY,
    nombre_usuario VARCHAR(50) NOT NULL UNIQUE,
    correo VARCHAR(50) NOT NULL UNIQUE,
    contrasena VARCHAR(50) NOT NULL, 
    rol VARCHAR(30) NOT NULL, 
    estado VARCHAR(20) DEFAULT 'Activo',
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE proveedor (
    id_proveedor INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    contacto_nombre VARCHAR(100) NULL,
    telefono VARCHAR(20) NULL,
    correo VARCHAR(100) NULL,
    direccion VARCHAR(255) NULL
) ENGINE=InnoDB;

CREATE TABLE insumo (
    id_insumo INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    categoria VARCHAR(50) NOT NULL,
    unidad_medida VARCHAR(10) NOT NULL, 
    es_perecedero BOOLEAN NOT NULL DEFAULT 1, -- 1 si caduca, 0 si no
    minimo_reposicion DECIMAL(10,2) NOT NULL, 
    estado VARCHAR(20) DEFAULT 'Activo'
) ENGINE=InnoDB;

CREATE TABLE lote_insumo (
    id_lote INT AUTO_INCREMENT PRIMARY KEY,
    id_insumo INT NOT NULL,
    id_proveedor INT NULL, 
    cantidad_recibida DECIMAL(10,2) NOT NULL,
    cantidad_disponible DECIMAL(10,2) NOT NULL,
    costo_unitario DECIMAL(10,2) NOT NULL,
    fecha_entrada TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    caducidad DATE NULL, 
    numero_factura VARCHAR(50) NULL,
    CONSTRAINT fk_lote_insumo FOREIGN KEY (id_insumo) REFERENCES insumo(id_insumo),
    CONSTRAINT fk_lote_proveedor FOREIGN KEY (id_proveedor) REFERENCES proveedor(id_proveedor)
) ENGINE=InnoDB;

CREATE TABLE producto (
    id_producto INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    categoria VARCHAR(50) NOT NULL,
    precio_venta DECIMAL(10,2) NOT NULL,
    estado VARCHAR(20) DEFAULT 'activo'
) ENGINE=InnoDB;

CREATE TABLE receta (
    id_receta INT AUTO_INCREMENT PRIMARY KEY,
    id_producto INT NOT NULL,
    id_insumo INT NOT NULL,
    cantidad_necesaria DECIMAL(10,4) NOT NULL, 
    CONSTRAINT fk_receta_producto FOREIGN KEY (id_producto) REFERENCES producto(id_producto) ON DELETE CASCADE,
    CONSTRAINT fk_receta_insumo FOREIGN KEY (id_insumo) REFERENCES insumo(id_insumo)
) ENGINE=InnoDB;

CREATE TABLE venta (
    id_venta INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT NOT NULL, 
    total DECIMAL(10,2) NOT NULL,
    forma_pago VARCHAR(30) NOT NULL, 
    monto_recibido DECIMAL(10,2) NOT NULL,
    cambio DECIMAL(10,2) NOT NULL,
    estado VARCHAR(20) DEFAULT 'completada', 
    fecha_emision_ticket TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_venta_usuario FOREIGN KEY (id_usuario) REFERENCES usuario(id_usuario)
) ENGINE=InnoDB;

CREATE TABLE detalle_venta (
    id_detalle INT AUTO_INCREMENT PRIMARY KEY,
    id_venta INT NOT NULL,
    id_producto INT NOT NULL,
    cantidad INT NOT NULL,
    precio_unitario DECIMAL(10,2) NOT NULL,
    subtotal DECIMAL(10,2) NOT NULL,
    CONSTRAINT fk_detalle_venta FOREIGN KEY (id_venta) REFERENCES venta(id_venta) ON DELETE CASCADE,
    CONSTRAINT fk_detalle_producto FOREIGN KEY (id_producto) REFERENCES producto(id_producto)
) ENGINE=InnoDB;

CREATE TABLE movimiento_inventario (
    id_movimiento INT AUTO_INCREMENT PRIMARY KEY,
    id_insumo INT NOT NULL,
    id_usuario INT NOT NULL,
    tipo_movimiento VARCHAR(30) NOT NULL,
    cantidad DECIMAL(10,2) NOT NULL,
    motivo VARCHAR(255) NULL,
    fecha_movimiento TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_mov_insumo FOREIGN KEY (id_insumo) REFERENCES insumo(id_insumo),
    CONSTRAINT fk_mov_usuario FOREIGN KEY (id_usuario) REFERENCES usuario(id_usuario)
) ENGINE=InnoDB;

CREATE TABLE merma (
    id_merma INT AUTO_INCREMENT PRIMARY KEY,
    id_insumo INT NOT NULL,
    id_lote INT NULL, 
    id_usuario INT NOT NULL, 
    cantidad DECIMAL(10,2) NOT NULL,
    motivo VARCHAR(255) NOT NULL, 
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_merma_insumo FOREIGN KEY (id_insumo) REFERENCES insumo(id_insumo),
    CONSTRAINT fk_merma_lote FOREIGN KEY (id_lote) REFERENCES lote_insumo(id_lote),
    CONSTRAINT fk_merma_usuario FOREIGN KEY (id_usuario) REFERENCES usuario(id_usuario)
) ENGINE=InnoDB;

CREATE TABLE corte_caja (
    id_corte INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT NOT NULL, 
    efectivo_esperado DECIMAL(10,2) NOT NULL,
    efectivo_fisico DECIMAL(10,2) NOT NULL,
    diferencia DECIMAL(10,2) NOT NULL, 
    estado VARCHAR(20) DEFAULT 'cerrado', 
    fecha_inicio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_cierre TIMESTAMP NULL,
    CONSTRAINT fk_corte_usuario FOREIGN KEY (id_usuario) REFERENCES usuario(id_usuario)
) ENGINE=InnoDB;

CREATE TABLE alerta_inventario (
    id_alerta INT AUTO_INCREMENT PRIMARY KEY,
    id_insumo INT NOT NULL,
    tipo_alerta VARCHAR(50) NOT NULL, 
    mensaje VARCHAR(255) NOT NULL,
    leida BOOLEAN DEFAULT 0, -- 0 = No leída, 1 = Leída
    fecha_alerta TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_alerta_insumo FOREIGN KEY (id_insumo) REFERENCES insumo(id_insumo)
) ENGINE=InnoDB;