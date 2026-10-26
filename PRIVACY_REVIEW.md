# Revisión de privacidad de JobScout Pro

**Estado: nota técnica para una beta; no es un aviso legal ni una certificación de cumplimiento del RGPD.** Antes de ofrecer el producto comercialmente, el responsable debe completar los datos identificativos y revisar el alojamiento, los proveedores y la base jurídica.

## Qué hace el código actual

### CV opcional
- El usuario elige un PDF y debe marcar una casilla de consentimiento antes de que el texto se extraiga y se use para el ranking.
- El archivo se recibe y analiza en la memoria del servidor que ejecuta Streamlit. Límites actuales: 5 MB, 15 páginas y 100.000 caracteres extraídos.
- El texto del CV se mantiene en el estado de la sesión de Streamlit. El código del dashboard no lo escribe en YAML ni en la base SQLite de vacantes.
- El código del dashboard no envía el CV a las fuentes de empleo ni a Gemini/u otro modelo externo para puntuar las vacantes.
- Desmarcar el consentimiento elimina el texto extraído de la puntuación. El botón **Borrar CV y archivo** también reinicia el selector de archivos para retirar el documento cargado de esa sesión.
- El parser no guarda el PDF en una ruta local. Este hecho describe el código; no debe confundirse con una garantía de borrado físico inmediato de memoria o de la infraestructura del proveedor de alojamiento.

### Datos de búsqueda
- Los puestos objetivo y ubicaciones se escriben en un fichero de configuración temporal de la sesión para ejecutar el rastreador.
- Las vacantes devueltas se guardan en una base SQLite temporal propia de esa sesión.
- La ruta temporal queda aislada por un identificador aleatorio de sesión.
- El código toca un marcador de actividad y elimina directorios de sesión inactivos durante más de 24 horas cuando se procesa una nueva petición/rerun. No es un borrado programado en el segundo exacto de cumplir 24 horas; si no hay actividad posterior, la limpieza puede ejecutarse después.

## Fuentes y transferencias

- La interfaz utiliza fuentes del sistema y no descarga tipografías desde Google Fonts u otro proveedor externo.

La búsqueda envía a los proveedores de búsqueda los términos del puesto y la ubicación necesarios para consultar vacantes. No envía el texto del CV. Los proveedores de empleo pueden recibir y registrar las consultas HTTP normales de sus servicios. Si el dashboard está desplegado en la nube, el archivo PDF viaja desde el navegador hasta el servidor de la aplicación y el proveedor de alojamiento opera esa infraestructura.

## Acciones para el usuario
1. No subir currículums de terceros ni información que no se quiera procesar en el servidor.
2. Desmarcar el consentimiento deja de usar el texto del CV para el ranking.
3. Pulsar **Borrar CV y archivo** retira el texto extraído y reinicia el selector del archivo.
4. Recargar/cerrar la pestaña puede reiniciar el estado de la sesión; no debe presentarse como una garantía de borrado forense de infraestructura.

## Lista obligatoria antes de un lanzamiento comercial
- [ ] Identificar legalmente al responsable del tratamiento y publicar un medio de contacto válido.
- [ ] Definir finalidades, bases jurídicas, conservación y ejercicio de derechos.
- [ ] Verificar condiciones, ubicación del tratamiento y subencargados del proveedor de hosting.
- [ ] Revisar logs, métricas, analítica, cookies, copias de seguridad y límites de acceso del despliegue real.
- [ ] Revisar las condiciones de las fuentes de ofertas y las restricciones de reutilización.
- [ ] Completar un aviso de privacidad legalmente revisado y vincularlo desde la aplicación.
- [ ] Probar el botón de borrado, retirada de consentimiento, aislamiento entre sesiones y expiración en el entorno de despliegue real.

## Metadatos públicos del repositorio

El repositorio es público y el historial de Git muestra metadatos de autor de los commits, incluido un correo universitario del autor. El escaneo de secretos no detecta esto como una credencial, pero sí es información personal visible públicamente. Para los próximos commits, configura en GitHub un correo de tipo `noreply` como correo de commits. El correo de commits que ya aparece en el historial no se oculta cambiando `.gitignore`; eliminarlo de los commits existentes requiere reescribir el historial y actualizar las referencias, con el impacto que eso puede tener en clones y ramas existentes. Esta revisión no reescribe ese historial automáticamente.

## Alcance de esta revisión

Se han revisado el flujo del CV en el código del dashboard, la configuración y aislamiento de espacios temporales, el archivo .gitignore, los archivos visibles del repositorio y la automatización propuesta. La revisión no puede certificar la configuración privada del hosting, los permisos de cuenta de GitHub, la lista de subencargados activa ni la eliminación de secretos de todo el historial hasta completar el escaneo automático del historial.
