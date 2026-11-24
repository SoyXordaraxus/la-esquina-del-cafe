# La Esquina del Café: Sistema de Control de Inventarios para Cafeterías

Sistema web local para una cafetería que controla el inventario de insumos por lotes
(PEPS: primero en caducar / primero en entrar), registra ventas desde la caja
descontando automáticamente los insumos de cada receta, avisa de caducidades y
existencias bajas, y genera reportes, bitácora y respaldos de la base de datos.
Funciona sin internet: el servidor corre en la misma computadora de la cafetería y
se usa desde el navegador.

**Materia:** Ingeniería de Software, grupo 6CM15, ESIME Culhuacán, Instituto Politécnico Nacional.
**Equipo 2**

---

## Contenido

1. [Equipo y roles](#1-equipo-y-roles)
2. [Funcionalidades principales](#2-funcionalidades-principales)
3. [Tecnologías](#3-tecnologías)
4. [Requisitos previos](#4-requisitos-previos)
5. [Instalación en Windows](#5-instalación-en-windows)
6. [Instalación en Linux, macOS o GitHub Codespaces](#6-instalación-en-linux-macos-o-github-codespaces)
7. [Usuarios de prueba y recuperación de contraseña](#7-usuarios-de-prueba-y-recuperación-de-contraseña)
8. [Variables de entorno](#8-variables-de-entorno)
9. [Roles y permisos](#9-roles-y-permisos)
10. [Estructura del proyecto](#10-estructura-del-proyecto)
11. [Pruebas](#11-pruebas)
12. [Respaldos](#12-respaldos)
13. [Solución de problemas comunes](#13-solución-de-problemas-comunes)
14. [Flujo de trabajo con Git](#14-flujo-de-trabajo-con-git)

---

## 1. Equipo y roles

| Integrante | Rol |
|---|---|
| Alan Osvaldo Vázquez García | Gestor de Proyectos |
| Oscar Francisco Villeda Caracheo | Desarrollador |
| Nicolás Jiménez Fernando | Analista de Negocio |
| Marielle Estefanya Linares Morales | Diseñadora UX/UI |
| Andrés Mosso Gómez | Ingeniero de Pruebas / QA |

---

## 2. Funcionalidades principales

| Módulo (pantalla) | Qué hace | RF |
|---|---|---|
| Inicio de sesión (`login.html`) | Login con usuario o correo y contraseña; sesión con token firmado y menú según el rol. Recuperación de contraseña con código maestro. | RF 1, 1.1, 1.2 |
| Panel principal (`inicio.html`) | Ventas y tickets del día, alertas de caducidad y de existencias con botones que llevan a la acción (reabastecer, registrar merma, ver lote). | RF 6.1, 10 |
| Caja (`caja.html`) | Comanda y cobro en pocos clics (efectivo marcado por omisión). Muestra qué productos se pueden vender según el stock compartido entre recetas; el backend vuelve a validar el stock y descuenta los insumos por PEPS en una sola transacción. | RF 7, 7.1, 15, 16, 19 |
| Recepción (`recepcion.html`) | Entrada de lotes con proveedor, costo, caducidad (no puede ser pasada) y factura con formato `FAC-` + 3 a 8 dígitos. Convierte la unidad de compra a la unidad base (1 kg = 1000 g). | RF 2, 4, 4.1, 18 |
| Mermas (`mermas.html`) | Baja de insumos por motivo de catálogo. Si la pérdida supera $100.00 MXN y la registra un Cajero, se pide la contraseña del Administrador; el Cajero no ve el monto exacto. | RF 11, 11.1, 11.2, 14 |
| Inventario / Semáforo (`semaforo.html`) | Existencias por insumo contra su mínimo de reposición: verde (más de 120 %), amarillo (101–120 %), rojo (100 % o menos). Excluye lotes caducados o agotados. | RF 10, 10.1 |
| Caducidades (`caducidades.html`) | Lotes por vencer (alerta hasta 5 días antes). Los lotes vencidos pasan solos a "Caducado" y los que llegan a 0 a "Agotado". | RF 5, 6, 6.1 |
| Insumos (`insumos.html`) | Catálogo maestro: unidad base, unidad de compra, factor de conversión, mínimo de reposición. Editar, activar/desactivar y eliminar con confirmación. | RF 2, 14, 18 |
| Productos (`productos.html`) | Productos de venta con su receta (insumos y cantidades). Cambiar el precio no altera las ventas ya registradas. | RF 3, 14, 18 |
| Ventas (`ventas.html`) | Historial con detalle (precio cobrado e insumos descontados) y cancelación/devolución solo por el Administrador, con motivo de catálogo. | RF 3, 9, 18 |
| Reportes (`reportes.html`) | Reportes de ventas, consumo de insumos y mermas por periodo; exportación a PDF y CSV (para Excel), generados localmente. | RF 12, 20 |
| Usuarios (`usuarios.html`) | Alta y edición de usuarios (Administrador / Cajero), activar/desactivar; contraseñas alfanuméricas de al menos 8 caracteres. | RF 1, 1.1, 14 |
| Bitácora (`bitacora.html`) | Registro de solo lectura de inicios de sesión, cambios de catálogo, ventas, cancelaciones, mermas, respaldos, etc. | RF 13 |
| Respaldos (`respaldos.html`) | Respaldo `.sql` manual, diario a una hora programada y al cerrar el sistema; copia a unidad externa e histórico de 30 días. | RF 21 |

---

## 3. Tecnologías

**Backend** (Python, ver `requirements.txt`):

| Paquete | Para qué se usa |
|---|---|
| FastAPI | API REST y servidor de las páginas del frontend |
| Uvicorn | Servidor ASGI que ejecuta FastAPI |
| SQLAlchemy | ORM y conexión a la base de datos |
| PyMySQL + cryptography | Controlador de MySQL 8 (cryptography es necesario para la autenticación de MySQL 8) |
| python-jose[cryptography] | Tokens de sesión JWT (HS256) |
| tzdata | Zonas horarias (necesario en Windows para `America/Mexico_City`) |
| fpdf2 | Reportes en PDF |
| httpx | Lo usa el `TestClient` de FastAPI en las pruebas |

Las contraseñas se guardan con PBKDF2-SHA256 de la biblioteca estándar de Python (`hashlib`).

**Base de datos:** MySQL 8 (principal) o SQLite (plan B, incluido en Python).

**Frontend:** HTML, CSS y JavaScript sin frameworks ni CDNs (funciona sin internet). Los
iconos son SVG escritos en `menu.js`. FastAPI sirve el frontend en el mismo puerto que el API.

---

## 4. Requisitos previos

- **Python 3.12 o superior**: <https://www.python.org/downloads/>. En Windows, durante la
  instalación marca **"Add python.exe to PATH"**.
- **MySQL 8**: en Windows, con el instalador oficial (MySQL Installer, opción "Server only"
  o "Developer Default"). Anota la contraseña de `root` que elijas.
  Si no puedes instalar MySQL, el sistema también corre con SQLite (ver `iniciar.bat sqlite`).
- **Git** (solo si vas a clonar el repositorio; si recibiste el `.zip` no hace falta):
  <https://git-scm.com/downloads>.
- **Docker** (opcional): solo para `./iniciar.sh mysql` en Linux, macOS o Codespaces, que
  levanta MySQL en un contenedor.

---

## 5. Instalación en Windows

Todo se hace en una terminal (`cmd` o PowerShell) dentro de la carpeta donde quieras el proyecto.

**1. Obtener el proyecto**

*Opción A: recibiste el proyecto en un `.zip` (por ejemplo, en USB).* No necesitas Git.
Clic derecho al `.zip` → **Extraer todo**, entra a la carpeta extraída (la que contiene
`iniciar.bat`) y abre ahí una terminal: en el Explorador escribe `cmd` en la barra de
direcciones y presiona Enter.

*Opción B: tienes acceso al repositorio en GitHub.*

```bat
git clone https://github.com/SoyXordaraxus/la-esquina-del-cafe.git
cd la-esquina-del-cafe
```


**2. Crear el entorno virtual e instalar dependencias**

```bat
python -m venv venv
venv\Scripts\python -m pip install -r requirements.txt
```

No hace falta "activar" el entorno: `iniciar.bat` usa `venv\Scripts\python` automáticamente.

**3. Configurar el archivo `.env`**

```bat
copy .env.ejemplo .env
notepad .env
```

Cambia como mínimo `DATABASE_URL` con tu usuario y contraseña de MySQL, por ejemplo:

```
DATABASE_URL=mysql+pymysql://root:MiClaveDeMySQL@127.0.0.1:3306/la_esquina_del_cafe
```

La base `la_esquina_del_cafe` **se crea sola** la primera vez (con `root` hay permiso para
crearla) y se llena con los datos iniciales de `backend/seed.py`. Escribe los valores sin
espacios alrededor del `=` y sin comillas.

> **Equipo de pruebas:** el archivo `.env` no viene en el `.zip`; créalo con los comandos de
> arriba. En `DATABASE_URL` pon la contraseña de `root` de **tu** MySQL. Si prefieres no
> cambiarla, la contraseña que usó el equipo en sus pruebas es `sixseven`; en ese caso
> la línea queda así:
>
> ```
> DATABASE_URL=mysql+pymysql://root:sixseven@127.0.0.1:3306/la_esquina_del_cafe
> ```

**4. Arrancar**

Doble clic en **`iniciar.bat`**, o desde la terminal:

| Comando | Qué hace |
|---|---|
| `iniciar.bat` | Modo normal: MySQL local según `DATABASE_URL` de `.env`. |
| `iniciar.bat reset` | Borra la base MySQL, la vuelve a poblar y arranca (pide escribir `SI` para confirmar). |
| `iniciar.bat sqlite` | Plan B sin MySQL: usa `backend\esquina.db` (la crea si no existe). |
| `iniciar.bat sqlite reset` | Borra `backend\esquina.db`, la vuelve a poblar y arranca. |

`iniciar.bat` revisa que estén las dependencias, que MySQL responda, que el puerto esté libre
y que la base tenga datos; luego arranca el servidor en el puerto 8000 y abre el navegador en
<http://127.0.0.1:8000/login.html>. Si algo falla, muestra el motivo en español y espera una
tecla antes de cerrar la ventana.

Para apagar el sistema presiona **Ctrl+C** en la ventana negra (así se genera el respaldo
"al cerrar"; si cierras la ventana con la X, ese respaldo no se hace).

La documentación interactiva del API queda en <http://127.0.0.1:8000/docs>.

---

## 6. Instalación en Linux, macOS o GitHub Codespaces

Si recibiste el `.zip`, descomprímelo (`unzip la-esquina-del-cafe-main.zip`), entra a la
carpeta y empieza desde `python3 -m venv venv`. Si vas a clonar:

```bash
git clone https://github.com/SoyXordaraxus/la-esquina-del-cafe.git
cd la-esquina-del-cafe
python3 -m venv venv
venv/bin/python -m pip install -r requirements.txt
./iniciar.sh
```

En Codespaces Python ya viene instalado; puedes saltarte el `venv` e instalar con
`python3 -m pip install -r requirements.txt`.

`iniciar.sh` tiene cuatro modos:

| Comando | Qué hace |
|---|---|
| `./iniciar.sh` | SQLite en `backend/esquina.db`; la crea y la puebla si no existe. |
| `./iniciar.sh reset` | SQLite: borra la base, la vuelve a poblar y arranca. |
| `./iniciar.sh mysql` | MySQL 8 en Docker (contenedor `mysql-cafe`, base `la_esquina_del_cafe`, usuario `cafe` / `cafe1234`); lo crea o lo enciende si hace falta y puebla la base si está vacía. |
| `./iniciar.sh mysql reset` | MySQL en Docker: borra la base, la vuelve a poblar y arranca. |

El servidor queda en el puerto 8000 (cámbialo con `PUERTO=8001 ./iniciar.sh`) con recarga
automática al guardar cambios (`--reload`). En Codespaces el script imprime la dirección del
puerto reenviado. Ctrl+C apaga el servidor (el contenedor de MySQL se queda encendido).

`iniciar.sh` define `DATABASE_URL` por su cuenta y **no lee `.env`**. Para las demás
variables, expórtalas antes de correrlo:

```bash
export HORA_RESPALDO=22:00
export RUTA_RESPALDO_EXTERNO=/media/usb/respaldos
./iniciar.sh mysql
```

En Windows con Git Bash, `iniciar.sh` también detecta `venv\Scripts\python`.

---

## 7. Usuarios de prueba y recuperación de contraseña

`seed.py` crea estos usuarios (se puede entrar con el **correo** o con el **nombre de usuario**):

| Rol | Correo | Nombre de usuario | Contraseña |
|---|---|---|---|
| Administrador | `admin@esquinadelcafe.mx` | `Andres Mosso` | `admin123` |
| Cajero | `osvaldo@esquinadelcafe.mx` | `Osvaldo Vazquez` | `cajero123` |

No existe un usuario llamado `admin`: usa el correo.

**Recuperar contraseña:** en el login, "¿Olvidaste tu contraseña?" pide el usuario o correo,
el **código maestro** del establecimiento y la nueva contraseña (alfanumérica, mínimo 8
caracteres). El código maestro es el valor de `CODIGO_MAESTRO` (por omisión
`CAFE-MAESTRO-2026`); cámbialo en `.env` para uso real. Queda registrado en la bitácora.
No se puede recuperar la contraseña de una cuenta desactivada.

---

## 8. Variables de entorno

En Windows se escriben en `.env` (ver `.env.ejemplo`); en Linux/macOS se exportan en la terminal.

| Variable | Para qué sirve | Por omisión | Ejemplo |
|---|---|---|---|
| `DATABASE_URL` | Conexión a la base de datos. Obligatoria (los scripts de arranque la definen en modo SQLite y en `iniciar.sh mysql`). | — | `mysql+pymysql://root:clave@127.0.0.1:3306/la_esquina_del_cafe` · `sqlite:///./esquina.db` |
| `SECRET_KEY` | Clave para firmar los tokens de sesión. Sin ella se usa una clave de desarrollo y aparece un aviso. | clave de desarrollo | `un-texto-largo-y-secreto` |
| `CODIGO_MAESTRO` | Código para recuperar contraseñas desde el login. | `CAFE-MAESTRO-2026` | `MiCafe-2027` |
| `TZ_NEGOCIO` | Zona horaria del negocio: define "hoy", los filtros por día y las horas mostradas. En la base todo se guarda en UTC. | `America/Mexico_City` | `America/Monterrey` |
| `SESION_HORAS` | Horas que dura una sesión antes de pedir login otra vez. | `12` | `8` |
| `HORA_RESPALDO` | Hora del respaldo diario (`HH:MM`, hora del negocio). Si el equipo está apagado a esa hora, el respaldo se hace al arrancar. Un valor inválido usa 23:00. | `23:00` | `22:30` |
| `RUTA_RESPALDO_EXTERNO` | Carpeta de la unidad externa donde se copia cada respaldo, con retención de 30 días. **La carpeta debe existir**: no se crea sola, para no escribir en el disco interno cuando la USB no está conectada. Si no está definida o no está disponible, el respaldo queda solo en local y se registra un aviso. | sin definir | `E:\RespaldosCafe` · `/media/usb/respaldos` |
| `PUERTO` | Puerto del servidor (`iniciar.bat` e `iniciar.sh`). | `8000` | `8001` |
| `HOST` | Interfaz donde escucha el servidor (solo `iniciar.bat`; `iniciar.sh` usa `0.0.0.0`). Con `0.0.0.0` se puede entrar desde otros equipos de la red. | `127.0.0.1` | `0.0.0.0` |

---

## 9. Roles y permisos

Los permisos se validan en el backend con el token de la sesión (no basta con ocultar el
menú): un Cajero que llame a una ruta de Administrador recibe 403.

| Pantalla | Administrador | Cajero |
|---|:---:|:---:|
| Inicio (panel con métricas y alertas) | Sí | No |
| Caja (cobrar) | Sí | Sí (pantalla inicial del Cajero) |
| Recepción de lotes | Sí | Sí |
| Mermas | Sí, ve el monto | Sí; si la pérdida supera $100 necesita la contraseña del Administrador y no ve el monto exacto |
| Inventario (semáforo) | Sí | No |
| Caducidades | Sí | No |
| Insumos y Productos (catálogos) | Sí | No |
| Ventas (historial, detalle, cancelación) | Sí | No |
| Reportes PDF/CSV | Sí | No |
| Usuarios | Sí | No |
| Bitácora | Sí | No |
| Respaldos | Sí | No |

---

## 10. Estructura del proyecto

```
la-esquina-del-cafe/
├── iniciar.bat              Arranque en Windows (MySQL local o SQLite), lee .env
├── iniciar.sh               Arranque en Linux/macOS/Codespaces (SQLite o MySQL en Docker)
├── requirements.txt         Dependencias de Python
├── .env.ejemplo             Plantilla de configuración (copiar como .env)
├── backend/
│   ├── main.py              App FastAPI: rutas, frontend estático, respaldo diario y al cerrar
│   ├── database.py          Conexión SQLAlchemy (DATABASE_URL); MySQL en UTC
│   ├── models.py            Modelos de las 14 tablas
│   ├── seed.py              Crea las tablas y carga los datos iniciales
│   ├── preparar.py          Ayudante de iniciar.bat: dependencias, base de datos, puerto, navegador
│   ├── database/
│   │   └── estructura.sql   Script SQL de referencia del esquema (MySQL)
│   ├── routes/
│   │   ├── auth_tableros.py Login, recuperación, panel principal y semáforo
│   │   ├── ventas.py        Caja: productos disponibles, cobro, historial y cancelación
│   │   ├── almacen.py       Recepción de lotes, caducidades y mermas
│   │   ├── catalogos.py     Insumos y productos con recetas
│   │   └── reportes_admin.py Reportes, usuarios, bitácora y respaldos
│   ├── services/
│   │   ├── sesion.py        Tokens JWT y control de acceso por rol
│   │   ├── contrasenas.py   Hash PBKDF2 y política de contraseñas
│   │   ├── venta_service.py Cobro en una transacción, descuento PEPS, cancelaciones
│   │   ├── reportes_export.py Generación de PDF y CSV
│   │   ├── respaldos.py     Respaldos .sql, programador diario, unidad externa, retención
│   │   ├── bitacora.py      Registro en la bitácora
│   │   └── tiempo.py        Zona horaria del negocio (único lugar donde se define)
│   ├── pruebas/             Pruebas automáticas (ver sección 11)
│   └── backups/             Respaldos .sql generados (no se sube a Git)
└── frontend/
    ├── login.html, inicio.html, caja.html, ...   Una página por pantalla
    ├── css/estilos.css      Estilos de todo el sistema
    └── js/
        ├── config.js        Dirección del API, sesión y token en cada petición (cargar primero)
        ├── menu.js          Barra superior, menú lateral por rol y modales
        └── <pantalla>.js    Lógica de cada pantalla
```

---

## 11. Pruebas

Las pruebas son scripts que se corren **desde la carpeta `backend/`**. Cada una crea una base
SQLite temporal, así que no tocan tus datos. Terminan con código 0 si todo pasa; cada
comprobación se imprime como `OK` o `FALLA`.

| Archivo | Qué prueba |
|---|---|
| `prueba_caja_stock_factura.py` | Límite de la comanda según el stock compartido entre recetas (RF 7, 7.1) y factura `FAC-####` en Recepción (RF 18). |
| `prueba_catalogos_estado.py` | Editar, desactivar/activar y eliminar insumos y productos. |
| `prueba_errores_sesion.py` | Mensajes de error y cierre de sesión. |
| `prueba_panel_acciones.py` | Botones de acciones del panel principal y badges. |
| `prueba_reportes.py` | Reportes PDF y CSV de ventas, consumo y mermas (RF 12). |
| `prueba_respaldos.py` | Respaldo diario programado, recuperación al arrancar, sin duplicados, unidad externa, retención de 30 días, folio y endpoint de estado (RF 21). |
| `prueba_zona_horaria.py` | Una venta a las 23:30 hora de México cuenta en ese día aunque en UTC ya sea el siguiente. |

Windows:

```bat
cd backend
..\venv\Scripts\python pruebas\prueba_reportes.py
for %f in (pruebas\prueba_*.py) do ..\venv\Scripts\python %f
```

Linux/macOS:

```bash
cd backend
python3 pruebas/prueba_reportes.py
for f in pruebas/prueba_*.py; do python3 "$f" || echo "FALLÓ: $f"; done
```

Para correrlas contra MySQL, define `DATABASE_URL` apuntando a una base **vacía** creada solo
para pruebas (nunca a la base real).

---

## 12. Respaldos

**Dónde se guardan:** `backend/backups/` con nombres como
`respaldo_diario_20261122_230000.sql` (tipo, fecha y hora del negocio). Si
`RUTA_RESPALDO_EXTERNO` apunta a una carpeta existente, cada respaldo también se copia ahí.
En ambas carpetas se borran solos los respaldos de más de 30 días.

**Cuándo se generan:**

- **Diario**, a la hora `HORA_RESPALDO` (23:00 por omisión). Si la computadora estaba apagada a
  esa hora, se hace al arrancar el sistema. Nunca se genera más de uno por día.
- **Al cerrar el sistema** (Ctrl+C en la ventana del servidor).
- **Manual**, con el botón "Respaldar base de datos ahora" en la pantalla Respaldos.

La pantalla Respaldos muestra la hora programada, el próximo respaldo, el último diario, el
estado de la unidad externa y el historial con folio fijo (`BKP-20261122-230000-D`), tipo,
ubicación y descarga del `.sql`.

**Restaurar un respaldo en MySQL.** El archivo trae la estructura (`DROP TABLE` + `CREATE TABLE`)
y los datos de las 14 tablas, pero no crea la base. Primero apaga el sistema (Ctrl+C), luego:

```bat
:: 1. Crear la base si no existe (si existe, sus tablas se reemplazan)
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS la_esquina_del_cafe CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"

:: 2. Cargar el respaldo (en cmd; en PowerShell usa: cmd /c "mysql -u root -p la_esquina_del_cafe < archivo.sql")
mysql -u root -p la_esquina_del_cafe < backend\backups\respaldo_diario_20261122_230000.sql
```

Si `mysql` no se reconoce como comando, usa la ruta completa
(`"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe"`) o, en MySQL Workbench,
**Server > Data Import > Import from Self-Contained File**, elige el `.sql` y la base
`la_esquina_del_cafe` como destino. Con el MySQL de Docker:
`docker exec -i mysql-cafe mysql -uroot -pcafe1234 la_esquina_del_cafe < archivo.sql`.

Los respaldos hechos con SQLite usan otra sintaxis: se restauran en un archivo SQLite nuevo
(`sqlite3 esquina.db < archivo.sql`), no en MySQL.

---

## 13. Solución de problemas comunes

**"Address already in use" / "El puerto 8000 ya está en uso"**
Ya hay otro servidor abierto (otra ventana de `iniciar.bat`/`iniciar.sh`). Ciérralo con Ctrl+C
o usa otro puerto (`PUERTO=8001` en `.env`, o `PUERTO=8001 ./iniciar.sh`). Para ver qué programa
lo ocupa: `netstat -ano | findstr :8000` (Windows) o `lsof -i :8000` (Linux/macOS).

**"No se reconoce `iniciar.bat`" o "No such file" al arrancar desde el `.zip`**
Revisa que la terminal esté en la carpeta que contiene `iniciar.bat`. Al extraer, Windows a
veces crea una carpeta dentro de otra (`la-esquina-del-cafe-main\la-esquina-del-cafe-main`);
entra a la de adentro.

**"Python was not found" o "python no se reconoce como comando"**
Python no está en el PATH. Usa `py` en lugar de `python` (`py -m venv venv`), o reinstala
Python marcando **"Add python.exe to PATH"**. En PowerShell, si usas la ruta completa de
Python, ponle `&` adelante: `& "C:\ruta\a\python.exe" -m venv venv`. Corre los comandos
siempre **dentro de la carpeta del proyecto** (la que contiene `requirements.txt`); si no,
aparece "Could not open requirements file".

**"MySQL no responde"**
- Windows: abre *Servicios*, busca `MySQL80` y dale *Iniciar* (o `net start MySQL80` en una
  terminal de administrador).
- Revisa host, puerto, usuario y contraseña de `DATABASE_URL` en `.env`. Si el mensaje dice
  "usuario o contraseña incorrectos", la contraseña no coincide con la de MySQL. Si tu
  contraseña tiene `@`, `:`, `/`, `#` o `%`, escríbela codificada (`@` = `%40`, etc.).
- Con Docker: `docker start mysql-cafe` y `docker logs mysql-cafe`.
- Mientras tanto puedes trabajar con `iniciar.bat sqlite` o `./iniciar.sh`.

**Falta una dependencia (`ModuleNotFoundError: No module named ...`)**
Instala las dependencias con el mismo Python que arranca el sistema:
`venv\Scripts\python -m pip install -r requirements.txt` (Windows) o
`venv/bin/python -m pip install -r requirements.txt` (Linux/macOS). `iniciar.bat` te dice el
comando exacto.

**"Usuario o contraseña incorrectos" con el usuario "admin"**
No existe un usuario `admin`. Entra con `admin@esquinadelcafe.mx` / `admin123` (o el nombre
`Andres Mosso`). Si la base está vacía o ya cambiaron la contraseña, usa "¿Olvidaste tu
contraseña?" con el código maestro, o repuebla la base con `iniciar.bat reset` (borra los datos).

**El navegador muestra la versión vieja de una pantalla**
Recarga sin caché con **Ctrl+Shift+R** (Cmd+Shift+R en Mac). Las páginas `.html` no se guardan
en caché, pero los `.js` y `.css` sí.

**"Unidad externa no disponible" en Respaldos**
La carpeta de `RUTA_RESPALDO_EXTERNO` no existe o la USB no está conectada (o cambió de letra,
por ejemplo de `E:` a `F:`). Conecta la unidad y crea la carpeta (`mkdir E:\RespaldosCafe`).
Mientras tanto los respaldos se siguen guardando en `backend/backups/`. Después de cambiar
`.env`, reinicia el sistema.

---

## 14. Flujo de trabajo con Git

1. Actualiza `main` y crea una rama para cada cambio, con un nombre que lo describa:

   ```bash
   git checkout main
   git pull
   git checkout -b fix-caja-stock      # ej.: rf21-respaldos, mejora-reportes-pdf
   ```

2. Haz commits pequeños con mensajes en español que digan qué cambió y por qué.
3. Antes de subir, corre las pruebas de `backend/pruebas/`.
4. Sube la rama y abre un Pull Request hacia `main` en GitHub:

   ```bash
   git push -u origin fix-caja-stock
   ```

5. Otro integrante revisa el PR; cuando esté aprobado se hace merge a `main`. Nadie sube
   cambios directamente a `main`.

**No subir a Git** (ya están en `.gitignore`):

- `.env`: tiene contraseñas y claves. Sube solo `.env.ejemplo`.
- `venv/`, `__pycache__/`, `*.pyc`.
- Bases de datos `*.db` (SQLite).
- `backend/backups/`: los respaldos contienen todos los datos del negocio.
- `.vscode/` y otras configuraciones personales del editor.
