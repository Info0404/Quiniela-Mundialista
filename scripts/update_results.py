#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Actualizador automatico de resultados de la Quiniela Mundialista ASeguros.

Que hace en cada corrida:
  1. Consulta los partidos TERMINADOS del Mundial 2026 en football-data.org.
  2. Los empareja con los partidos de la quiniela (por nombre de equipo en
     grupos; por tabla de posiciones / bracket en eliminatorias).
  3. Escribe el marcador real en Firebase (nodo `results/<id>`).
  4. Recalcula los puntos de TODOS los jugadores (misma logica que la app web)
     y los escribe en `users/<usuario>/points`.

No tiene dependencias externas: solo libreria estandar de Python 3.

Variables de entorno:
  FOOTBALL_DATA_TOKEN  API key gratuita de football-data.org (obligatoria).
  FIREBASE_URL         URL de la Realtime Database (sin barra final).
  COMPETITION          Codigo de competencia en football-data (default: WC).
  DRY_RUN              "1"/"true" => no escribe nada, solo muestra que haria.
                       Si la variable no existe, se asume modo prueba (seguro).
"""

import os
import sys
import json
import unicodedata
import urllib.request
import urllib.error

# --------------------------------------------------------------------------
# Configuracion
# --------------------------------------------------------------------------
TOKEN = os.environ.get("FOOTBALL_DATA_TOKEN", "").strip()
FIREBASE_URL = os.environ.get(
    "FIREBASE_URL", "https://quiniela-aseguros-default-rtdb.firebaseio.com"
).rstrip("/")
COMPETITION = os.environ.get("COMPETITION", "WC").strip()
DRY_RUN = os.environ.get("DRY_RUN", "true").strip().lower() in ("1", "true", "yes", "si", "s")

API_BASE = "https://api.football-data.org/v4"

# --------------------------------------------------------------------------
# Fixture de la fase de grupos (id de la quiniela -> equipos, en espanol)
# --------------------------------------------------------------------------
GROUP_FIXTURE = [
    ("g01", "Mexico", "Sudafrica"), ("g02", "Corea del Sur", "Chequia"),
    ("g03", "Chequia", "Sudafrica"), ("g04", "Mexico", "Corea del Sur"),
    ("g05", "Chequia", "Mexico"), ("g06", "Sudafrica", "Corea del Sur"),
    ("g07", "Canada", "Bosnia"), ("g08", "Qatar", "Suiza"),
    ("g09", "Suiza", "Bosnia"), ("g10", "Canada", "Qatar"),
    ("g11", "Suiza", "Canada"), ("g12", "Bosnia", "Qatar"),
    ("g13", "Brasil", "Marruecos"), ("g14", "Haiti", "Escocia"),
    ("g15", "Escocia", "Marruecos"), ("g16", "Brasil", "Haiti"),
    ("g17", "Escocia", "Brasil"), ("g18", "Marruecos", "Haiti"),
    ("g19", "Estados Unidos", "Paraguay"), ("g20", "Australia", "Turquia"),
    ("g21", "Estados Unidos", "Australia"), ("g22", "Turquia", "Paraguay"),
    ("g23", "Turquia", "Estados Unidos"), ("g24", "Paraguay", "Australia"),
    ("g25", "Alemania", "Curazao"), ("g26", "Costa de Marfil", "Ecuador"),
    ("g27", "Alemania", "Costa de Marfil"), ("g28", "Ecuador", "Curazao"),
    ("g29", "Ecuador", "Alemania"), ("g30", "Curazao", "Costa de Marfil"),
    ("g31", "Paises Bajos", "Japon"), ("g32", "Suecia", "Tunisia"),
    ("g33", "Paises Bajos", "Suecia"), ("g34", "Tunisia", "Japon"),
    ("g35", "Japon", "Suecia"), ("g36", "Tunisia", "Paises Bajos"),
    ("g37", "Iran", "Nueva Zelanda"), ("g38", "Belgica", "Egipto"),
    ("g39", "Belgica", "Iran"), ("g40", "Nueva Zelanda", "Egipto"),
    ("g41", "Egipto", "Iran"), ("g42", "Nueva Zelanda", "Belgica"),
    ("g43", "Espana", "Cabo Verde"), ("g44", "Arabia Saudita", "Uruguay"),
    ("g45", "Espana", "Arabia Saudita"), ("g46", "Uruguay", "Cabo Verde"),
    ("g47", "Cabo Verde", "Arabia Saudita"), ("g48", "Uruguay", "Espana"),
    ("g49", "Francia", "Senegal"), ("g50", "Irak", "Noruega"),
    ("g51", "Francia", "Irak"), ("g52", "Noruega", "Senegal"),
    ("g53", "Noruega", "Francia"), ("g54", "Senegal", "Irak"),
    ("g55", "Argentina", "Argelia"), ("g56", "Austria", "Jordania"),
    ("g57", "Argentina", "Austria"), ("g58", "Jordania", "Argelia"),
    ("g59", "Argelia", "Austria"), ("g60", "Jordania", "Argentina"),
    ("g61", "Portugal", "R.D. Congo"), ("g62", "Uzbekistan", "Colombia"),
    ("g63", "Portugal", "Uzbekistan"), ("g64", "Colombia", "R.D. Congo"),
    ("g65", "Colombia", "Portugal"), ("g66", "R.D. Congo", "Uzbekistan"),
    ("g67", "Inglaterra", "Croacia"), ("g68", "Ghana", "Panama"),
    ("g69", "Inglaterra", "Ghana"), ("g70", "Panama", "Croacia"),
    ("g71", "Panama", "Inglaterra"), ("g72", "Croacia", "Ghana"),
]

# Equipo en espanol -> (codigo FIFA, [otros nombres aceptados]).
# Se usa para emparejar contra los nombres que devuelve la API.
TEAMS = {
    "Mexico": ("MEX", ["Mexico"]),
    "Sudafrica": ("RSA", ["South Africa"]),
    "Corea del Sur": ("KOR", ["Korea Republic", "South Korea", "Republic of Korea"]),
    "Chequia": ("CZE", ["Czechia", "Czech Republic"]),
    "Canada": ("CAN", ["Canada"]),
    "Bosnia": ("BIH", ["Bosnia and Herzegovina", "Bosnia-Herzegovina", "Bosnia Herzegovina"]),
    "Qatar": ("QAT", ["Qatar"]),
    "Suiza": ("SUI", ["Switzerland"]),
    "Brasil": ("BRA", ["Brazil"]),
    "Marruecos": ("MAR", ["Morocco"]),
    "Haiti": ("HAI", ["Haiti"]),
    "Escocia": ("SCO", ["Scotland"]),
    "Estados Unidos": ("USA", ["United States", "USA", "United States of America"]),
    "Paraguay": ("PAR", ["Paraguay"]),
    "Australia": ("AUS", ["Australia"]),
    "Turquia": ("TUR", ["Turkey", "Turkiye", "Turkey (Turkiye)"]),
    "Alemania": ("GER", ["Germany"]),
    "Curazao": ("CUW", ["Curacao"]),
    "Costa de Marfil": ("CIV", ["Ivory Coast", "Cote d'Ivoire", "Cote dIvoire"]),
    "Ecuador": ("ECU", ["Ecuador"]),
    "Paises Bajos": ("NED", ["Netherlands", "Holland"]),
    "Japon": ("JPN", ["Japan"]),
    "Suecia": ("SWE", ["Sweden"]),
    "Tunisia": ("TUN", ["Tunisia"]),
    "Iran": ("IRN", ["Iran", "IR Iran"]),
    "Nueva Zelanda": ("NZL", ["New Zealand"]),
    "Belgica": ("BEL", ["Belgium"]),
    "Egipto": ("EGY", ["Egypt"]),
    "Espana": ("ESP", ["Spain"]),
    "Cabo Verde": ("CPV", ["Cape Verde", "Cabo Verde Islands"]),
    "Arabia Saudita": ("KSA", ["Saudi Arabia"]),
    "Uruguay": ("URU", ["Uruguay"]),
    "Francia": ("FRA", ["France"]),
    "Senegal": ("SEN", ["Senegal"]),
    "Irak": ("IRQ", ["Iraq"]),
    "Noruega": ("NOR", ["Norway"]),
    "Argentina": ("ARG", ["Argentina"]),
    "Argelia": ("ALG", ["Algeria"]),
    "Austria": ("AUT", ["Austria"]),
    "Jordania": ("JOR", ["Jordan"]),
    "Portugal": ("POR", ["Portugal"]),
    "R.D. Congo": ("COD", ["DR Congo", "Congo DR", "Democratic Republic of Congo", "Congo"]),
    "Uzbekistan": ("UZB", ["Uzbekistan"]),
    "Colombia": ("COL", ["Colombia"]),
    "Inglaterra": ("ENG", ["England"]),
    "Croacia": ("CRO", ["Croatia"]),
    "Ghana": ("GHA", ["Ghana"]),
    "Panama": ("PAN", ["Panama"]),
}

# --------------------------------------------------------------------------
# Eliminatorias: cada partido de la quiniela y sus dos "lados".
#   ("G", pos, "A")  -> el equipo en la posicion `pos` del grupo A (1ro/2do)
#   ("W", "o01")     -> el ganador del partido o01 de la quiniela
#   ("3", [grupos])  -> un tercer lugar (no se ancla; se resuelve de rebote)
# Stage = etapa correspondiente en football-data.org.
# --------------------------------------------------------------------------
KO_ROUNDS = [
    ("LAST_32", [
        ("o01", ("G", 2, "A"), ("G", 2, "B")),
        ("o02", ("G", 1, "C"), ("G", 2, "F")),
        ("o03", ("G", 1, "E"), ("3", ["A", "B", "C", "D", "F"])),
        ("o04", ("G", 1, "F"), ("G", 2, "C")),
        ("o05", ("G", 2, "E"), ("G", 2, "I")),
        ("o06", ("G", 1, "I"), ("3", ["C", "D", "F", "G", "H"])),
        ("o07", ("G", 1, "A"), ("3", ["C", "E", "F", "H", "I"])),
        ("o08", ("G", 1, "L"), ("3", ["E", "H", "I", "J", "K"])),
        ("o09", ("G", 1, "G"), ("3", ["A", "E", "H", "I", "J"])),
        ("o10", ("G", 1, "D"), ("3", ["B", "E", "F", "I", "J"])),
        ("o11", ("G", 1, "H"), ("G", 2, "J")),
        ("o12", ("G", 2, "K"), ("G", 2, "L")),
        ("o13", ("G", 1, "B"), ("3", ["E", "F", "G", "I", "J"])),
        ("o14", ("G", 2, "D"), ("G", 2, "G")),
        ("o15", ("G", 1, "J"), ("G", 2, "H")),
        ("o16", ("G", 1, "K"), ("3", ["D", "E", "I", "J", "L"])),
    ]),
    ("LAST_16", [
        ("q01", ("W", "o01"), ("W", "o03")),
        ("q02", ("W", "o02"), ("W", "o05")),
        ("q03", ("W", "o04"), ("W", "o06")),
        ("q04", ("W", "o07"), ("W", "o08")),
        ("q05", ("W", "o11"), ("W", "o12")),
        ("q06", ("W", "o09"), ("W", "o10")),
        ("q07", ("W", "o14"), ("W", "o16")),
        ("q08", ("W", "o13"), ("W", "o15")),
    ]),
    ("QUARTER_FINALS", [
        ("s01", ("W", "q01"), ("W", "q02")),
        ("s02", ("W", "q03"), ("W", "q04")),
        ("s03", ("W", "q05"), ("W", "q06")),
        ("s04", ("W", "q07"), ("W", "q08")),
    ]),
    ("SEMI_FINALS", [
        ("f01", ("W", "s01"), ("W", "s02")),
        ("f02", ("W", "s03"), ("W", "s04")),
    ]),
    ("FINAL", [
        ("f03", ("W", "f01"), ("W", "f02")),
    ]),
]

DOUBLED = ("semifinal", "final")  # fases con puntos x2 (igual que la app)


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------
def log(msg):
    print(msg, flush=True)


def norm(s):
    """Normaliza un nombre: minusculas, sin acentos, solo alfanumerico."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return "".join(c for c in s.lower() if c.isalnum())


