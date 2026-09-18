# StillFriends

Quién te sigue, quién te dejó de seguir y a quién sigues sin que te siga de vuelta
— en Facebook, Instagram y X — con historial de cada revisión. Todo en la terminal.

```
┌─────────────────────────────────────────────────────────────────┐
│  📸  Instagram   412 seguidores  (-2)   2026-09-13 19:51        │
│         Nuevos (1)              Se fueron (3)                   │
│  ┌────┬──────────┐              ┌────┬──────────┐               │
│  │ +  │ Caro     │              │ -  │ Beto     │               │
│  └────┴──────────┘              └────┴──────────┘               │
│   No te siguen de vuelta (18)                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Cómo funciona

Playwright conduce un perfil de Edge (o Chrome) con tus sesiones ya iniciadas:
no hay cookies exportadas ni tokens que caduquen.

Nunca se rasca el HTML: las redes lo cambian cada dos por tres.

- **Instagram** va por la API interna que usa su propia web
  (`/api/v1/friendships/<id>/followers/`), paginando hasta el final. Es exacta,
  rápida, y de paso te dice cuántos debería haber.
- **Facebook y X** cargan la lista y escuchan las respuestas JSON que la página
  pide sola mientras hace scroll.

En los dos casos se guarda el **ID interno** de cada cuenta, así que si alguien
se cambia el nombre o el usuario ya no aparece como "se fue uno y entró otro".

Cada pasada guarda una foto de la lista y añade una línea al historial.

Las altas y bajas se etiquetan según la lista: en seguidores son "nuevos
seguidores" y "se fueron"; en seguidos, "empezaste a seguir" y "dejaste de
seguir", que no es lo mismo.

**Una captura corta nunca se guarda.** Cuando la red dice cuántos seguidores
tienes y se recogen bastantes menos, la pasada se descarta con un aviso: si se
guardara, todos los que faltan aparecerían en la siguiente revisión como bajas
que nunca ocurrieron. `--force` salta la comprobación si sabes lo que haces.

## Instalación

```bash
pip install -r requirements.txt
```

No hace falta `playwright install`: el script usa el Edge (o Chrome) que ya
tienes instalado, no descarga ningun navegador aparte.

Luego copia la configuración y rellena tus datos:

```bash
cp config.example.toml config.toml
```

- `channel`: `msedge` (por defecto), `chrome`, `msedge-beta` o `chrome-beta`.
- `user_data_dir` y `profile`: si dejas `user_data_dir` vacío se usa la ruta
  estándar del navegador elegido. Para comprobarlo, abre `edge://version` (o
  `chrome://version`) y mira "Ruta del perfil": la carpeta padre va en
  `user_data_dir` y la última parte — `Default`, `Profile 3`... — en `profile`.
- `[urls]`: tus perfiles en cada red.

### Perfil propio: tu navegador no se toca

StillFriends usa un **perfil de navegador propio**, aparte del que usas a
diario. Inicias sesión una vez y queda guardada:

```bash
python stillfriends.py login
```

Se abre una pestaña por red, entras en cada una, vuelves y pulsas Enter. A
partir de ahí las revisiones funcionan **con tu Edge abierto**: nunca se cierra
ni se toca.

<details>
<summary>Por qué no usa directamente tu perfil de siempre</summary>

Sería lo ideal, pero ya no se puede. Desde **Chrome 136 / Edge 136** (cambio de
2025 contra malware que roba cookies), el navegador **ignora en silencio**
`--remote-debugging-port` cuando `--user-data-dir` apunta al perfil por defecto.
Sin error: el puerto simplemente no abre nunca. Y sin ese puerto no hay manera
de conducir la ventana que ya tienes abierta.

La otra vía —que Playwright arranque el navegador con tu perfil— choca con que
ni Edge ni Chrome admiten dos procesos sobre el mismo perfil, así que exigiría
cerrarlo en cada revisión.

El perfil propio evita las dos cosas. El precio es un login por red, una sola
vez.
</details>

Si prefieres controlarlo tú, `cdp_url` en `config.toml` se engancha a un
navegador que arranques con el puerto abierto — recordando que su
`--user-data-dir` no puede ser tu perfil normal, por lo de arriba.

## Uso

