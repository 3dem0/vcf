# Validación de campo

Fecha: 2026-10-05. Versión: `1.0.0-rc1`.

## Resultado reportado

El operador reportó funcionamiento correcto después de probar la candidata
con VCF Operations / Intelligent Assist 9.1.1, un gateway LiteLLM y modelos
on-premises. El reporte es una confirmación funcional del operador, no una
auditoría independiente ni un registro completo de cada comprobación.

El prototipo anterior había mostrado descubrimiento de modelos, inferencia
a través del bridge y una respuesta de alertas en el asistente de VCF.
La confirmación posterior corresponde a la candidata distribuible.

No se publican endpoints internos, credenciales, nombres de recursos, capturas,
logs ni identificadores corporativos. No se dispone aquí de una matriz pública
con el build exacto y el resultado individual de cada prueba. El checklist de
[validación](VALIDATION.md) queda como plantilla para registrar otras instalaciones.

## Alcance de esta publicación

El código ejecutable, la configuración de ejemplo, las dependencias y la definición
del contenedor se conservan sin cambios respecto de la candidata entregada.
La preparación para GitHub actualiza documentación e instrucciones de publicación.
No implica una instalación, reinicio ni modificación del despliegue existente.

Se mantiene la versión `1.0.0-rc1`. No se afirma compatibilidad universal,
certificación de Broadcom/VMware, auditoría de seguridad ni capacidad de carga
sostenida. El bridge no implementa PAIS completo: transporta el intercambio con
el proveedor y las herramientas de infraestructura continúan ejecutándose en VCF.

La corrección del `/v1` duplicado y el enriquecimiento de modelos estuvieron
presentes en la configuración que funcionó. No se aisló experimentalmente que
el enriquecimiento sea indispensable; ver [compatibilidad](COMPATIBILITY.md).
