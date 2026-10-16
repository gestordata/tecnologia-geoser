# CLAUDE.md — Contexto de continuidad

Proyecto: **Inventario tecnológico GeoSer**. Propósito: controlar hoja de vida por equipo y colaborador, activo actual, serial/nomenclatura, fotos, actas de entrega/devolución, asignaciones históricas y trazabilidad de importaciones.

## UX — decisión expresa del solicitante
**NO** crear "Hojas de vida" como módulo aparte. Desde el listado **Equipos**, clic en nomenclatura/fila => ficha completa del equipo. Desde **Colaboradores**, clic en fila/nombre => ficha del usuario. Botón **Editar** separado. Actualmente se muestran en modal; próxima iteración puede usar vista inmersiva integrada en la misma sección, nunca una navegación a módulo independiente.

## Regla de identidad
Primera columna `EQUIPOS GEOSER` de `Nomenclatura_Computadores_GEOSER.xlsx` es nomenclatura oficial (hostname, p. ej. PGS-PC-023), columna `equipment.device_name`. `asset_tag` es identificador interno provisional, `serial` es serial físico. No fusionar por similitud de responsable/nombre sin confirmación.

## Stack y servidor
Python HTTPServer Threading + SQLite, HTML/CSS/JS, sin dependencias web build. Ubuntu, `/opt/geoser/tecnologia-geoser`, puerto 3014, cron `start.sh` existente en producción. Repositorio aislado del Semáforo Comercial.

## Esquema
`people`, `equipment`, `movements`, `evidence`; tablas relacionales `source_records`, `asset_assignments`, `identity_review`. Código API principal `server.py`, perfiles/migración `profiles.py`, script de importación controlada `apply_official_names.py`. Fotos adjuntas en `data/photos`, evidencias en `data/uploads` (ignoradas por Git).

## Riesgos conocidos / prioridades
- P0 seguridad: sin SSO/RBAC de producción; no hacer DNS público ni publicar información de colaboradores.
- P0 endurecer endpoint de fotos/evidencias, validar MIME y autenticación, revisar exposición de fotos.
- P1 mejorar consistencia de asignaciones actuales: fuentes con responsables no son necesariamente vigentes.
- P1 conciliación nomenclatura ↔ serial: 95 nomenclaturas, muchas sin correlación verificada.
- P1 UI integrada de hoja de vida (modal existente): navegar equipo/colaborador, fotos, actas, origen, responsive.
- P2 revisión de identidades pendientes, conciliación asistida y reporte de conflictos.
- P2 pruebas automatizadas de backend/API y migraciones versionadas.
- P3 conectar data comercial/ventas solo después de autorización explícita.

## Reglas de entrega
No subir archivos de Excel con datos personales, SQLite, fotos, actas, secretos, registros de logs. Conservar backup y plan de reversión previo a deploy. No tocar otras apps /opt/geoser/.