```bash
python stillfriends.py                      # revisar todo y comparar
python stillfriends.py check -p ig          # solo Instagram
python stillfriends.py check --no-following # solo seguidores, más rápido
python stillfriends.py check --dry-run      # mirar sin guardar
python stillfriends.py login                # iniciar sesion (la primera vez)
python stillfriends.py unrequited           # quién no te sigue de vuelta
python stillfriends.py history -d           # historial con nombres
python stillfriends.py history -p x -n 5    # últimas 5 revisiones de X
python stillfriends.py list -k following    # la lista guardada de seguidos
python stillfriends.py report               # abrir el informe HTML
python stillfriends.py check --html         # revisar y abrirlo al terminar
```

## El informe

Cada `check` deja `data/informe.html` al dia. Es un archivo suelto, sin
internet ni servidor: doble clic y listo.

Se organiza como una **línea de tiempo**: la revisión más reciente arriba y las
anteriores debajo, para leer de un vistazo cómo ha ido cambiando el asunto. Cada
pasada muestra qué se movió ese día, con nombres; las listas largas van plegadas
para que la línea siga siendo legible.

Debajo, el estado actual: quién no te sigue de vuelta, y las listas completas.

Arriba, una pestaña por red y los totales con su variación. El filtro busca en
toda la página a la vez y abre lo que esté plegado, para que no se te escape
nadie.

Es **oscuro siempre**, a propósito: no sigue el tema del sistema. Y se lee bien
en el móvil.

En Windows, **doble clic en `StillFriends.cmd`** abre un menú con todo lo
anterior — y se encarga de poner la consola en UTF-8, encontrar Python e
instalar las dependencias la primera vez. También acepta argumentos:
`StillFriends.cmd check -p ig`.

Sin `-p`, se revisan las redes de `platforms` en `config.toml`. Quita de esa
lista las que no uses y dejarán de avisar en cada pasada.

### Quién desapareció de tus seguidos

Que alguien caiga de tu lista de seguidos no siempre es cosa tuya. En Instagram,
cada baja de esa lista se investiga preguntando por la cuenta, y sale etiquetada:

- **la cuenta sigue ahí** — la dejaste de seguir tú.
- **cuenta borrada, inactiva o te bloqueó** — desapareció de tu vista.

Esas tres causas van juntas a propósito: Instagram responde exactamente igual
(404) en los tres casos, así que separarlas sería inventárselo. Lo que sí sabes
con certeza es que ya no puedes verla.

Solo se consulta a quien desapareció, no la lista entera, así que cuesta poco.

Facebook no tiene "seguidos": la amistad es mutua, así que ahí sólo hay lista de
amigos y no hay sección de no correspondidos.

**X necesita sesión iniciada**, aunque tu perfil sea público: `/followers` y
`/following` redirigen al perfil con muro de login. Los números son públicos,
las listas no.

## Dónde quedan los datos

```
data/
  ig/followers.json            última foto de la lista
  ig/followers_history.jsonl   una línea por revisión: totales, altas y bajas
  ig/following.json
  ig/following_history.jsonl
```

Son JSON normales, así que puedes abrirlos o procesarlos con cualquier cosa.
`data/` y `config.toml` están en `.gitignore`.

Si vienes de la versión vieja, los `FB.txt` / `IG.txt` se leen como punto de
partida en la primera pasada, emparejando por texto (nombre en Facebook,
usuario en Instagram) ya que aquellos ficheros no guardaban IDs.

Aquellos ficheros los escribía el script viejo con la codificación local de
Windows (cp1252), así que se leen probando utf-8 y cayendo a cp1252. Importa más
de lo que parece: leerlos mal convierte "Andrés" en "Andr?s", y un nombre roto
no empareja con nadie — la misma persona saldría como baja y como alta a la vez.

El único punto ciego que queda es ahí: quien se haya **cambiado el nombre de
usuario** desde entonces sí aparecerá duplicado esa primera vez. De la segunda
pasada en adelante ya no pasa, porque se compara por ID.

## Notas

- Las tres redes limitan cuánto puedes pedir seguido. Instagram responde 429 y
  el script te lo dice tal cual; se pasa solo esperando un rato. Si te ocurre a
  menudo, sube `scroll_pause_ms` en `[tuning]`.
- `--headless` va más rápido, pero Instagram y X detectan mejor el navegador sin
  ventana. Si una pasada sale vacía, prueba sin esa opción.
- `--headless` funciona, pero Instagram y X detectan mejor el navegador sin
  ventana. Con `cdp_url` no aplica: manda el modo con el que arrancó.
- La parte de Twitter ya no usa la API: la v1.1 de followers dejó de estar
  disponible en el plan gratuito, así que ahora X se lee igual que las otras dos.

## Licencia

MIT — ver [LICENSE](LICENSE).
