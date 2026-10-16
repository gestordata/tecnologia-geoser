# GeoSer Tecnología — Inventario TI

Aplicación independiente de inventario tecnológico de Grupo GeoSer. **No es** el repositorio `inventario-geoser` (Semáforo Comercial).

## Estado / handoff (16 octubre 2026)
- Ubuntu host autorizado: `/opt/geoser/tecnologia-geoser`, proceso Python `server.py`, puerto 3014, acceso LAN `http://192.168.0.181:3014`.
- Interfaz HTML/CSS/JS sin framework de compilación en `public/index.html`. API HTTP en `server.py` y consultas relacionales en `profiles.py`.
- SQLite en `data/tecnologia.db` **NO versionada**: contiene información personal/confidencial. No almacenar datos reales, backups, actas ni fotos en Git.
- Tabla `people`, `equipment`, `movements`, `evidence`, `source_records`, `asset_assignments`, `identity_review`.
- Origen de información: ACTA ENTREGA M.xlsm; Base de datos 6_10_2026.xlsx; Equipos ALLCOM (version 1).xlsb; Nomenclatura_Computadores_GEOSER.xlsx.
- Nomenclatura oficial = **primera columna de EQUIPOS GEOSER**, p. ej. `PGS-PC-023`. Guardada en `equipment.device_name`. No confundir con serial `equipment.serial` ni placa provisional `equipment.asset_tag`.
- En octubre 2026: ~314 equipos, 95 nombres oficiales, 210 personas, 517 fuentes, 68 asignaciones históricas/relacionadas, 146 referencias de persona por conciliar. Confirmar cifras consultando DB actual.
- El usuario quiere **abrir ficha/hoja de vida dentro del listado** al hacer clic sobre equipo o colaborador. No hacer módulo separado. El botón Editar debe permanecer independiente.
- Ficha equipo: foto, nomenclatura oficial, placa, serial, tipo, marca/modelo, SO, Bitdefender, renting, ubicación, asignado actual, características, historial, actas, fuentes.
- Ficha colaborador: foto, identificación, correo/cargo/centro de costos, equipos actuales e históricos, actas y evidencias.
- Integración con ventas es **futura**, no implementarla sin solicitud. Se reservaron `external_sales_key`.
- DNS se dejó pendiente. Seguridad pendiente: implementar SSO corporativo (Entra ID), roles y controles de acceso ANTES de publicar a Internet.

## Arranque local (solo entorno aislado)
Requiere Python 3.14+ o compatible con SQLite.
```bash
python3 server.py
```
Por defecto escucha en 0.0.0.0:3014; configurables `HOST` y `PORT`. Se inicializa esquema SQLite automáticamente; los datos de producción NO se incluyen. Para otro equipo se debe migrar la base por un canal seguro, fuera de Git, si hay autorización.

## Rutas principales
- `/` — Inventario, dashboard, equipos, colaboradores, movimientos, actas.
- `/api/health`, `/api/dashboard`, `/api/equipment`, `/api/people`, `/api/movements`
- `/api/profiles/summary`, `/api/profiles/equipment`, `/api/profiles/people`
- `/api/profiles/equipment/:id`, `/api/profiles/people/:id` (detalle con asignaciones, actas, fuentes)
- POST `/api/profiles/{equipment|people}/:id/photo` (imagen base64 <= 3 MB)
- `/hojas-de-vida.html` es una vista heredada separada; no promover como módulo. La UX principal está integrada mediante `openProfileDetail` en index.html.

## Instrucciones para Claude
1. Leer `CLAUDE.md` y `docs/ARCHITECTURE.md`.
2. No cambiar nomenclaturas oficiales, no confundir hostname/serial/placa.
3. No asociar equipos por mera coincidencia de nombres: requieren validación documental/serial; referencias dudosas van a `identity_review`.
4. Hacer backup SQLite antes de toda migración. No ejecutar migraciones destructivas sin inspección previa.
5. Mantener historial y trazabilidad. No actualizar automáticamente responsable actual desde fuentes históricas sin verificación.
6. Probar `python3 -m py_compile server.py profiles.py`, comprobar JS con `node --check` extrayendo scripts y comprobar endpoints.
7. Seguridad: app actual NO tiene autenticación integral. Mantener solo intranet mientras se completa SSO/RBAC.