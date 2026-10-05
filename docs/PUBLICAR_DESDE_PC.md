# Publicar desde una PC, sin acceder a la VM productiva

El ZIP contiene fuentes y documentación. No hay que conectarse a la VM, instalar Git
allí, detener contenedores ni copiar su configuración para publicar este proyecto.

## 1. Extraer el ZIP

Descargarlo en la PC y usar «Extraer todo». Entrar en la carpeta que contiene
`README.md`, `Dockerfile`, `compose.yaml`, `.env.example`, `.github/`, `bridge/` y `docs/`.

**Se sube el contenido de esa carpeta, no el ZIP ni otra carpeta contenedora.**
No crear un `.env` real en esta copia: `.env.example` contiene únicamente ejemplos.
No editar los archivos con herramientas que cambien sus saltos de línea antes de
subirlos. La carga web no aplica la normalización de `.gitattributes`.

## 2. Cargar al repositorio ya creado

Abrir el repositorio en GitHub, pestaña **Code**. Seleccionar **Add file → Upload files**
o, para un repositorio vacío, el enlace para cargar archivos existentes.
Arrastrar desde el Explorador todos los archivos y carpetas interiores.

Comprobar que `README.md`, `Dockerfile` y `compose.yaml` queden directamente en la
raíz del repositorio. Conservar también los archivos cuyo nombre empieza con punto:
`.env.example`, `.gitignore`, `.dockerignore`, `.gitattributes` y `.github/workflows/ci.yml`.
Las carpetas `certs/` y `ca/` solo contienen un `.gitkeep` vacío, no certificados.

La primera carga de un repositorio nuevo puede usar el mensaje:

```text
Publicación inicial de VCF AI OpenAI Bridge 1.0.0-rc1
```

Confirmar con **Commit changes** si se permite la escritura directa. Cuando la
rama esté protegida o la interfaz proponga una rama nueva, usar **Propose changes**
y completar el pull request. Si el repositorio ya tiene README o LICENSE, revisar
el reemplazo: la licencia de este paquete es MIT.

Revisar la lista de archivos antes de confirmar. Los nombres de archivos privados,
certificados o respaldos no deben aparecer; nunca agregar secretos para completar
una prueba desde el repositorio público.

## 3. Revisar GitHub Actions

En **Actions**, revisar la ejecución **Source tests and container build** del commit
publicado. El workflow incluido construye la imagen; el Dockerfile ejecuta la suite
de tests como etapa requerida. No despliega a la VM y no recibe sus credenciales.

Un estado verde confirma ese build, no la compatibilidad con cada instalación VCF.
Si no aparece una ejecución, verificar que `.github/workflows/ci.yml` se haya cargado
y que Actions esté permitido por la configuración del repositorio. Ante un error,
abrir el job y revisar el log; no declararlo aprobado sin verlo.

## 4. Crear la release desde el navegador

Con la carga revisada y el workflow aprobado, ir a **Releases → Draft a new release**
o **Create a new release**, según el estado del repositorio.

- Tag: `v1.0.0-rc1`, creado sobre la rama que contiene el código revisado.
- Título: `VCF AI OpenAI Bridge 1.0.0-rc1`.
- Descripción: copiar [las notas de release](RELEASE_NOTES.md).
- Marcar **This is a pre-release**, porque el código conserva `rc1`.

Se puede adjuntar el ZIP limpio como asset descargable y luego usar **Publish release**.
No confundir adjuntar el ZIP a una release con cargar las fuentes: el repositorio
necesita los archivos extraídos del paso 2 para mostrar el README y ejecutar CI.
Si se modificaron los archivos después de descargar este ZIP, no adjuntar un paquete
antiguo como si correspondiera al nuevo commit; usar los archivos fuente de la release.

No editar la versión del código ni renombrar la release como estable `1.0.0` solo
para quitar `rc1` del título.

## 5. Compartir

Copiar la URL pública del repositorio y completar [el texto de LinkedIn](LINKEDIN.md).
No adjuntar pantallas del entorno sin quitar dominios, IPs, nombres de recursos y
cualquier dato corporativo. La publicación no implica respaldo del fabricante.

## Referencias oficiales

Consultadas el 2026-10-05:

- GitHub, carga de archivos: https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository
- GitHub, releases: https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository
