# VCF AI OpenAI Bridge 1.0.0-rc1

Primera publicación comunitaria del bridge para conectar el flujo observado de
VCF Intelligent Assist con un proveedor OpenAI-compatible.

## Incluye

Configuración mediante `.env`, API keys independientes para VCF y el proveedor,
HTTPS, descubrimiento configurable de modelos, transporte de chat JSON y SSE,
transporte de llamadas a herramientas, filtro de modelos, límites de solicitudes,
logs sin contenido sensible, healthcheck, migración reversible, pruebas automáticas
y documentación en español.

El operador reportó funcionamiento correcto de esta candidata con VCF Operations /
Intelligent Assist 9.1.1 y LiteLLM con modelos on-premises. El alcance y los límites
están registrados en `docs/FIELD_VALIDATION.md` y `docs/COMPATIBILITY.md`.

El código ejecutable se conserva respecto de la candidata entregada. La preparación
para GitHub actualiza documentación y agrega instrucciones de publicación desde PC.

## Alcance

Publicación `pre-release`, versión `1.0.0-rc1`. No implementa PAIS completo, no ejecuta
las herramientas de VCF y no ofrece compatibilidad universal ni soporte oficial
de Broadcom/VMware. La compatibilidad depende del cliente, el proveedor y el modelo.
No se realizó una auditoría independiente de seguridad ni una prueba de carga sostenida.

No incluye credenciales, configuración real de producción, certificados, backups ni logs.
