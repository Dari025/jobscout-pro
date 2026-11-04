# Revisión de privacidad de JobScout Pro

**Estado: nota técnica para una beta; no es un aviso legal ni una certificación de cumplimiento del RGPD.** Antes de ofrecer el producto comercialmente, el responsable debe completar los datos identificativos y revisar el alojamiento, los proveedores y la base jurídica.

## Qué hace el código actual

### CV opcional
- El usuario elige un PDF y debe marcar una casilla de consentimiento antes de que el texto se extraiga y se use para el ranking.
- El archivo se recibe y analiza en la memoria del servidor que ejecuta Streamlit. Límites actuales: 5 MB, 15 páginas y 100.000 caracteres extraídos.
- El texto del CV se mantiene en el estado de la sesión de Streamlit. El código del dashboard no lo escribe en YAML ni en la base SQLite de vacantes.
- El ranking ordinario no envía el CV a las fuentes de empleo ni a un modelo externo.
- Existe una pestaña independiente de análisis de CV con Groq. Solo se ejecuta tras marcar un consentimiento específico y pulsar el botón de análisis; el consentimiento de procesamiento local del PDF no habilita por sí mismo el envío externo.
- La app transmite texto extraído, nunca el PDF, elimina patrones comunes de email, teléfono y URL y limita el texto a 18.000 caracteres. La redacción automática no garantiza anonimización completa; el CV puede seguir conteniendo nombres, empleadores, centros formativos u otros datos personales.
- La clave API personal y el informe se mantienen en el estado de sesión; no se escriben en YAML ni SQLite. La clave pasa por el servidor Streamlit que ejecuta JobScout y, por tanto, el administrador de la instancia alojada debe considerarse parte de la superficie de confianza. En despliegues de terceros se debe advertir al usuario que no introduzca una clave si no confía en quien opera el servidor; una instalación local o propia reduce esa exposición frente a un hosting ajeno. Al retirar el consentimiento de IA se elimina el informe y se borra la clave del estado de sesión. Al borrar o sustituir el CV también se invalida el informe.
- Groq declara que no utiliza customer data para entrenar sus modelos. La inferencia no se retiene por defecto, pero entradas/salidas pueden registrarse hasta 30 días para solucionar problemas o investigar abusos, salvo que se habilite Zero Data Retention (ZDR). Groq declara que los datos retenidos se alojan en GCP en Estados Unidos. El usuario debe revisar las condiciones vigentes y sus controles de datos antes de aceptar.
- Desmarcar el consentimiento elimina el texto extraído de la puntuación. El botón **Borrar CV y archivo** también reinicia el selector de archivos para retirar el documento cargado de esa sesión.
- El parser no guarda el PDF en una ruta local. Este hecho describe el código; no debe confundirse con una garantía de borrado físico inmediato de memoria o de la infraestructura del proveedor de alojamiento.

### Datos de búsqueda
- Los puestos objetivo y ubicaciones se escriben en un fichero de configuración temporal de la sesión para ejecutar el rastreador.
- Las vacantes devueltas se guardan en una base SQLite temporal propia de esa sesión.
- La ruta temporal queda aislada por un identificador aleatorio de sesión.
- El código toca un marcador de actividad y elimina directorios de sesión inactivos durante más de 24 horas cuando se procesa una nueva petición/rerun. No es un borrado programado en el segundo exacto de cumplir 24 horas; si no hay actividad posterior, la limpieza puede ejecutarse después.

## Fuentes y transferencias

- La interfaz utiliza fuentes del sistema y no descarga tipografías desde Google Fonts u otro proveedor externo.

La búsqueda nunca envía el texto del CV a los proveedores de ofertas. Freehire recibe el término y la ubicación. Arbeitnow y Jobicy descargan feeds públicos; sus coincidencias por título se filtran localmente. Jobicy recibe únicamente la región geográfica elegida (no el puesto ni el CV), y su feed remoto se descarga y almacena en caché local. El feed público de Jobicy se conserva en una caché local de una hora bajo el directorio de datos de usuario; contiene anuncios públicos, no datos personales del candidato. Jobicy exige atribución y conservar el enlace canónico; Freehire limita el uso sin clave a lo personal/no comercial; Arbeitnow exige enlazar de vuelta y puede revocar el permiso. Revisa las condiciones y el README antes de ampliar el uso. Los proveedores pueden registrar las consultas HTTP normales de sus servicios. Si el dashboard está desplegado en la nube, el archivo PDF viaja desde el navegador hasta el servidor de la aplicación y el proveedor de alojamiento opera esa infraestructura. Si el usuario activa de forma separada el análisis con IA, el texto redactado se transmite a la API de Groq en Estados Unidos; la app no almacena una copia local adicional de esa petición ni usa endpoints de batch o fine-tuning.

## Acciones para el usuario
1. No subir currículums de terceros ni información que no se quiera procesar en el servidor.
2. Desmarcar el consentimiento local deja de usar el texto del CV para el ranking y elimina el informe de IA asociado.
3. Desmarcar el consentimiento específico de IA elimina el informe y la clave API del estado de sesión.
4. Pulsar **Borrar CV** retira el texto extraído y reinicia el selector del archivo.
5. Recargar/cerrar la pestaña puede reiniciar el estado de la sesión; no debe presentarse como una garantía de borrado forense de infraestructura.

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
