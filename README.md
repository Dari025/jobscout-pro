# JobScout Pro

JobScout Pro es una aplicación Streamlit para recoger, visualizar, filtrar y priorizar ofertas guardadas en SQLite. El ranking es un índice orientativo, no una probabilidad de conseguir el empleo.

El motor de recogida incluido en `src/job_scout` se basa en [job-scout](https://github.com/weberwcwei/job-scout), distribuido bajo licencia MIT. Consulta `THIRD_PARTY_NOTICES.md`.

## Estado y límites importantes

- El dashboard solo muestra ofertas que realmente están guardadas en SQLite. No crea vacantes ficticias cuando la base está vacía.
- El sistema descarta URLs que parecen páginas de búsqueda o portales genéricos. Esto no demuestra que la vacante siga activa ni que la página no haya cambiado; para eso hay que volver a consultar el portal de origen.
- El dashboard y el motor de recogida `job_scout.cli` están incluidos en este repositorio, dentro de `src/job_scout`.
- Los sitios de empleo pueden cambiar enlaces, retirar vacantes o aplicar límites. Respeta sus términos de uso.

## Modo multiusuario de la aplicación web

La aplicación web pública arranca con puestos y ubicaciones vacíos: cada visitante introduce su propia búsqueda. Cada sesión del navegador recibe un identificador aleatorio, una configuración temporal y una base SQLite propia; la lectura de ofertas nunca recurre a una base compartida si la base de esa sesión no existe o está vacía. Los datos de un perfil anterior no se usan como valores por defecto.

El selector del CV permanece desactivado hasta que el usuario marque una casilla de consentimiento situada antes de la subida. La extracción del PDF se hace en memoria con límites de 5 MB, 15 páginas y 100.000 caracteres extraídos. El texto del CV no se escribe en la configuración del rastreador ni en SQLite, y el ranking del dashboard no envía el CV a proveedores de empleo ni a modelos externos.

La casilla de consentimiento puede desmarcarse en cualquier momento; al retirarla se borra el texto extraído del estado de la sesión y se reinicia el selector del archivo. El botón «Borrar CV y archivo» permite hacerlo explícitamente.

Las búsquedas y los resultados se guardan en un espacio temporal independiente por sesión. La app intenta eliminar espacios inactivos de más de 24 horas cuando procesa nuevas peticiones; esto no constituye una garantía de borrado físico inmediato de la infraestructura del proveedor de alojamiento.

El espacio está pensado para una beta web compartida y no sustituye a un sistema de autenticación o gestión de cuentas. Consulta [PRIVACY_REVIEW.md](PRIVACY_REVIEW.md) para los flujos de datos y la lista de comprobaciones previas a un lanzamiento comercial.

## Filtros opcionales y lectura de requisitos

Los filtros avanzados están desactivados por defecto. El usuario puede activar, de forma independiente, un salario mínimo bruto anual en EUR, nivel de experiencia, tipo de contrato y modalidad de trabajo. Por defecto, los anuncios sin información suficiente se mantienen; cada filtro permite excluir los datos desconocidos de forma expresa.

Las tarjetas incluyen una lectura automática y explicable de las condiciones: salario publicado y periodo, años de experiencia detectados, nivel aproximado, tipo de contrato, modalidad y herramientas mencionadas. Si se carga un CV con consentimiento, se comparan los requisitos detectados con el texto disponible en la sesión. Esta extracción no es un LLM ni una predicción de contratación; muestra evidencia encontrada, no inventa datos que falten y puede pasar por alto formulaciones poco habituales. Los importes en monedas distintas del EUR no se convierten para el filtro salarial.

## El motor de ranking no usa IA en tiempo de ejecución

JobScout Pro no envía tu CV ni tus búsquedas a ningún modelo de lenguaje. El índice de encaje se calcula con un algoritmo determinista y auditable:

- solapamiento de vocabulario entre tu CV y el texto del anuncio;
- coincidencia de títulos, incluidos alias profesionales («Hydrogeologist» ↔ «Groundwater Specialist»);
- una penalización conservadora cuando el anuncio pertenece a otro dominio profesional.

Las mismas entradas producen siempre la misma puntuación, cada punto se puede explicar y no hay claves de API ni coste por búsqueda. La inteligencia artificial se usó como herramienta de desarrollo, no como dependencia en ejecución. Cualquier funcionalidad futura que quisiera enviar el CV a un proveedor externo tendría que venir con consentimiento explícito y con cambios en este documento y en [PRIVACY_REVIEW.md](PRIVACY_REVIEW.md); no forma parte de esta versión.

## Modos de búsqueda

- **Rápida** (predeterminada en el dashboard): consulta una selección de fuentes y términos, limita la paginación, reduce los reintentos y no descarga cada descripción de LinkedIn por separado. Está pensada para obtener una primera lista con menos peticiones.
- **Completa**: intenta cubrir más resultados y recuperar más información. Puede tardar más y está sujeta a bloqueos, límites y cambios de las páginas externas.

No se garantiza una duración fija: el tiempo depende de la respuesta de cada portal. El panel muestra el registro de la ejecución y conserva los resultados que el motor haya guardado.

## Fuentes de búsqueda y diagnóstico

La búsqueda rápida prioriza **Freehire** y **Arbeitnow**, fuentes con respuestas estructuradas, y también consulta LinkedIn e Indeed como respaldo por si la fuente principal no tiene vacantes para una consulta concreta. La búsqueda completa amplía la cobertura con más términos y páginas. Google Jobs se omite porque el resultado actual requiere JavaScript y el parser del servidor no puede recogerlo de forma fiable.

- Freehire publica una API de lectura gratuita para uso personal y no comercial. Si conviertes la app en un servicio ofrecido a otras personas, consulta su licencia y plan de API antes de compartir vacantes de esa fuente.
- Arbeitnow ofrece un feed de vacantes con enlaces a páginas de anuncio individuales; la aplicación filtra los resultados por puesto y ubicación.
- La aplicación registra por fuente las consultas, anuncios recibidos, consultas vacías y errores. Si ninguna fuente devuelve ofertas utilizables, la búsqueda termina con advertencia y código de error: ya no se presenta un resultado vacío como si todo hubiera salido bien.
- Los portales pueden limitar peticiones, cambiar sus páginas o retirar anuncios. La comprobación de URL confirma que el enlace es específico, pero no garantiza que el puesto siga abierto; comprueba la oferta antes de solicitarla.

## Uso responsable y límites legales

JobScout Pro es una herramienta **personal y educativa**, no un servicio comercial ni un producto ofrecido a terceros. Conviene tenerlo presente al compartirla:

- **Freehire** publica su API de lectura gratuita para uso personal y no comercial. Este proyecto encaja en ese uso; convertirlo en un servicio para otras personas exigiría revisar su licencia y su plan de API.
- **LinkedIn** e **Indeed** no autorizan el scraping en sus términos de servicio. La aplicación los consulta como fuentes de respaldo y esa elección es configurable: si publicas o compartes el proyecto, revisa antes esas condiciones y decide si los mantienes activos.
- Respeta los límites de peticiones de cada portal y no uses la herramienta para recopilar datos a gran escala.
- El índice de encaje es orientativo: no es una probabilidad de contratación ni un filtro automático de candidaturas.

## Instalación en Windows

Requiere Python 3.10 o superior.

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Crea tu configuración privada:

```powershell
Copy-Item .\busqueda.example.yaml .\busqueda.yaml
```

Edita `busqueda.yaml` con tu perfil y las búsquedas que te interesan. No subas ese archivo a GitHub. El texto del CV debe estar vacío en el ejemplo; introduce únicamente la información que quieras usar en tu equipo.

Arranca el dashboard:

```powershell
streamlit run app.py
```

## Base de datos

La aplicación busca la base de datos en una lista corta de ubicaciones conocidas. Puedes definir la ubicación exacta mediante una variable de entorno:

```powershell
$env:JOBSCOUT_DB_PATH = "C:\Users\TU_USUARIO\AppData\Local\job_scout\jobs.db"
```

También se puede configurar `db_path` en el YAML privado. La app abre la base en modo de solo lectura y busca una tabla con registros que incluyan título y empresa. Si no encuentra ofertas válidas, muestra un aviso en vez de inventar resultados.

## Filtros y ofertas con información incompleta

Los filtros son acumulables: puesto/palabra clave, fecha de publicación, relevancia, fuentes, salario mínimo/máximo, experiencia, tipo de contrato, modalidad, duración y horas semanales. Experiencia, contrato, modalidad y duración permiten seleccionar varias opciones.

**Regla de datos desconocidos:** los campos ausentes o no comparables se mantienen en los resultados por defecto. Cada filtro tiene una opción para conservar o excluir expresamente las ofertas sin ese dato. La extracción de duración, horas y salario se basa en texto/metadatos explícitos; no se consideran valores estimados como si fueran datos publicados.

El modo sin CV sigue disponible: basta con indicar uno o varios puestos y una ubicación. El CV es opcional y solo se usa para el análisis de relevancia en la sesión actual.

## Compartir el Top 10 sin configurar servicios

En la pestaña **Alertas**, JobScout muestra el Top 10 y un botón **Compartir Top 10**. En los navegadores que admiten el menú nativo de compartir, puedes elegir una aplicación que ya uses, como correo o mensajería. No necesitas crear una cuenta, configurar un bot ni introducir contraseñas en JobScout. Tú confirmas el envío desde la aplicación elegida.

Si el navegador no admite ese menú, el botón intentará **copiar el resumen automáticamente** para que solo tengas que pegarlo en tu correo o mensajería. Si el navegador también bloquea el portapapeles, pulsa **Descargar resumen completo (.txt)**. Incluye puestos, empresas, puntuación orientativa, condiciones conocidas, pros, puntos que conviene comprobar y enlaces a los anuncios originales.

La app no envía mensajes por su cuenta ni programa avisos en segundo plano: compartir es una acción manual y explícita. Un envío automático de correo necesitaría credenciales de envío o un servicio externo; para conservar una experiencia sencilla no se pide configurar nada de eso.

**Importante:** los campos que el anuncio no publica aparecen como «No indicado» y la oferta se conserva por defecto. Solo se excluye un campo desconocido si el usuario activa expresamente el ajuste correspondiente.

## Pruebas

```powershell
pip install pytest
python -m pytest -q
python scripts/simulate_ranking.py
```

Las pruebas cubren rechazo de URLs genéricas, separación de enlace del anuncio y de candidatura, coincidencias por palabras completas, carga y aislamiento de SQLite, retirada y límites de CV, aislamiento del entorno del subproceso, arranque de Streamlit y regresiones de ranking. Consulta [SIMULATION_RESULTS.md](SIMULATION_RESULTS.md) para la batería sintética y sus limitaciones.

## Seguridad

- `busqueda.yaml`, `.env` y las bases de datos son locales y no deben subirse.
- No se debe interpretar el índice como probabilidad de contratación.
- El CV se lee para el ranking local de la sesión; no subas CV ni información personal a un repositorio público.
