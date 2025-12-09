# services/team_stats.py - NOVO MÓDULO COMPLETO
"""
Sistema de estatísticas de EQUIPAS NBA.
Offensive/Defensive ratings, pace, rankings, comparações entre épocas.
"""

from typing import Optional, Literal, List
import pandas as pd
from nba_api.stats.endpoints import leaguedashteamstats
from nba_api.stats.static import teams as teams_static
from rich.table import Table
from rich.console import Console
from rich.panel import Panel
from rich import box
from pathlib import Path

console = Console()

CACHE_DIR = Path("data/cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _get_team_id(team_abbr: str) -> Optional[int]:
    """Obtém team_id da NBA API."""
    all_teams = teams_static.get_teams()
    match = [t for t in all_teams if t["abbreviation"] == team_abbr]
    return match[0]["id"] if match else None


def get_team_stats(
    season: str = "2025-26",
    season_type: Literal["Regular Season", "Playoffs"] = "Regular Season",
    per_mode: Literal["PerGame", "Totals"] = "PerGame",
    use_cache: bool = True
) -> pd.DataFrame:
    """
    Obtém estatísticas de TODAS as equipas da liga.
    
    Returns:
        DataFrame com stats de todas as 30 equipas
    """
    cache_key = f"team_stats_{season}_{season_type}_{per_mode}.json"
    cache_file = CACHE_DIR / cache_key
    
    # Tentar cache
    if use_cache and cache_file.exists():
        try:
            df = pd.read_json(cache_file)
            console.print(f"[dim]✓ Team stats do cache: {cache_file.name}[/dim]")
            return df
        except Exception:
            pass
    
    # Fetch da API
    try:
        resp = leaguedashteamstats.LeagueDashTeamStats(
            season=season,
            season_type_all_star=season_type,
            per_mode_detailed=per_mode
        )
        df = resp.get_data_frames()[0]
        
        # Guardar cache
        if use_cache:
            df.to_json(cache_file, orient="records", indent=2)
        
        return df
    
    except Exception as e:
        console.print(f"[red]Erro ao obter team stats: {e}[/red]")
        return pd.DataFrame()


def get_single_team_stats(
    team_abbr: str,
    season: str = "2025-26",
    season_type: Literal["Regular Season", "Playoffs"] = "Regular Season"
) -> Optional[pd.Series]:
    """
    Obtém stats de UMA equipa específica.
    
    Returns:
        Series com estatísticas da equipa ou None
    """
    team_id = _get_team_id(team_abbr)
    if not team_id:
        return None
    
    df = get_team_stats(season=season, season_type=season_type)
    
    if df.empty:
        return None
    
    team_row = df[df["TEAM_ID"] == team_id]
    
    return team_row.iloc[0] if not team_row.empty else None


def ver_estatisticas_equipa_detalhado(
    team_abbr: str,
    season: str = "2025-26",
    compare_with_previous: bool = True
) -> None:
    """
    Visualiza estatísticas detalhadas de UMA equipa.
    
    Args:
        team_abbr: Abreviação da equipa
        season: Época atual
        compare_with_previous: Comparar com época anterior?
    """
    current_stats = get_single_team_stats(team_abbr, season)
    
    if current_stats is None:
        console.print(f"[red]Equipa '{team_abbr}' não encontrada[/red]")
        return
    
    # Header
    console.print(f"\n[bold cyan]📊 ESTATÍSTICAS DETALHADAS: {team_abbr}[/bold cyan]")
    console.print(f"[dim]Época: {season} | Regular Season[/dim]\n")
    
    # === RECORD & BASICS ===
    record_content = (
        f"[bold]Record:[/bold] {int(current_stats.get('W', 0))}-{int(current_stats.get('L', 0))} "
        f"({current_stats.get('W_PCT', 0):.3f})\n"
        f"[bold]Games Played:[/bold] {int(current_stats.get('GP', 0))}\n"
        f"[bold]Plus/Minus:[/bold] {current_stats.get('PLUS_MINUS', 0):+.1f}"
    )
    console.print(Panel(record_content, title="🏆 Record", box=box.ROUNDED, border_style="green"))
    
    # === OFFENSIVE STATS ===
    offensive_content = (
        f"[bold green]PPG:[/bold green] {current_stats.get('PTS', 0):.1f}\n"
        f"[bold]FG%:[/bold] {current_stats.get('FG_PCT', 0):.1%} | "
        f"[bold]3P%:[/bold] {current_stats.get('FG3_PCT', 0):.1%} | "
        f"[bold]FT%:[/bold] {current_stats.get('FT_PCT', 0):.1%}\n"
        f"[bold]AST:[/bold] {current_stats.get('AST', 0):.1f} | "
        f"[bold]TOV:[/bold] {current_stats.get('TOV', 0):.1f} | "
        f"[bold]AST/TO:[/bold] {(current_stats.get('AST', 0) / max(current_stats.get('TOV', 1), 1)):.2f}"
    )
    console.print(Panel(offensive_content, title="⚡ Offensive Stats", box=box.ROUNDED, border_style="yellow"))
    
    # === DEFENSIVE STATS ===
    opp_pts = current_stats.get('OPP_PTS', current_stats.get('PTS', 0))  # Fallback se OPP_PTS não existir
    defensive_content = (
        f"[bold red]OPP PPG:[/bold red] {opp_pts:.1f}\n"
        f"[bold]STL:[/bold] {current_stats.get('STL', 0):.1f} | "
        f"[bold]BLK:[/bold] {current_stats.get('BLK', 0):.1f}\n"
        f"[bold]DREB:[/bold] {current_stats.get('DREB', 0):.1f} | "
        f"[bold]Total REB:[/bold] {current_stats.get('REB', 0):.1f}"
    )
    console.print(Panel(defensive_content, title="🛡️ Defensive Stats", box=box.ROUNDED, border_style="red"))
    
    # === COMPARAÇÃO COM ÉPOCA ANTERIOR ===
    if compare_with_previous:
        # Calcular época anterior
        current_year = int(season.split("-")[0])
        prev_season = f"{current_year-1}-{str(current_year)[-2:]}"
        
        prev_stats = get_single_team_stats(team_abbr, prev_season)
        
        if prev_stats is not None:
            console.print(f"\n[bold]📈 Comparação com {prev_season}:[/bold]")
            
            comparisons = {
                "PPG": ("PTS", "green"),
                "FG%": ("FG_PCT", "yellow"),
                "W%": ("W_PCT", "green"),
                "APG": ("AST", "blue"),
                "RPG": ("REB", "blue")
            }
            
            table = Table(box=box.SIMPLE)
            table.add_column("Métrica", style="cyan")
            table.add_column(prev_season, justify="right")
            table.add_column(season, justify="right")
            table.add_column("Δ", justify="right", style="bold")
            
            for label, (col, color) in comparisons.items():
                if col in current_stats.index and col in prev_stats.index:
                    curr_val = current_stats[col]
                    prev_val = prev_stats[col]
                    delta = curr_val - prev_val
                    
                    # Formatação
                    if "PCT" in col:
                        curr_str = f"{curr_val:.1%}"
                        prev_str = f"{prev_val:.1%}"
                        delta_str = f"{delta:+.1%}"
                    else:
                        curr_str = f"{curr_val:.1f}"
                        prev_str = f"{prev_val:.1f}"
                        delta_str = f"{delta:+.1f}"
                    
                    # Cor do delta
                    if delta > 0:
                        delta_str = f"[green]{delta_str} ↑[/green]"
                    elif delta < 0:
                        delta_str = f"[red]{delta_str} ↓[/red]"
                    else:
                        delta_str = f"[dim]{delta_str} ━[/dim]"
                    
                    table.add_row(label, prev_str, curr_str, delta_str)
            
            console.print(table)


def export_team_stats(
    output_file: str,
    season: str = "2025-26",
    format: Literal["csv", "json", "excel"] = "csv"
) -> None:
    """Exporta stats de todas as equipas."""
    df = get_team_stats(season=season)
    
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
        
        console.print(f"[green]✓ Stats de equipas exportadas para {output_file}[/green]")
    
    except Exception as e:
        console.print(f"[red]Erro ao exportar: {e}[/red]")