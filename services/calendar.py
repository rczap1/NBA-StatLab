# services/calendar.py - VERSÃO COMPLETA CORRIGIDA

import requests
import pytz
from datetime import datetime
import pandas as pd

# ✅ MAPEAMENTO ESPN → SISTEMA INTERNO
ESPN_TO_INTERNAL_ABBR = {
    # Equipas com abreviações diferentes
    "SA": "SAS",   # San Antonio Spurs
    "GS": "GSW",   # Golden State Warriors
    "NO": "NOP",   # New Orleans Pelicans
    "NY": "NYK",   # New York Knicks
    "UTAH": "UTA", # Utah Jazz
    "WSH": "WAS",  # Washington Wizards
    
    # Todas as outras (manter igual)
    "ATL": "ATL", "BOS": "BOS", "BKN": "BKN", "CHA": "CHA",
    "CHI": "CHI", "CLE": "CLE", "DAL": "DAL", "DEN": "DEN",
    "DET": "DET", "HOU": "HOU", "IND": "IND", "LAC": "LAC",
    "LAL": "LAL", "MEM": "MEM", "MIA": "MIA", "MIL": "MIL",
    "MIN": "MIN", "NYK": "NYK", "OKC": "OKC", "ORL": "ORL",
    "PHI": "PHI", "PHX": "PHX", "POR": "POR", "SAC": "SAC",
    "SAS": "SAS", "TOR": "TOR", "UTA": "UTA", "WAS": "WAS",
    "GSW": "GSW", "NOP": "NOP"
}

def _normalize_abbr(espn_abbr: str) -> str:
    """
    Normaliza abreviação da ESPN para o formato interno.
    
    Args:
        espn_abbr: Abreviação da ESPN (ex: 'SA', 'GS', 'WSH')
    
    Returns:
        Abreviação interna (ex: 'SAS', 'GSW', 'WAS)
    """
    return ESPN_TO_INTERNAL_ABBR.get(espn_abbr, espn_abbr)


def get_jogos_do_dia(data: str):
    """
    Retorna lista de jogos para o dia dado no formato YYYY-MM-DD.
    Cada jogo é um dict { "home": abreviação_casa, "away": abreviação_visitante }.
    
    ✅ CORRIGIDO: Normaliza abreviações ESPN
    """
    date_param = data.replace("-", "")
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={date_param}"
    resp = requests.get(url)
    resp.raise_for_status()
    data_json = resp.json()
    events = data_json.get("events", [])
    jogos = []
    
    for ev in events:
        comps = ev.get("competitions", [])
        if not comps:
            continue
        comp = comps[0]
        
        home = comp["competitors"][0] if comp["competitors"][0]["homeAway"] == "home" else comp["competitors"][1]
        visitor = comp["competitors"][1] if comp["competitors"][1]["homeAway"] == "away" else comp["competitors"][0]
        
        home_abbr = home.get("team", {}).get("abbreviation", "")
        visitor_abbr = visitor.get("team", {}).get("abbreviation", "")
        
        # ✅ NORMALIZAR ABREVIAÇÕES
        home_abbr = _normalize_abbr(home_abbr)
        visitor_abbr = _normalize_abbr(visitor_abbr)
        
        jogos.append({"home": home_abbr, "away": visitor_abbr})
    
    return jogos


def ver_calendario_espn(data: str):
    """
    Mostra calendário da NBA para a data dada no formato YYYY-MM-DD.
    
    ✅ CORRIGIDO: Normaliza abreviações
    """
    date_param = data.replace("-", "")
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={date_param}"
    resp = requests.get(url)
    resp.raise_for_status()
    data_json = resp.json()
    events = data_json.get("events", [])

    from rich.table import Table
    from rich.console import Console
    console = Console()
    lisbon = pytz.timezone('Europe/Lisbon')

    table = Table(title=f"Calendário de Jogos — {data}")
    table.add_column("Casa", justify="center")
    table.add_column("Visitante", justify="center")
    table.add_column("Horário PT 🇵🇹", justify="center")
    table.add_column("Estado", justify="center")
    table.add_column("Resultado", justify="center")
    table.add_column("Arena", justify="left")

    for ev in events:
        comps = ev.get("competitions", [])
        if not comps:
            continue
        comp = comps[0]
        
        home = comp["competitors"][0] if comp["competitors"][0]["homeAway"] == "home" else comp["competitors"][1]
        visitor = comp["competitors"][1] if comp["competitors"][1]["homeAway"] == "away" else comp["competitors"][0]
        
        home_abbr = home.get("team", {}).get("abbreviation", "")
        visitor_abbr = visitor.get("team", {}).get("abbreviation", "")
        
        # ✅ NORMALIZAR ABREVIAÇÕES
        home_abbr = _normalize_abbr(home_abbr)
        visitor_abbr = _normalize_abbr(visitor_abbr)

        # hora do jogo
        start_time = ev.get("date", "")
        horario_pt = "-"
        if start_time:
            try:
                dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                dt_ls = dt.astimezone(lisbon)
                horario_pt = dt_ls.strftime("%H:%M")
            except Exception:
                horario_pt = start_time

        status = comp.get("status", {}).get("type", {}).get("description", "")
        home_score = home.get("score")
        visitor_score = visitor.get("score")
        
        if status.lower() in ["scheduled", "upcoming", "pre-game"] or home_score is None or visitor_score is None:
            resultado = "Ainda não começou"
        else:
            resultado = f"{home_score}-{visitor_score}"

        arena = comp.get("venue", {}).get("fullName", "")

        table.add_row(home_abbr, visitor_abbr, horario_pt, status, resultado, arena)

    console.print(table)


def calendario_df_espn(data: str) -> pd.DataFrame:
    """
    Retorna DataFrame com jogos do dia.
    
    ✅ CORRIGIDO: Normaliza abreviações
    """
    date_param = data.replace("-", "")
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={date_param}"
    resp = requests.get(url)
    resp.raise_for_status()
    data_json = resp.json()

    rows = []
    for ev in data_json.get("events", []):
        comp = (ev.get("competitions") or [{}])[0]
        teams = comp.get("competitors") or []
        if len(teams) != 2:
            continue
        
        home = next(t for t in teams if t.get("homeAway") == "home")
        away = next(t for t in teams if t.get("homeAway") == "away")
        
        home_abbr = home.get("team", {}).get("abbreviation", "")
        away_abbr = away.get("team", {}).get("abbreviation", "")
        
        # ✅ NORMALIZAR ABREVIAÇÕES
        home_abbr = _normalize_abbr(home_abbr)
        away_abbr = _normalize_abbr(away_abbr)

        rows.append({
            "date": data,
            "start_iso": ev.get("date"),
            "home": home_abbr,
            "away": away_abbr,
            "home_score": int(home.get("score")) if home.get("score") is not None else None,
            "away_score": int(away.get("score")) if away.get("score") is not None else None,
            "status": comp.get("status", {}).get("type", {}).get("description", ""),
            "venue": comp.get("venue", {}).get("fullName", "")
        })
    
    return pd.DataFrame(rows)