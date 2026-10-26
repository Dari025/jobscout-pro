# JobScout Pro

JobScout Pro es una aplicación Streamlit para recoger, visualizar, filtrar y priorizar ofertas guardadas en SQLite. El ranking es un índice orientativo, no una probabilidad de conseguir el empleo.

El motor de recogida incluido en `src/job_scout` se basa en [job-scout](https://github.com/weberwcwei/job-scout), distribuido bajo licencia MIT. Consulta `THIRD_PARTY_NOTICES.md`.

## Estado y límites importantes

- El dashboard solo muestra ofertas que realmente están guardadas en SQLite. No crea vacantes ficticias cuando la base está vacía.
- El sistema descarta URLs que parecen páginas de búsqueda o portales genéricos. Esto no demuestra que la vacante siga activa ni que la página no haya cambiado; para eso hay que volver a consultar el portal de origen.
- El dashboard y el motor de recogida `job_scout.cli` están incluidos en este repositorio, dentro de `src/job_scout`.
- Los sitios de empleo pueden cambiar enlaces, retirar vacantes o aplicar límites. Respeta sus términos de uso.

## Modos de búsqueda

- **Rápida** (predeterminada en el dashboard): consulta una selección de fuentes y términos, limita la paginación, reduce los reintentos y no descarga cada descripción de LinkedIn por separado. Está pensada para obtener una primera lista con menos peticiones.
- **Completa**: intenta cubrir más resultados y recuperar más información. Puede tardar más y está sujeta a bloqueos, límites y cambios de las páginas externas.

No se garantiza una duración fija: el tiempo depende de la respuesta de cada portal. El panel muestra el registro de la ejecución y conserva los resultados que el motor haya guardado.

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

## Notificaciones de Telegram

Revoca cualquier token que haya estado publicado en el repositorio. Crea un token nuevo en Telegram con BotFather y guárdalo como variable de entorno en PowerShell (solo para la sesión actual):

```powershell
$env:TELEGRAM_BOT_TOKEN = "PEGA_AQUI_EL_TOKEN_NUEVO"
$env:TELEGRAM_CHAT_ID = "TU_CHAT_ID"
python notificar_top.py
```

No guardes el token en el repositorio, en capturas de pantalla ni en archivos que vayas a publicar. Las variables de entorno de PowerShell dejan de existir al cerrar esa terminal, salvo que las configures de forma persistente tú mismo.

## Pruebas

```powershell
pip install pytest
python -m pytest -q
```

Las pruebas cubren rechazo de URLs genéricas, separación de enlace del anuncio y de candidatura, cálculo de coincidencias sin falsos positivos con la letra R y carga de la tabla SQLite.

## Seguridad

- `busqueda.yaml`, `.env` y las bases de datos son locales y no deben subirse.
- No se debe interpretar el índice como probabilidad de contratación.
- El CV se lee para el ranking local de la sesión; no subas CV ni información personal a un repositorio público.
