# Arquitectura y modelo relacional

## Datos principales
- `people.id` PK: nombre, cédula, correo, cargo, área/centro de costos, teléfono, foto, external_sales_key.
- `equipment.id` PK: device_name (nomenclatura oficial, único), asset_tag (placa interna), serial (único no vacío), IMEI, tipo, fabricante/modelo, condición/estado, asignado actual (FK people), SO, Bitdefender, renting, foto y metadatos.
- `movements.id` PK: movimiento histórico/acta (entrega/devolución), case_no, fecha, persona FK, equipo FK, detalle, observaciones y origen.
- `evidence.id` PK: adjuntos por `movement_id`.
- `source_records.id`: procedencia exacta `source_file + source_sheet + source_row`, JSON original y FKs resueltas; `matching_method`.
- `asset_assignments.id`: histórico equipo-persona con fechas, origen y movimiento.
- `identity_review`: relaciones dudosas no confirmadas; no alterar la asignación actual hasta validar.

## Claves y prioridades de conciliación
1. Equipos: serial exacto normalizado o nomenclatura oficial inequívoca.
2. Personas: documento exacto válido, luego nombre exacto único normalizado.
3. Nunca vincular un equipo a una persona por simple similitud o porque aparezca como responsable en una fuente antigua.
4. Conservar la fila de origen siempre y marcar pendiente si no hay evidencia suficiente.

## DDL/migración
El esquema base se inicializa en `server.py` y la extensión relacional en `profiles.py`. Para evitar drift, migrar a versiones SQL numeradas antes de próximas actualizaciones.

## Despliegue
`HOST=0.0.0.0 PORT=3014 python3 server.py`, `start.sh` supervisa mediante cron en servidor actual. No se versionan bases reales ni configuración de red. DNS pendiente.