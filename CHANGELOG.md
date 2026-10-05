# Changelog

## 1.0.0-rc1 — 2026-10-05

Primera candidata distribuible, derivada de un prototipo probado por el operador.

Configuración genérica por `.env`; credenciales independientes; migración en el mismo puerto y rollback; HTTPS con certificado reutilizable; listado enriquecido o passthrough; alias de rutas; chat JSON/SSE sin cambio del body; filtros de modelos también en inferencia; errores saneados; logs sin contenido; health/readiness; contenedor sin root y con límites; tests y documentación.

Se conserva el campo de compatibilidad `status=AVAILABLE` del prototipo, pero no se afirma que sea requerido por VCF. Se documenta la evidencia del `/v1` duplicado sin concluir que el enriquecimiento era necesariamente la causa original.

Actualización de documentación para publicación: el operador reportó funcionamiento correcto de la candidata; se agrega el alcance de ese reporte y una guía de publicación desde PC, sin acceder a la VM productiva. El código ejecutable no cambia.

Se mantiene `1.0.0-rc1`. Una release estable requiere documentar la matriz de compatibilidad, revisar dependencias/imagen y decidir explícitamente la promoción. No se publica automáticamente.
