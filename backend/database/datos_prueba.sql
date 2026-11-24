USE la_esquina_del_cafe;

-- 1. Proveedores
INSERT INTO proveedor (nombre, contacto_nombre, telefono, correo, direccion) VALUES
('Cafetalera de Veracruz S.A.', 'Carlos Mendoza', '5512345678', 'ventas@cafeveracruz.mx', 'Av. Reforma 120, CDMX'),
('Lácteos y Derivados del Centro', 'Laura Gómez', '5587654321', 'pedidos@lacteoscentro.mx', 'Calz. Tlalpan 450, CDMX'),
('Panadería Artesanal La Espiga', 'Roberto Díaz', '5544332211', 'contacto@laespiga.mx', 'Calle Madero 88, CDMX');

-- 2. Insumos (materias primas)
INSERT INTO insumo (nombre, categoria, unidad_medida, unidad_compra, factor_conversion, es_perecedero, minimo_reposicion, estado) VALUES
('Café en grano tostado', 'Café y Té', 'g', 'kg', 1000.0000, 0, 1000.00, 'Activo'),
('Leche entera', 'Lácteos', 'ml', 'L', 1000.0000, 1, 3000.00, 'Activo'),
('Leche deslactosada', 'Lácteos', 'ml', 'L', 1000.0000, 1, 2000.00, 'Activo'),
('Jarabe de vainilla', 'Endulzantes y Jarabes', 'ml', 'L', 1000.0000, 0, 500.00, 'Activo'),
('Chocolate en polvo', 'Insumos de Barra', 'g', 'kg', 1000.0000, 0, 600.00, 'Activo'),
('Vaso desechable 12 oz', 'Desechables', 'pza', 'paq', 50.0000, 0, 40.00, 'Activo'),
('Croissant de mantequilla', 'Alimentos', 'pza', 'caja', 12.0000, 1, 10.00, 'Activo'),
('Pastel de zanahoria (rebanada)', 'Alimentos', 'pza', 'charola', 8.0000, 1, 6.00, 'Activo');

-- 3. Lotes de inventario (incluye lotes vigentes, uno próximo a vencer y uno bajo mínimo para probar el semáforo)
INSERT INTO lote_insumo (id_insumo, id_proveedor, cantidad_recibida, cantidad_disponible, costo_unitario, caducidad, numero_factura, estado) VALUES
(1, 1, 5000.00, 4200.00, 0.32, DATE_ADD(CURDATE(), INTERVAL 60 DAY), 'FAC-1001', 'Disponible'),
(2, 2, 10000.00, 2500.00, 0.02, DATE_ADD(CURDATE(), INTERVAL 2 DAY),  'FAC-2001', 'Disponible'),
(2, 2, 12000.00, 12000.00, 0.02, DATE_ADD(CURDATE(), INTERVAL 12 DAY), 'FAC-2005', 'Disponible'),
(3, 2, 6000.00, 1500.00, 0.03, DATE_ADD(CURDATE(), INTERVAL 4 DAY),  'FAC-2008', 'Disponible'),
(4, 1, 2000.00, 1400.00, 0.15, DATE_ADD(CURDATE(), INTERVAL 90 DAY), 'FAC-1002', 'Disponible'),
(5, 1, 2000.00, 1100.00, 0.18, DATE_ADD(CURDATE(), INTERVAL 45 DAY), 'FAC-1003', 'Disponible'),
(6, 1, 200.00, 150.00, 1.80, NULL,                                   'FAC-1004', 'Disponible'),
(7, 3, 24.00, 16.00, 18.00, DATE_ADD(CURDATE(), INTERVAL 3 DAY),     'FAC-3001', 'Disponible'),
(8, 3, 16.00, 4.00, 25.00, DATE_ADD(CURDATE(), INTERVAL 2 DAY),      'FAC-3002', 'Disponible');

-- 4. Productos de venta (con las 3 categorías exactas de caja.html)
INSERT INTO producto (nombre, categoria, precio_venta, estado) VALUES
('Café Americano 12 oz', 'Bebidas calientes', 38.00, 'activo'),
('Capuchino Clásico', 'Bebidas calientes', 52.00, 'activo'),
('Latte Vainilla Caliente', 'Bebidas calientes', 58.00, 'activo'),
('Moka Caliente', 'Bebidas calientes', 60.00, 'activo'),
('Latte Frío', 'Bebidas frías', 60.00, 'activo'),
('Frappé Moka', 'Bebidas frías', 68.00, 'activo'),
('Croissant de Mantequilla', 'Alimentos', 42.00, 'activo'),
('Rebanada Pastel de Zanahoria', 'Alimentos', 55.00, 'activo');

-- 5. Recetas (explosión de insumos por cada producto vendido)
INSERT INTO receta (id_producto, id_insumo, cantidad_necesaria) VALUES
(1, 1, 18.0000), (1, 6, 1.0000),
(2, 1, 18.0000), (2, 2, 220.0000), (2, 6, 1.0000),
(3, 1, 18.0000), (3, 2, 220.0000), (3, 4, 25.0000), (3, 6, 1.0000),
(4, 1, 18.0000), (4, 2, 200.0000), (4, 5, 30.0000), (4, 6, 1.0000),
(5, 1, 18.0000), (5, 2, 250.0000), (5, 6, 1.0000),
(6, 1, 18.0000), (6, 2, 200.0000), (6, 5, 35.0000), (6, 6, 1.0000),
(7, 7, 1.0000),
(8, 8, 1.0000);

-- 6. Venta inicial de ejemplo para el resumen del día
INSERT INTO venta (id_usuario, total, forma_pago, monto_recibido, cambio, estado)
VALUES (1, 90.00, 'Efectivo', 100.00, 10.00, 'completada');

INSERT INTO detalle_venta (id_venta, id_producto, cantidad, precio_unitario, subtotal) VALUES
(1, 1, 1, 38.00, 38.00),
(1, 2, 1, 52.00, 52.00);