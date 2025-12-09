# services/predictions.py - CORREÇÃO COMPLETA B2B
"""
Sistema completo de análise de jogos NBA.
Integra: Elo, MOV, Rest, Injuries (com tiers dinâmicos)

✅ CORRIGIDO: Detecção de back-to-back melhorada
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Tuple, Optional, List
import pandas as pd
from datetime import datetime, timedelta
from services.calendar import calendario_df_espn
import math
from rich.console import Console

console = Console()

# --------------------
# Configuração base
# --------------------
ELO_START = 1500.0

# K-Factor dinâmico
K_EARLY_SEASON = 30.0
K_MID_SEASON = 20.0
K_LATE_SEASON = 15.0

HOME_COURT_BONUS = 60.0

# Ajustes
BACK_TO_BACK_PENALTY = -50.0
REST_ADVANTAGE = 25.0
TRAVEL_FATIGUE = -15.0

# Regressão à média
REGRESSION_FACTOR = 1/3
REGRESSION_MONTH = 10

RATINGS_PATH = Path("data/elo_ratings.json")
SCHEDULE_CACHE_PATH = Path("data/schedule_cache.json")
REGRESSION_HISTORY_PATH = Path("data/regression_history.json")
CHECKPOINT_PATH = Path("data/elo_checkpoint.json")


# --------------------
# Checkpoint System
# --------------------
def _load_checkpoint() -> Optional[str]:
    """Carrega a última data processada."""
    if CHECKPOINT_PATH.exists():
        try:
            data = json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
            return data.get("last_processed_date")
        except Exception:
            return None
    return None

def _save_checkpoint(date: str) -> None:
    """Guarda checkpoint com data processada."""
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    checkpoint = {
        "last_processed_date": date,
        "updated_at": datetime.now().isoformat()
    }
    CHECKPOINT_PATH.write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")


# --------------------
# Regressão à Média
# --------------------
def _load_regression_history() -> Dict[str, str]:
    """Carrega histórico de quando cada equipa foi regredida pela última vez."""
    REGRESSION_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if REGRESSION_HISTORY_PATH.exists():
        return json.loads(REGRESSION_HISTORY_PATH.read_text(encoding="utf-8"))
    return {}

def _save_regression_history(history: Dict[str, str]) -> None:
    """Guarda histórico de regressões."""
    REGRESSION_HISTORY_PATH.write_text(json.dumps(history, indent=2), encoding="utf-8")

def apply_regression_to_mean(ratings: Dict[str, float], current_date: str) -> Dict[str, float]:
    """
    Aplica regressão à média se estamos em início de nova época (Outubro).
    """
    try:
        dt = datetime.strptime(current_date, "%Y-%m-%d").date()
        
        # Só aplicar regressão em Outubro
        if dt.month != REGRESSION_MONTH:
            return ratings
        
        # Verificar se já aplicámos regressão este ano
        regression_history = _load_regression_history()
        current_year = dt.year
        last_regression_key = f"last_regression_{current_year}"
        
        if regression_history.get(last_regression_key):
            return ratings
        
        # Aplicar regressão
        regressed_ratings = {}
        regression_count = 0
        total_change = 0.0
        
        for team, elo in ratings.items():
            distance_from_mean = elo - ELO_START
            regression_amount = distance_from_mean * REGRESSION_FACTOR
            new_elo = elo - regression_amount
            
            regressed_ratings[team] = new_elo
            regression_count += 1
            total_change += abs(regression_amount)
        
        # Guardar que aplicámos regressão este ano
        regression_history[last_regression_key] = current_date
        _save_regression_history(regression_history)
        
        avg_change = total_change / regression_count if regression_count > 0 else 0
        
        console.print(f"[dim]REGRESSÃO aplicada em {current_date}: {regression_count} equipas, mudança média {avg_change:.1f} pontos[/dim]")
        
        return regressed_ratings
        
    except Exception as e:
        console.print(f"[yellow]Aviso: Erro na regressão ({e})[/yellow]")
        return ratings


# --------------------
# K-Factor Dinâmico
# --------------------
def get_k_factor(game_date: str) -> float:
    try:
        dt = datetime.strptime(game_date, "%Y-%m-%d").date()
        month = dt.month
        
        if 10 <= month <= 12:
            return K_EARLY_SEASON
        elif 1 <= month <= 3:
            return K_MID_SEASON
        elif 4 <= month <= 6:
            return K_LATE_SEASON
        else:
            return K_MID_SEASON
    except Exception:
        return K_MID_SEASON


# --------------------
# Utilitários básicos
# --------------------
def _load_ratings() -> Dict[str, float]:
    RATINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if RATINGS_PATH.exists():
        return json.loads(RATINGS_PATH.read_text(encoding="utf-8"))
    return {}

def _save_ratings(ratings: Dict[str, float]) -> None:
    RATINGS_PATH.write_text(json.dumps(ratings, indent=2), encoding="utf-8")

def get_team_elo(ratings: Dict[str, float], abbr: str) -> float:
    if abbr not in ratings:
        ratings[abbr] = ELO_START
    return ratings[abbr]


# --------------------
# Schedule Cache
# --------------------
def _load_schedule_cache() -> Dict[str, str]:
    SCHEDULE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SCHEDULE_CACHE_PATH.exists():
        return json.loads(SCHEDULE_CACHE_PATH.read_text(encoding="utf-8"))
    return {}

def _save_schedule_cache(cache: Dict[str, str]) -> None:
    SCHEDULE_CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")

def _update_schedule_cache(team_abbr: str, game_date: str) -> None:
    cache = _load_schedule_cache()
    cache[team_abbr] = game_date
    _save_schedule_cache(cache)

def _days_since_last_game(team_abbr: str, current_date: str) -> Optional[int]:
    cache = _load_schedule_cache()
    last_game = cache.get(team_abbr)
    
    if not last_game:
        return None
    
    try:
        last_dt = datetime.strptime(last_game, "%Y-%m-%d").date()
        curr_dt = datetime.strptime(current_date, "%Y-%m-%d").date()
        return (curr_dt - last_dt).days
    except Exception:
        return None


# --------------------
# Injury Impact
# --------------------
def get_injury_adjustment(team_abbr: str, game_date: str, season: str = "2025-26") -> Tuple[float, List[Tuple[str, int]]]:
    """
    Calcula ajuste de lesões baseado em TIERS DINÂMICOS.
    """
    try:
        from services.injuries import injuries_por_jogo
        from services.player_tiers import get_player_elo_impact
        import unicodedata
        
        injuries_df = injuries_por_jogo(game_date)
        
        if injuries_df.empty:
            return 0.0, []
        
        team_injuries = injuries_df[injuries_df["team_abbr"] == team_abbr]
        
        if team_injuries.empty:
            return 0.0, []
        
        adjustment = 0.0
        injured_players_detail = []
        
        for _, inj in team_injuries.iterrows():
            status = (inj.get("status") or "").lower()
            player = inj.get("player", "")
            
            # Normalizar nome
            player_normalized = unicodedata.normalize('NFKD', player).encode('ASCII', 'ignore').decode('ASCII')
            player_normalized = ' '.join(player_normalized.split())
            
            # Apenas contar "Out" como ausência confirmada
            if status in ["out", "out for season", "out indefinitely"]:
                player_impact = get_player_elo_impact(player_normalized, season, silent=True)
                
                adjustment += player_impact
                injured_players_detail.append((player_normalized, player_impact))
        
        # Ordenar por impacto (mais grave primeiro)
        injured_players_detail.sort(key=lambda x: x[1])
        
        return adjustment, injured_players_detail
    
    except Exception as e:
        console.print(f"[dim]Aviso: Erro ao calcular injury adjustment ({e})[/dim]")
        return 0.0, []


# --------------------
# Rest Adjustments
# --------------------
def calculate_rest_adjustment(home_abbr: str, away_abbr: str, game_date: str) -> Tuple[float, float]:
    """
    ✅ CORRIGIDO: Adiciona logging para debug de B2B
    """
    home_days = _days_since_last_game(home_abbr, game_date)
    away_days = _days_since_last_game(away_abbr, game_date)
    
    home_adj = 0.0
    away_adj = 0.0
    
    if home_days == 1:
        home_adj += BACK_TO_BACK_PENALTY
    if away_days == 1:
        away_adj += BACK_TO_BACK_PENALTY
    
    if home_days and away_days:
        if home_days >= 3 and away_days < 3:
            home_adj += REST_ADVANTAGE
        elif away_days >= 3 and home_days < 3:
            away_adj += REST_ADVANTAGE
    
    return home_adj, away_adj


# --------------------
# MOV Multiplier
# --------------------
def mov_multiplier(point_diff: int, elo_diff: float) -> float:
    mov_factor = math.log(abs(point_diff) + 1)
    surprise_factor = 2.2 / ((elo_diff * 0.001) + 2.2)
    return mov_factor * surprise_factor


# --------------------
# Fórmulas Elo
# --------------------
def expected_prob(elo_home: float, elo_away: float, 
                 home_bonus: float = HOME_COURT_BONUS,
                 home_rest_adj: float = 0.0,
                 away_rest_adj: float = 0.0,
                 home_injury_adj: float = 0.0,
                 away_injury_adj: float = 0.0) -> float:
    elo_home_adj = elo_home + home_bonus + home_rest_adj + home_injury_adj
    elo_away_adj = elo_away + away_rest_adj + away_injury_adj
    
    diff = elo_home_adj - elo_away_adj
    return 1.0 / (1.0 + 10 ** (-(diff) / 400.0))

def update_elo(elo_winner: float, elo_loser: float, point_diff: int, game_date: str) -> Tuple[float, float]:
    elo_diff = elo_winner - elo_loser
    exp_win = 1.0 / (1.0 + 10 ** (-elo_diff / 400.0))
    mov_mult = mov_multiplier(point_diff, elo_diff)
    
    k_base = get_k_factor(game_date)
    k_effective = k_base * mov_mult
    
    delta = k_effective * (1.0 - exp_win)
    return elo_winner + delta, elo_loser - delta


# --------------------
# Determinar Season Automaticamente
# --------------------
def _get_season_from_date(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    
    if dt.month >= 10:
        season_start = dt.year
    else:
        season_start = dt.year - 1
    
    season_end = str(season_start + 1)[-2:]
    
    return f"{season_start}-{season_end}"


# --------------------
# API pública
# --------------------
def previsao_jogo(home_abbr: str, away_abbr: str, game_date: str, season: Optional[str] = None) -> Dict:
    if season is None:
        season = _get_season_from_date(game_date)
    
    ratings = _load_ratings()
    eh = get_team_elo(ratings, home_abbr)
    ea = get_team_elo(ratings, away_abbr)
    
    home_rest_adj, away_rest_adj = calculate_rest_adjustment(home_abbr, away_abbr, game_date)
    home_injury_adj, home_injured = get_injury_adjustment(home_abbr, game_date, season)
    away_injury_adj, away_injured = get_injury_adjustment(away_abbr, game_date, season)
    
    p_home = expected_prob(eh, ea, 
                          home_rest_adj=home_rest_adj,
                          away_rest_adj=away_rest_adj,
                          home_injury_adj=home_injury_adj,
                          away_injury_adj=away_injury_adj)
    pred = home_abbr if p_home >= 0.5 else away_abbr
    
    k_factor = get_k_factor(game_date)
    
    return {
        "home": home_abbr,
        "away": away_abbr,
        "prob_home": round(p_home, 3),
        "predicted_winner": pred,
        "home_rest_adj": round(home_rest_adj, 1),
        "away_rest_adj": round(away_rest_adj, 1),
        "home_injury_adj": round(home_injury_adj, 1),
        "away_injury_adj": round(away_injury_adj, 1),
        "home_injured_detail": home_injured,
        "away_injured_detail": away_injured,
        "k_factor": k_factor
    }

def aplicar_resultado_final(home_abbr: str, away_abbr: str, 
                           home_score: int, away_score: int,
                           game_date: str) -> None:
    ratings = _load_ratings()
    eh = get_team_elo(ratings, home_abbr)
    ea = get_team_elo(ratings, away_abbr)

    point_diff = abs(home_score - away_score)
    
    if home_score > away_score:
        eh_new, ea_new = update_elo(eh, ea, point_diff, game_date)
    else:
        ea_new, eh_new = update_elo(ea, eh, point_diff, game_date)

    ratings[home_abbr] = eh_new
    ratings[away_abbr] = ea_new
    _save_ratings(ratings)
    
    _update_schedule_cache(home_abbr, game_date)
    _update_schedule_cache(away_abbr, game_date)


def prever_vencedor_para_data(jogos_df: pd.DataFrame, season: Optional[str] = None) -> pd.DataFrame:
    """
    ✅ CORRIGIDO: Atualiza schedule_cache com jogos de ONTEM antes de calcular
    """
    if jogos_df is None or jogos_df.empty:
        return jogos_df

    # Auto-determinar season
    if season is None and "date" in jogos_df.columns and not jogos_df.empty:
        season = _get_season_from_date(jogos_df.iloc[0]["date"])

    out = jogos_df.copy()
    ratings = _load_ratings()
    
    # ✅ CRÍTICO: Garantir que schedule_cache tem dados de ONTEM
    game_date = jogos_df.iloc[0]["date"]
    yesterday = (datetime.strptime(game_date, "%Y-%m-%d") - timedelta(days=1)).date().isoformat()
    
    try:
        jogos_ontem = calendario_df_espn(yesterday)
        
        if not jogos_ontem.empty:
            # Atualizar cache para equipas que jogaram ontem
            for _, jogo in jogos_ontem.iterrows():
                _update_schedule_cache(jogo["home"], yesterday)
                _update_schedule_cache(jogo["away"], yesterday)
    except Exception:
        pass  # Silenciar erros (dia sem jogos, etc)

    probs_home = []
    probs_away = []
    vencedores = []
    elo_home_list = []
    elo_away_list = []
    home_rest_list = []
    away_rest_list = []
    home_injury_list = []
    away_injury_list = []
    home_days_list = []
    away_days_list = []
    home_injured_stars_list = []
    away_injured_stars_list = []
    k_factors = []

    for _, r in out.iterrows():
        game_date_row = r["date"]
        home = r["home"]
        away = r["away"]
        
        eh = get_team_elo(ratings, home)
        ea = get_team_elo(ratings, away)
        
        home_rest_adj, away_rest_adj = calculate_rest_adjustment(home, away, game_date_row)
        home_days = _days_since_last_game(home, game_date_row)
        away_days = _days_since_last_game(away, game_date_row)
        
        home_injury_adj, home_injured = get_injury_adjustment(home, game_date_row, season)
        away_injury_adj, away_injured = get_injury_adjustment(away, game_date_row, season)
        
        p_home = expected_prob(eh, ea,
                              home_rest_adj=home_rest_adj,
                              away_rest_adj=away_rest_adj,
                              home_injury_adj=home_injury_adj,
                              away_injury_adj=away_injury_adj)
        p_away = 1 - p_home
        
        k_factor = get_k_factor(game_date_row)

        probs_home.append(p_home)
        probs_away.append(p_away)
        vencedores.append(home if p_home >= 0.5 else away)
        elo_home_list.append(round(eh, 1))
        elo_away_list.append(round(ea, 1))
        home_rest_list.append(round(home_rest_adj, 1))
        away_rest_list.append(round(away_rest_adj, 1))
        home_injury_list.append(round(home_injury_adj, 1))
        away_injury_list.append(round(away_injury_adj, 1))
        home_days_list.append(home_days if home_days else "-")
        away_days_list.append(away_days if away_days else "-")
        home_injured_stars_list.append(home_injured if home_injured else "-")
        away_injured_stars_list.append(away_injured if away_injured else "-")
        k_factors.append(k_factor)

    out["prob_home"] = probs_home
    out["prob_away"] = probs_away
    out["vencedor_previsto"] = vencedores
    out["elo_home"] = elo_home_list
    out["elo_away"] = elo_away_list
    out["home_rest_adj"] = home_rest_list
    out["away_rest_adj"] = away_rest_list
    out["home_injury_adj"] = home_injury_list
    out["away_injury_adj"] = away_injury_list
    out["home_days_rest"] = home_days_list
    out["away_days_rest"] = away_days_list
    out["home_injured_detail"] = home_injured_stars_list
    out["away_injured_detail"] = away_injured_stars_list
    out["k_factor"] = k_factors
    
    return out


# --------------------
# Histórico Elo
# --------------------
def _parse_resultado(row) -> Tuple[bool | None, int | None]:
    status = (row.get("status") or "").lower()
    hs = row.get("home_score")
    as_ = row.get("away_score")
    
    if ("final" in status) or (hs is not None and as_ is not None):
        try:
            home_score = int(hs)
            away_score = int(as_)
            return (home_score > away_score, abs(home_score - away_score))
        except Exception:
            return (None, None)
    return (None, None)

def atualizar_elos_historico(inicio: str, fim: str, force_full: bool = False) -> None:
    """
    Atualiza ratings Elo com K-factor dinâmico e regressão à média.
    """
    # Carregar checkpoint
    last_checkpoint = None if force_full else _load_checkpoint()
    
    if last_checkpoint and not force_full:
        checkpoint_date = datetime.strptime(last_checkpoint, "%Y-%m-%d").date()
        inicio_date = datetime.strptime(inicio, "%Y-%m-%d").date()
        fim_date = datetime.strptime(fim, "%Y-%m-%d").date()
        
        if checkpoint_date >= fim_date:
            console.print(f"[green]✓ Elo já atualizado até {last_checkpoint}[/green]")
            return
        
        dt_ini = checkpoint_date + timedelta(days=1)
        console.print(f"[cyan]📌 Checkpoint encontrado: {last_checkpoint}[/cyan]")
        console.print(f"[cyan]⚡ Processando apenas de {dt_ini} até {fim}[/cyan]")
    else:
        dt_ini = datetime.strptime(inicio, "%Y-%m-%d").date()
        if force_full:
            console.print(f"[yellow]🔄 Recalculando tudo (force_full=True)[/yellow]")
            _save_ratings({})
            _save_schedule_cache({})
    
    ratings = _load_ratings()
    dt_fim = datetime.strptime(fim, "%Y-%m-%d").date()
    
    assert dt_ini <= dt_fim, "Data inicial deve ser <= data final"

    dia = dt_ini
    count_games = 0
    total_mov = 0
    back_to_back_games = 0
    
    early_season_games = 0
    mid_season_games = 0
    late_season_games = 0
    regression_applied = 0
    
    total_days = (dt_fim - dt_ini).days + 1
    days_processed = 0
    
    while dia <= dt_fim:
        data_str = dia.isoformat()
        
        if days_processed % 30 == 0 and days_processed > 0:
            progress_pct = (days_processed / total_days) * 100
            console.print(f"[dim]  Progresso: {progress_pct:.0f}% ({days_processed}/{total_days} dias)[/dim]")
        
        # Aplicar regressão em Outubro
        if dia.month == REGRESSION_MONTH and dia.day == 1:
            ratings = apply_regression_to_mean(ratings, data_str)
            _save_ratings(ratings)
            regression_applied += 1
        
        try:
            df = calendario_df_espn(data_str)
        except Exception:
            dia += timedelta(days=1)
            days_processed += 1
            continue

        if df is not None and not df.empty:
            for _, r in df.iterrows():
                home = r["home"]
                away = r["away"]
                home_won, point_diff = _parse_resultado(r)
                
                if home and away and home_won is not None and point_diff is not None:
                    home_days = _days_since_last_game(home, data_str)
                    away_days = _days_since_last_game(away, data_str)
                    
                    if home_days == 1:
                        back_to_back_games += 1
                    if away_days == 1:
                        back_to_back_games += 1
                    
                    k = get_k_factor(data_str)
                    if k == K_EARLY_SEASON:
                        early_season_games += 1
                    elif k == K_MID_SEASON:
                        mid_season_games += 1
                    elif k == K_LATE_SEASON:
                        late_season_games += 1
                    
                    home_score = int(r["home_score"])
                    away_score = int(r["away_score"])
                    aplicar_resultado_final(home, away, home_score, away_score, data_str)
                    count_games += 1
                    total_mov += point_diff
        
        if days_processed % 7 == 0:
            _save_checkpoint(data_str)
                    
        dia += timedelta(days=1)
        days_processed += 1
    
    _save_checkpoint(dt_fim.isoformat())

    avg_mov = total_mov / count_games if count_games > 0 else 0
    console.print(f"\n[green]✓ Histórico Elo atualizado:[/green]")
    console.print(f"  • Jogos processados: {count_games}")
    console.print(f"  • MOV médio: {avg_mov:.1f} pontos")
    console.print(f"  • Back-to-backs: {back_to_back_games}")
    console.print(f"  • Early Season (K={K_EARLY_SEASON}): {early_season_games}")
    console.print(f"  • Mid Season (K={K_MID_SEASON}): {mid_season_games}")
    console.print(f"  • Late Season (K={K_LATE_SEASON}): {late_season_games}")
    console.print(f"  • Regressões aplicadas: {regression_applied}")
    
    if last_checkpoint and not force_full:
        console.print(f"  • [cyan]Processamento incremental desde {last_checkpoint}[/cyan]")


# --------------------
# Avaliação
# --------------------
def avaliar_previsoes_para_data(data: str) -> dict:
    df = calendario_df_espn(data)
    if df is None or df.empty:
        return {"data": data, "jogos": 0, "acerto": None, "brier": None}

    prev = prever_vencedor_para_data(df)
    n, certos, soma_brier = 0, 0, 0.0
    b2b_count = 0
    injury_impact_count = 0

    for _, r in prev.iterrows():
        if str(r.get("status","")).lower().startswith("final") and r.get("home_score") is not None:
            n += 1
            y = 1 if int(r["home_score"]) > int(r["away_score"]) else 0
            p = float(r["prob_home"])
            pred_home = r["vencedor_previsto"] == r["home"]
            certos += 1 if (pred_home and y==1) or ((not pred_home) and y==0) else 0
            soma_brier += (p - y) ** 2
            
            if r.get("home_days_rest") == 1 or r.get("away_days_rest") == 1:
                b2b_count += 1
            
            if r.get("home_injury_adj") != 0 or r.get("away_injury_adj") != 0:
                injury_impact_count += 1

    if n == 0:
        return {"data": data, "jogos": 0, "acerto": None, "brier": None}

    return {
        "data": data,
        "jogos": n,
        "acerto": round(certos / n, 3),
        "brier": round(soma_brier / n, 4),
        "back_to_backs": b2b_count,
        "injuries_impact": injury_impact_count,
        "k_factor": get_k_factor(data)
    }