def es_keys(es_name):
    """Claves de identidad para un equipo de la quiniela (en espanol)."""
    tla, aliases = TEAMS[es_name]
    keys = {norm(es_name), norm(tla)}
    for a in aliases:
        keys.add(norm(a))
    return keys


def api_keys(team):
    """Claves de identidad para un equipo segun la API."""
    keys = set()
    for f in ("name", "shortName", "tla"):
        v = team.get(f)
        if v:
            keys.add(norm(v))
    return keys


def phase_of(mid):
    return {"g": "grupos", "o": "octavos", "q": "cuartos",
            "s": "semifinal", "f": "final"}[mid[0]]


def calc_points(pred, result, phase):
    """Misma logica de puntos que la app web."""
    try:
        ph, pa = int(pred["home"]), int(pred["away"])
        rh, ra = int(result["home"]), int(result["away"])
    except (KeyError, TypeError, ValueError):
        return 0
    mult = 2 if phase in DOUBLED else 1
    if ph == rh and pa == ra:
        return 3 * mult
    pw = "h" if ph > pa else "a" if ph < pa else "d"
    rw = "h" if rh > ra else "a" if rh < ra else "d"
    if pw == rw:
        return 2 * mult
    if ph == rh or pa == ra:
        return 1 * mult
    return 0


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
def api_get(path):
    req = urllib.request.Request(
        API_BASE + path, headers={"X-Auth-Token": TOKEN, "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def fb_get(path):
    url = FIREBASE_URL + "/" + path.lstrip("/") + ".json"
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def fb_patch(path, obj):
    """PATCH (update) sobre un nodo. Respeta DRY_RUN."""
    if DRY_RUN:
        log("  [PRUEBA] PATCH /%s  %s" % (path, json.dumps(obj, ensure_ascii=False)))
        return
    url = FIREBASE_URL + "/" + path.lstrip("/") + ".json"
    data = json.dumps(obj).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="PATCH",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()


# --------------------------------------------------------------------------
# Emparejado
# --------------------------------------------------------------------------
def fulltime(match):
    """Marcador final del partido (puede venir tras tiempo extra)."""
    ft = (match.get("score") or {}).get("fullTime") or {}
    return ft.get("home"), ft.get("away")


def find_api_match(matches, keys_a, keys_b=None):
    """Busca el partido de la API que contenga al equipo `keys_a`
    (y opcionalmente al `keys_b`)."""
    for m in matches:
        hk, ak = api_keys(m["homeTeam"]), api_keys(m["awayTeam"])
        sides = [hk, ak]
        has_a = any(keys_a & s for s in sides)
        if not has_a:
            continue
        if keys_b is None or any(keys_b & s for s in sides):
            return m
    return None


def process_groups(matches):
    """Empareja los partidos de grupos terminados.
    Devuelve ({id_quiniela: {home,away}}, set con los id() de la API usados)."""
    results = {}
    group_matches = [m for m in matches if (m.get("stage") == "GROUP_STAGE")]
    used = set()
    for mid, home_es, away_es in GROUP_FIXTURE:
        kh, ka = es_keys(home_es), es_keys(away_es)
        m = None
        for cand in group_matches:
            if id(cand) in used:
                continue
            hk, ak = api_keys(cand["homeTeam"]), api_keys(cand["awayTeam"])
            if (kh & hk and ka & ak) or (kh & ak and ka & hk):
                m = cand
                break
        if not m:
            continue
        h, a = fulltime(m)
        if h is None or a is None:
            continue
        used.add(id(m))
        hk = api_keys(m["homeTeam"])
        if kh & hk:          # la API tiene a nuestro local como local
            results[mid] = {"home": int(h), "away": int(a)}
        else:                # vienen invertidos -> giramos el marcador
            results[mid] = {"home": int(a), "away": int(h)}
    return results, used


def build_standings():
    """Devuelve {(grupo, posicion): keys_equipo} a partir de la tabla."""
    pos = {}
    try:
        data = api_get("/competitions/%s/standings" % COMPETITION)
    except Exception as e:
        log("  No se pudo leer la tabla de posiciones: %s" % e)
        return pos
    for st in data.get("standings", []):
        if st.get("type") not in (None, "TOTAL"):
            continue
        grp = (st.get("group") or "")
        letter = grp.replace("GROUP_", "").replace("Group ", "").strip().upper()[:1]
        if not letter:
            continue
        for row in st.get("table", []):
            pos[(letter, row.get("position"))] = api_keys(row["team"])
    return pos


def process_knockouts(all_matches):
    """Resuelve y empareja eliminatorias.
    Devuelve ({id_quiniela: {home,away}}, set con los id() de la API usados)."""
    results = {}
    used = set()
    resolved = {}  # slot -> {"home": keys, "away": keys, "winner": keys}
    standings = build_standings()
    if not standings:
        log("  Sin tabla de posiciones todavia: eliminatorias se omiten por ahora.")
        return results, used

    def resolve_side(side):
        kind = side[0]
        if kind == "G":
            return standings.get((side[2], side[1]))
        if kind == "W":
            r = resolved.get(side[1])
            return r["winner"] if r else None
        return None  # "3" (tercer lugar): no se ancla

    for stage, slots in KO_ROUNDS:
        stage_matches = [m for m in all_matches if m.get("stage") == stage]
        for mid, side_h, side_a in slots:
            kh = resolve_side(side_h)
            ka = resolve_side(side_a)
            anchor = kh or ka
            if not anchor:
                continue
            other = ka if anchor is kh else kh
            m = find_api_match(stage_matches, anchor, other)
            if not m:
                continue
            h, a = fulltime(m)
            if h is None or a is None:
                continue
            used.add(id(m))
            hk = api_keys(m["homeTeam"])
            ak = api_keys(m["awayTeam"])
            # Orientar el marcador al "local" de la quiniela.
            home_is_api_home = bool(kh & hk) if kh else not bool(ka & hk)
            if home_is_api_home:
                results[mid] = {"home": int(h), "away": int(a)}
                home_keys, away_keys = hk, ak
            else:
                results[mid] = {"home": int(a), "away": int(h)}
                home_keys, away_keys = ak, hk
            # Ganador (para propagar a la siguiente ronda).
            wlabel = (m.get("score") or {}).get("winner")
            if wlabel == "HOME_TEAM":
                winner = hk
            elif wlabel == "AWAY_TEAM":
                winner = ak
            else:
                winner = hk if int(h) > int(a) else ak if int(a) > int(h) else hk
            resolved[mid] = {"home": home_keys, "away": away_keys, "winner": winner}
    return results, used


# --------------------------------------------------------------------------
# Recalculo de puntos (igual que recalcPoints de la app)
# --------------------------------------------------------------------------
def recalc_points(results):
    preds = fb_get("predictions") or {}
    users = fb_get("users") or {}
    updates = {}
    for uname in users:
        total = 0
        upred = preds.get(uname) or {}
        for mid, res in results.items():
            pred = upred.get(mid)
            if not pred:
                continue
            total += calc_points(pred, res, phase_of(mid))
        updates["%s/points" % uname] = total
    return updates


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main():
    if not TOKEN:
        log("FOOTBALL_DATA_TOKEN no esta configurado. No hay nada que hacer "
            "(esto es normal hasta que agregues el secreto en GitHub). Saliendo.")
        return 0

    log("== Actualizador de resultados ASeguros ==")
    log("Modo: %s" % ("PRUEBA (no escribe)" if DRY_RUN else "EN VIVO"))

    try:
        data = api_get("/competitions/%s/matches?status=FINISHED" % COMPETITION)
    except urllib.error.HTTPError as e:
        log("Error al consultar football-data.org (HTTP %s). Revisa el token "
            "o el codigo de competencia COMPETITION." % e.code)
        return 1
    except Exception as e:
        log("Error al consultar football-data.org: %s" % e)
        return 1

    matches = data.get("matches", [])
    log("Partidos terminados segun la API: %d" % len(matches))

    group_results, used_g = process_groups(matches)
    log("Partidos de grupos emparejados: %d" % len(group_results))

    ko_results, used_k = process_knockouts(matches)
    log("Partidos de eliminatorias emparejados: %d" % len(ko_results))

    # Avisar de partidos terminados que NO logramos emparejar (para no perderlos
    # en silencio: casi siempre es un nombre de equipo que falta en el mapa TEAMS).
    used_ids = used_g | used_k
    unmatched = [m for m in matches if id(m) not in used_ids]
    if unmatched:
        log("AVISO: %d partido(s) terminado(s) sin emparejar (revisar nombres):"
            % len(unmatched))
        for m in unmatched:
            hn = (m.get("homeTeam") or {}).get("name", "?")
            an = (m.get("awayTeam") or {}).get("name", "?")
            log("   - %s vs %s [%s]" % (hn, an, m.get("stage")))

    all_results = {}
    all_results.update(group_results)
    all_results.update(ko_results)

    if not all_results:
        log("No hay resultados nuevos para escribir. Listo.")
        return 0

    # 1) Escribir los marcadores reales.
    log("Escribiendo %d resultado(s) en Firebase..." % len(all_results))
    fb_patch("results", all_results)

    # 2) Recalcular puntos de todos los jugadores (sobre TODOS los resultados,
    #    los de antes mas los nuevos).
    full_results = fb_get("results") or {}
    full_results.update(all_results)
    point_updates = recalc_points(full_results)
    log("Recalculando puntos de %d jugador(es)..." % len(point_updates))
    fb_patch("users", point_updates)

    log("Listo. %s" % ("(modo prueba, no se escribio nada)" if DRY_RUN else "Resultados y puntos actualizados."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
