# services/injuries.py - VERSÃO COMPLETA CORRIGIDA

import requests
import pandas as pd
from services.calendar import calendario_df_espn

INJURY_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"

# ✅ MAPEAMENTO COMPLETO ESPN NAMES → ABREVIAÇÕES INTERNAS
ESPN_NAME_TO_ABBR = {
    "Atlanta Hawks": "ATL",
    "Boston Celtics": "BOS",
    "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA",
    "Chicago Bulls": "CHI",
    "Cleveland Cavaliers": "CLE",
    "Dallas Mavericks": "DAL",
    "Denver Nuggets": "DEN",
    "Detroit Pistons": "DET",
    "Golden State Warriors": "GSW",  # ✅ GSW (não GS)
    "Houston Rockets": "HOU",
    "Indiana Pacers": "IND",
    "LA Clippers": "LAC",
    "Los Angeles Lakers": "LAL",
    "Memphis Grizzlies": "MEM",
    "Miami Heat": "MIA",
    "Milwaukee Bucks": "MIL",
    "Minnesota Timberwolves": "MIN",
    "New Orleans Pelicans": "NOP",  # ✅ NOP (não NO)
    "New York Knicks": "NYK",       # ✅ NYK (não NY)
    "Oklahoma City Thunder": "OKC",
    "Orlando Magic": "ORL",
    "Philadelphia 76ers": "PHI",
    "Phoenix Suns": "PHX",
    "Portland Trail Blazers": "POR",
    "Sacramento Kings": "SAC",
    "San Antonio Spurs": "SAS",     # ✅ SAS (não SA)
    "Toronto Raptors": "TOR",
    "Utah Jazz": "UTA",             # ✅ UTA (não UTAH)
    "Washington Wizards": "WAS"     # ✅ WAS (não WSH)
}


def _fetch_all_injuries():
    """
    Busca todas as lesões da NBA.
    Usa displayName em vez de ID porque os IDs da ESPN são inconsistentes.
    
    ✅ CORRIGIDO: Normaliza abreviações
    """
    try:
        resp = requests.get(INJURY_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        rows = []
        
        for team_bloc in (data.get("injuries") or []):
            # Usar displayName em vez de ID
            team_name = team_bloc.get("displayName", "")
            team_abbr = ESPN_NAME_TO_ABBR.get(team_name, team_name)
            
            # Se não encontrar no mapa, tentar match parcial
            if team_abbr == team_name:
                # Buscar match parcial (ex: "Los Angeles Clippers" contém "Clippers")
                for full_name, abbr in ESPN_NAME_TO_ABBR.items():
                    if full_name.lower() in team_name.lower() or team_name.lower() in full_name.lower():
                        team_abbr = abbr
                        break
            
            # Lesões desta equipa
            team_injuries = team_bloc.get("injuries", [])
            
            for injury in team_injuries:
                athlete_data = injury.get("athlete", {})
                player_name = athlete_data.get("displayName", "Unknown")
                status = injury.get("status", "Unknown")
                detail = injury.get("shortComment", "") or injury.get("longComment", "")
                
                rows.append({
                    "team_abbr": team_abbr,
                    "player": player_name,
                    "status": status,
                    "injury": detail
                })
        
        return rows
    
    except Exception as e:
        print(f"⚠️ Erro ao buscar lesões: {e}")
        return []


def injuries_por_jogo(data: str) -> pd.DataFrame:
    """
    Dada uma data (YYYY-MM-DD), retorna lesões das equipas que jogam nesse dia.
    Colunas: team_abbr, player, status, injury
    
    ✅ CORRIGIDO: Usa abreviações normalizadas
    """
    # Buscar jogos do dia (já retorna abreviações normalizadas)
    jogos = calendario_df_espn(data)
    if jogos is None or jogos.empty:
        return pd.DataFrame(columns=["team_abbr", "player", "status", "injury"])
    
    # Equipas que jogam hoje (já estão normalizadas)
    equipas_hoje = set(jogos["home"].tolist() + jogos["away"].tolist())
    
    # Buscar todas as lesões (já retorna abreviações normalizadas)
    all_injuries = _fetch_all_injuries()
    
    if not all_injuries:
        return pd.DataFrame(columns=["team_abbr", "player", "status", "injury"])
    
    # Filtrar apenas equipas que jogam hoje
    injuries_hoje = [
        inj for inj in all_injuries 
        if inj["team_abbr"] in equipas_hoje
    ]
    
    return pd.DataFrame(injuries_hoje, columns=["team_abbr", "player", "status", "injury"])


def get_all_injuries_df() -> pd.DataFrame:
    """
    Retorna DataFrame com TODAS as lesões da NBA (todas as equipas).
    Útil para debug e análises gerais.
    
    ✅ CORRIGIDO: Usa abreviações normalizadas
    """
    injuries = _fetch_all_injuries()
    if not injuries:
        return pd.DataFrame(columns=["team_abbr", "player", "status", "injury"])
    return pd.DataFrame(injuries, columns=["team_abbr", "player", "status", "injury"])