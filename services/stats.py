# services/stats.py - VERSÃO COMPLETA COM RATE LIMIT PROTECTION
"""
Sistema completo de estatísticas de jogadores NBA.
Suporta múltiplas épocas, filtros avançados e métricas calculadas.

✅ CORRIGIDO: Rate limit protection + retry logic
"""

from typing import Optional, Literal, List
import pandas as pd
import time
from nba_api.stats.endpoints import leaguedashplayerstats
from nba_api.stats.static import teams as teams_static
from rich.table import Table
from rich.console import Console
from pathlib import Path

console = Console()

# Cache para evitar chamadas repetidas à API
CACHE_DIR = Path("data/cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ✅ NOVO: Rate limit protection
API_CALL_DELAY = 0.6  # 600ms entre chamadas (seguro)
_last_api_call = 0


def _wait_for_rate_limit():
    """
    Espera o tempo necessário para respeitar rate limit da NBA API.
    NBA API: máx ~100 requests/min = ~1.6 req/sec = 600ms entre calls
    """
    global _last_api_call
    
    now = time.time()
    elapsed = now - _last_api_call
    
    if elapsed < API_CALL_DELAY:
        wait_time = API_CALL_DELAY - elapsed
        time.sleep(wait_time)
    
    _last_api_call = time.time()


def _get_team_id(team_abbr: str) -> Optional[int]:
    """Obtém team_id da NBA API a partir da abreviação."""
    all_teams = teams_static.get_teams()
    match = [t for t in all_teams if t["abbreviation"] == team_abbr]
    return match[0]["id"] if match else None


def _calculate_advanced_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula métricas avançadas a partir de stats básicas.
    
    Métricas adicionadas:
    - TS% (True Shooting %): Eficiência de shooting considerando 3P e FT
    - EFF (Efficiency): (PTS + REB + AST + STL + BLK) - (FGA-FGM + FTA-FTM + TOV)
    - USG% aproximado: (FGA + 0.44*FTA + TOV) / MIN
    """
    df = df.copy()
    
    # True Shooting %
    if all(col in df.columns for col in ["PTS", "FGA", "FTA"]):
        tsa = 2 * (df["FGA"] + 0.44 * df["FTA"])
        df["TS_PCT"] = (df["PTS"] / tsa).replace([float('inf'), -float('inf')], 0).fillna(0)
    
    # Efficiency Rating
    if all(col in df.columns for col in ["PTS", "REB", "AST", "STL", "BLK", "FGA", "FGM", "FTA", "FTM", "TOV"]):
        df["EFF"] = (
            df["PTS"] + df["REB"] + df["AST"] + df["STL"] + df["BLK"]
            - (df["FGA"] - df["FGM"])
            - (df["FTA"] - df["FTM"])
            - df["TOV"]
        )
    
    # Usage Rate aproximado (simplificado)
    if all(col in df.columns for col in ["FGA", "FTA", "TOV", "MIN"]):
        df["USG_APPROX"] = ((df["FGA"] + 0.44 * df["FTA"] + df["TOV"]) / df["MIN"]).replace([float('inf'), -float('inf')], 0).fillna(0)
    
    return df


def get_player_stats(
    team_id: Optional[int] = None,
    team_abbr: Optional[str] = None,
    season: str = "2025-26",
    per_mode: Literal["PerGame", "Totals", "Per36"] = "PerGame",
    season_type: Literal["Regular Season", "Playoffs"] = "Regular Season",
    min_games: int = 0,
    min_minutes: float = 0.0,
    use_cache: bool = True
) -> pd.DataFrame:
    """
    Obtém estatísticas de jogadores (de uma equipa ou liga inteira).
    
    ✅ CORRIGIDO: Rate limit protection + retry logic
    
    Args:
        team_id: ID da equipa (None = todas as equipas)
        team_abbr: Abreviação da equipa (alternativa a team_id)
        season: Época (ex: "2025-26")
        per_mode: "PerGame", "Totals", ou "Per36"
        season_type: "Regular Season" ou "Playoffs"
        min_games: Filtrar jogadores com GP >= min_games
        min_minutes: Filtrar jogadores com MIN >= min_minutes
        use_cache: Usar cache local (evita rate limits)
    
    Returns:
        DataFrame com estatísticas + métricas avançadas
    """
    # Resolver team_id se foi dado team_abbr
    if team_abbr and not team_id:
        team_id = _get_team_id(team_abbr)
        if not team_id:
            console.print(f"[red]Equipa '{team_abbr}' não encontrada[/red]")
            return pd.DataFrame()
    
    # Cache key
    cache_key = f"stats_{season}_{per_mode}_{season_type}_{team_id or 'all'}.json"
    cache_file = CACHE_DIR / cache_key
    
    # Tentar carregar do cache
    if use_cache and cache_file.exists():
        try:
            df = pd.read_json(cache_file)
            console.print(f"[dim]✓ Carregado do cache: {cache_file.name}[/dim]")
            
            # Aplicar filtros
            if min_games > 0:
                df = df[df["GP"] >= min_games]
            if min_minutes > 0:
                df = df[df["MIN"] >= min_minutes]
            
            # Calcular métricas avançadas
            df = _calculate_advanced_metrics(df)
            
            return df
        except Exception:
            console.print(f"[yellow]Cache corrompido, a recarregar...[/yellow]")
    
    # ✅ Fetch da API com rate limit + retry
    max_retries = 3
    df = None
    
    for attempt in range(max_retries):
        try:
            # ✅ Esperar rate limit
            _wait_for_rate_limit()
            
            console.print(f"[dim]  Chamada NBA API (tentativa {attempt+1}/{max_retries})...[/dim]")
            
            resp = leaguedashplayerstats.LeagueDashPlayerStats(
                season=season,
                season_type_all_star=season_type,
                per_mode_detailed=per_mode,
                team_id_nullable=team_id if team_id else ""
            )
            df = resp.get_data_frames()[0]
            
            # Guardar cache
            if use_cache:
                df.to_json(cache_file, orient="records", indent=2)
                console.print(f"[dim]✓ Cache guardado: {cache_file.name}[/dim]")
            
            # ✅ Sucesso, sair do loop
            break
                
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2  # Backoff: 2s, 4s, 6s
                console.print(f"[yellow]  ⚠️ Erro na API, a tentar novamente em {wait_time}s...[/yellow]")
                time.sleep(wait_time)
            else:
                console.print(f"[red]Erro ao obter stats após {max_retries} tentativas: {e}[/red]")
                return pd.DataFrame()
    
    if df is None or df.empty:
        return pd.DataFrame()
    
    # Aplicar filtros
    if min_games > 0:
        df = df[df["GP"] >= min_games]
    if min_minutes > 0:
        df = df[df["MIN"] >= min_minutes]
    
    # Calcular métricas avançadas
    df = _calculate_advanced_metrics(df)
    
    return df


def get_roster_stats(
    team_abbr: str,
    exclude_players: Optional[List[str]] = None,
    season: str = "2025-26",
    min_games: int = 1
) -> pd.DataFrame:
    """
    Obtém stats do plantel de uma equipa (usado em análise de jogos).
    
    ✅ CORRIGIDO: Com rate limit protection
    
    Args:
        team_abbr: Abreviação da equipa
        exclude_players: Lista de nomes de jogadores a excluir (ex: lesionados)
        season: Época
        min_games: Mínimo de jogos jogados
    
    Returns:
        DataFrame ordenado por PTS (descendente)
    """
    df = get_player_stats(
        team_abbr=team_abbr,
        season=season,
        per_mode="PerGame",
        min_games=min_games
    )
    
    if df.empty:
        return df
    
    # Excluir jogadores
    if exclude_players:
        df = df[~df["PLAYER_NAME"].isin(exclude_players)]
    
    # Ordenar por pontos
    if "PTS" in df.columns:
        df = df.sort_values("PTS", ascending=False)
    
    return df


def ver_estatisticas_equipa(
    team_id: Optional[int] = None,
    team_abbr: Optional[str] = None,
    season: str = "2025-26",
    sort_by: str = "PTS",
    ascending: bool = False,
    show_all_metrics: bool = False,
    top_n: Optional[int] = None,
    min_games: int = 0
) -> None:
    """
    Visualiza estatísticas de uma equipa com Rich.
    
    Args:
        team_id: ID da equipa
        team_abbr: Abreviação da equipa (alternativa)
        season: Época
        sort_by: Coluna para ordenar
        ascending: Ordem ascendente?
        show_all_metrics: Mostrar todas as métricas?
        top_n: Limitar a top N jogadores
        min_games: Filtro de jogos mínimos
    """
    df = get_player_stats(
        team_id=team_id,
        team_abbr=team_abbr,
        season=season,
        per_mode="PerGame",
        min_games=min_games
    )
    
    if df.empty:
        console.print(f"[yellow]Sem dados disponíveis para {team_abbr or team_id} em {season}[/yellow]")
        return
    
    # Definir colunas
    cols_base = ["PLAYER_NAME", "GP", "MIN", "PTS", "REB", "AST", "FG_PCT", "FG3_PCT", "FT_PCT"]
    cols_extra = ["STL", "BLK", "TOV", "PLUS_MINUS", "TS_PCT", "EFF"]
    
    cols = cols_base + (cols_extra if show_all_metrics else [])
    available = [c for c in cols if c in df.columns]
    
    df_display = df[available].copy()
    
    # Ordenação
    if sort_by in df_display.columns:
        df_display = df_display.sort_values(sort_by, ascending=ascending)
    
    # Limitar top N
    if top_n:
        df_display = df_display.head(top_n)
    
    # Criar tabela
    team_name = team_abbr or team_id
    table = Table(title=f"📊 Estatísticas {team_name} — {season}", show_header=True)
    
    for col in available:
        justify = "left" if col == "PLAYER_NAME" else "right"
        
        # Styling por coluna
        if col == "PTS":
            style = "bold green"
        elif col in ["REB", "AST"]:
            style = "bold blue"
        elif "PCT" in col or col == "TS_PCT":
            style = "yellow"
        else:
            style = None
        
        table.add_column(col, justify=justify, style=style)
    
    # Preencher linhas
    for _, row in df_display.iterrows():
        formatted = []
        for col in available:
            val = row[col]
            
            # Formatação especial para percentagens
            if ("PCT" in col or col == "TS_PCT") and pd.notna(val):
                formatted.append(f"{val:.1%}")
            elif isinstance(val, float) and pd.notna(val):
                formatted.append(f"{val:.1f}")
            else:
                formatted.append(str(val))
        
        table.add_row(*formatted)
    
    console.print(table)
    
    # Resumo estatístico
    if not df_display.empty and "PTS" in df_display.columns:
        top_scorer = df_display.iloc[0]
        avg_ppg = df_display["PTS"].mean()
        
        console.print(
            f"\n[dim]📈 Média equipa: {avg_ppg:.1f} PPG | "
            f"Top scorer: {top_scorer['PLAYER_NAME']} ({top_scorer['PTS']:.1f} PPG)[/dim]"
        )
        
        if "REB" in df_display.columns and "AST" in df_display.columns:
            console.print(
                f"[dim]   Média REB: {df_display['REB'].mean():.1f} | "
                f"Média AST: {df_display['AST'].mean():.1f}[/dim]"
            )
    
    # Legenda
    if show_all_metrics:
        console.print(
            "\n[grey]Legenda: TS% = True Shooting %, EFF = Efficiency Rating, "
            "STL = Roubadas, BLK = Bloqueios, TOV = Turnovers[/grey]"
        )


def export_stats(
    output_file: str,
    team_abbr: Optional[str] = None,
    season: str = "2025-26",
    format: Literal["csv", "json", "excel"] = "csv"
) -> None:
    """
    Exporta estatísticas para ficheiro.
    
    Args:
        output_file: Path do ficheiro de saída
        team_abbr: Equipa (None = toda a liga)
        season: Época
        format: Formato de exportação
    """
    df = get_player_stats(team_abbr=team_abbr, season=season)
    
    if df.empty:
        console.print("[yellow]Sem dados para exportar[/yellow]")
        return
    
    try:
        if format == "csv":
            df.to_csv(output_file, index=False)
        elif format == "json":
            df.to_json(output_file, orient="records", indent=2)
        elif format == "excel":
            df.to_excel(output_file, index=False)
        
        console.print(f"[green]✓ Exportado para {output_file}[/green]")
    
    except Exception as e:
        console.print(f"[red]Erro ao exportar: {e}[/red]")