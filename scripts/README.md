# Auto-actualización de resultados

Robot que, cada 30 minutos, lee los partidos terminados del Mundial 2026, escribe
los marcadores reales en Firebase y recalcula los puntos de todos los jugadores.
Así la quiniela se actualiza sola sin entrar al panel de Admin.

- `update_results.py` — el robot (solo librería estándar de Python, sin instalar nada).
- `../.github/workflows/update-results.yml` — lo corre solo cada 30 min en GitHub Actions.

## Puesta en marcha (una sola vez)

### 1. Sacar la API key gratuita de football-data.org
1. Entrá a https://www.football-data.org/client/register
2. Registrate con tu correo (plan **Free**, sin tarjeta).
3. Te llega por correo un **API token** (una cadena larga de letras y números). Copialo.

### 2. Guardar el token como secreto en GitHub
1. Andá al repo en GitHub → **Settings** → **Secrets and variables** → **Actions**.
2. **New repository secret**.
3. Name: `FOOTBALL_DATA_TOKEN` — Secret: pegá el token. **Add secret**.

### 3. Probar antes de dejarlo en vivo (recomendado)
1. En el repo → pestaña **Actions** → workflow **Actualizar resultados quiniela**.
2. **Run workflow**. Dejá marcada la casilla **Modo prueba** (no escribe nada).
3. Abrí la corrida y mirá el log: debe decir cuántos partidos emparejó. Si avisa
   de partidos "sin emparejar", es un nombre de equipo a ajustar en `TEAMS`.

### 4. Dejarlo automático
No hay que hacer nada más: la corrida programada (cada 30 min) ya escribe de verdad.
Si querés forzar una actualización inmediata, usá **Run workflow** y **desmarcá**
"Modo prueba".

## Probar en tu compu (opcional)
```powershell
$env:FOOTBALL_DATA_TOKEN = "tu_token"
$env:DRY_RUN = "1"   # prueba, no escribe
python scripts/update_results.py
```

## Notas
- **Fase de grupos:** funciona de una, empareja por nombre de equipo.
- **Eliminatorias:** se resuelven leyendo la tabla de posiciones de la API (quién
  quedó 1°/2° de cada grupo) y propagando los ganadores ronda por ronda. Solo se
  puede validar de verdad cuando empiecen (28 jun).
- El robot **nunca borra** nada: solo escribe marcadores y puntos.
- Si football-data.org usara otro código para el Mundial, se cambia con la variable
  de entorno `COMPETITION` (default `WC`).
