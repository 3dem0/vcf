# Seguridad

Proyecto comunitario en fase RC. No existe una garantía de seguridad, una auditoría externa ni soporte del fabricante.

## Secretos y datos

Mantener `.env` y `certs/key.pem` con permiso 600. `.local/` contiene backups de credenciales y debe permanecer privada. Docker y sus administradores pueden leer las variables del contenedor: la separación entre keys evita reenviarlas al destinatario incorrecto, pero no las protege del administrador del host.

No publicar `.env`, certificados/key, backups, logs del prototipo, capturas con datos internos ni salidas de `docker inspect`/`docker compose config`. `.gitignore` y `.dockerignore` reducen errores comunes, pero `git add -f` y una copia manual pueden saltarlos. El exportador de código no es un detector exhaustivo de secretos.

Los logs del bridge omiten contenido. El proveedor y VCF tienen su propio almacenamiento/auditoría: revisar retención, permisos y destino de los prompts. Configurar un proveedor externo significa que los datos enviados por VCF pueden salir de la infraestructura local.

## Acceso

La key pública es obligatoria; no exponer el puerto a Internet. Restringir origen a los nodos/servicios VCF autorizados mediante controles de red compatibles con la publicación de puertos Docker. No se modifican reglas de firewall automáticamente.

Preferir una key upstream limitada a los modelos y cuotas del bridge. Configurar `EXPOSE_MODELS`. El bridge no tiene identidades individuales, rotación dual de keys, rate limit por usuario ni almacén de secretos externo. Una key común no sustituye los permisos RBAC de VCF.

La autenticación, integridad y permisos de las herramientas dentro de VCF siguen siendo responsabilidad de VCF y el operador. Los modelos pueden generar errores o interpretar instrucciones presentes en datos; no usar respuestas de IA como autorización automática de cambios operativos.

## Transporte y recursos

Verificar TLS upstream; usar CA propia antes que desactivar verificación. No se siguen redirects upstream para evitar reenviar la key a un destino alternativo. Validar la URL configurada: no debe volver al propio bridge.

No se reenvían headers arbitrarios del cliente, cookies ni credenciales públicas. No hay proxy genérico de rutas administrativas. Tamaños y concurrencia están limitados; siguen haciendo falta vigilancia de carga y límites del proveedor.

La imagen ejecuta el servicio sin root, sin privilegios, sin Docker socket y con raíz de solo lectura. Esto no reemplaza el mantenimiento del kernel, Docker ni dependencias.

## Reportar problemas

No abrir una issue pública con secretos o detalles de un cliente. Rotar una key expuesta y utilizar el canal privado que el mantenedor habilite en el repositorio definitivo. Incluir versión, reproducción mínima y logs saneados. Antes de una publicación estable, revisar avisos de seguridad de dependencias e imagen base y registrar el resultado.
