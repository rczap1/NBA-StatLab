# services/game_analysis.py
"""
Sistema completo de análise de jogos NBA.
Integra: Elo, Odds, Lesões, Stats de Jogadores, Forma Recente
"""

from typing import Dict, Optional, List, Tuple
import pandas as pd
from rich.table import Table
from rich.console import Console
from rich.panel import Panel
from rich.columns import Columns
from rich import box
from datetime import datetime

from services.predictions import prever_vencedor_para_data, _load_ratings
from services.calendar import calendario_df_espn
from services.injuries import injuries_por_jogo
from services.stats import ver_estatisticas_equipa
from nba_api.stats.static import teams as teams_static
from nba_api.stats.endpoints import leaguedashplayerstats

console = Console()


def _get_team_id(abbr: str) -> Optional[int]:
    """Obtém team_id da NBA API a partir da abreviação."""
    all_teams = teams_static.get_teams()
    match = [t for t in all_teams if t["abbreviation"] == abbr]
    return match[0]["id"] if match else None


def _get_team_record(team_abbr: str, home_away: str = "all", season: str = "2025-26") -> str:
    """
    Obtém record de uma equipa (vitórias-derrotas) APENAS Regular Season.
    
    Args:
        team_abbr: Abreviação da equipa
        home_away: 'home', 'away', ou 'all'
        season: Época
    
    Returns:
        String no formato "W-L" ou "-" se indisponível
    """
    try:
        from nba_api.stats.endpoints import leaguedashteamstats
        
        team_id = _get_team_id(team_abbr)
        if not team_id:
            return "-"
        
        # Determinar location
        location = ""
        if home_away == "home":
            location = "Home"
        elif home_away == "away":
            location = "Road"
        
        # CRÍTICO: Especificar SeasonType para evitar pré-época
        resp = leaguedashteamstats.LeagueDashTeamStats(
            season=season,
            season_type_all_star="Regular Season",  # Apenas época regular
            team_id_nullable=team_id,
            location_nullable=location,
            per_mode_detailed="Totals"
        )
        df = resp.get_data_frames()[0]
        
        if df.empty:
            return "-"
        
        row = df.iloc[0]
        wins = int(row.get("W", 0))
        losses = int(row.get("L", 0))
        
        return f"{wins}-{losses}"
    
    except Exception as e:
        # Em caso de erro, tentar método alternativo via standings
        try:
            from nba_api.stats.endpoints import leaguestandings
            
            standings = leaguestandings.LeagueStandings(
                season=season,
                season_type="Regular Season"
            )
            df_standings = standings.get_data_frames()[0]
            
            team_row = df_standings[df_standings["TeamID"] == team_id]
            if team_row.empty:
                return "-"
            
            # Filtrar por location se necessário
            if home_away == "all":
                wins = int(team_row.iloc[0].get("WINS", 0))
                losses = int(team_row.iloc[0].get("LOSSES", 0))
                return f"{wins}-{losses}"
            elif home_away == "home":
                home_record = team_row.iloc[0].get("HOME", "-")
                return home_record
            elif home_away == "away":
                road_record = team_row.iloc[0].get("ROAD", "-")
                return road_record
            
            return "-"
        except Exception:
            return "-"
        """Obtém team_id da NBA API a partir da abreviação."""
    all_teams = teams_static.get_teams()
    match = [t for t in all_teams if t["abbreviation"] == abbr]
    return match[0]["id"] if match else None


def _get_all_players(team_abbr: str, injured_players: List[str], season: str = "2025-26") -> pd.DataFrame:
    """
    Obtém TODOS os jogadores de uma equipa ordenados por PPG.
    Remove jogadores lesionados da lista.
    """
    try:
        team_id = _get_team_id(team_abbr)
        if not team_id:
            return pd.DataFrame()
        
        resp = leaguedashplayerstats.LeagueDashPlayerStats(
            season=season,
            season_type_all_star="Regular Season",
            per_mode_detailed="PerGame",
            team_id_nullable=team_id
        )
        df = resp.get_data_frames()[0]
        
        # Filtrar colunas relevantes
        cols = ["PLAYER_NAME", "GP", "MIN", "PTS", "REB", "AST", "FG_PCT", "FG3_PCT"]
        available = [c for c in cols if c in df.columns]
        df = df[available]
        
        # NOVO: Remover jogadores lesionados
        if injured_players:
            df = df[~df["PLAYER_NAME"].isin(injured_players)]
        
        # Filtrar apenas quem jogou (GP > 0)
        if "GP" in df.columns:
            df = df[df["GP"] > 0]
        
        # Ordenar por pontos
        if "PTS" in df.columns:
            df = df.sort_values("PTS", ascending=False)
        
        return df
    
    except Exception as e:
        console.print(f"[dim]Aviso: Stats de {team_abbr} indisponíveis ({e})[/dim]")
        return pd.DataFrame()


def analisar_jogo_completo(home: str, away: str, data: str) -> Dict:
    """
    Análise COMPLETA de um jogo.
    
    Returns:
        Dict com todas as informações do jogo
    """
    analise = {
        "home": home,
        "away": away,
        "data": data,
        "previsao_elo": None,
        "odds": None,
        "lesoes_home": [],
        "lesoes_away": [],
        "jogadores_home": pd.DataFrame(),
        "jogadores_away": pd.DataFrame(),
        "value_bet": None
    }
    
    # 1. Previsão Elo
    try:
        jogos_df = calendario_df_espn(data)
        if not jogos_df.empty:
            previsoes = prever_vencedor_para_data(jogos_df)
            jogo = previsoes[
                (previsoes["home"] == home) & (previsoes["away"] == away)
            ]
            if not jogo.empty:
                analise["previsao_elo"] = jogo.iloc[0].to_dict()
    except Exception as e:
        console.print(f"[yellow]Aviso: Previsão Elo indisponível ({e})[/yellow]")
    
    # 2. Lesões
    try:
        injuries = injuries_por_jogo(data)
        if not injuries.empty:
            analise["lesoes_home"] = injuries[injuries["team_abbr"] == home].to_dict('records')
            analise["lesoes_away"] = injuries[injuries["team_abbr"] == away].to_dict('records')
    except Exception as e:
        console.print(f"[dim]Aviso: Lesões indisponíveis ({e})[/dim]")
    
    # 3. TODOS os Jogadores (excluindo lesionados "Out")
    injured_home = [inj["player"] for inj in analise["lesoes_home"] if inj.get("status") == "Out"]
    injured_away = [inj["player"] for inj in analise["lesoes_away"] if inj.get("status") == "Out"]
    
    analise["jogadores_home"] = _get_all_players(home, injured_home)
    analise["jogadores_away"] = _get_all_players(away, injured_away)
    
    # 4. NOVO: Records (Overall + Específico)
    analise["record_home_overall"] = _get_team_record(home, "all")
    analise["record_home_at_home"] = _get_team_record(home, "home")
    analise["record_away_overall"] = _get_team_record(away, "all")
    analise["record_away_on_road"] = _get_team_record(away, "away")
    
    return analise


def mostrar_analise_visual(analise: Dict) -> None:
    """
    Mostra análise de jogo de forma visual com Rich.
    """
    home = analise["home"]
    away = analise["away"]
    data = analise["data"]
    
    console.print("\n" + "="*80)
    console.print(f"[bold cyan]🏀 {home} vs {away}[/bold cyan] - {data}")
    console.print("="*80 + "\n")
    
    # ==================== PROBABILIDADES & VALUE ====================
    if analise["previsao_elo"]:
        prev = analise["previsao_elo"]
    
        prob_panel_content = (
            f"[bold]🎲 Previsão do Modelo Elo:[/bold]\n\n"
            f"  {home}: [green]{prev['prob_home']:.1%}[/green]\n"
            f"  {away}: [yellow]{prev['prob_away']:.1%}[/yellow]\n\n"
            f"[bold]Vencedor Previsto:[/bold] {prev['vencedor_previsto']}\n"
            f"[bold]Confiança:[/bold] {max(prev['prob_home'], prev['prob_away']):.1%}"
        )
    
    console.print(Panel(prob_panel_content, title="🔮 Previsão", box=box.ROUNDED, border_style="cyan"))
        

    # ==================== LESÕES ====================
    lesoes_content = ""
    
    if analise["lesoes_home"]:
        lesoes_content += f"[bold cyan]🏠 {home}:[/bold cyan]\n"
        for inj in analise["lesoes_home"][:5]:
            status_color = "red" if inj["status"] == "Out" else "yellow"
            icon = "❌" if inj["status"] == "Out" else "⚠️"
            lesoes_content += f"  {icon} {inj['player']} - [{status_color}]{inj['status']}[/{status_color}]\n"
    else:
        lesoes_content += f"[bold cyan]🏠 {home}:[/bold cyan] [green]✓ Sem lesões reportadas[/green]\n"
    
    lesoes_content += "\n"
    
    if analise["lesoes_away"]:
        lesoes_content += f"[bold yellow]✈️  {away}:[/bold yellow]\n"
        for inj in analise["lesoes_away"][:5]:
            status_color = "red" if inj["status"] == "Out" else "yellow"
            icon = "❌" if inj["status"] == "Out" else "⚠️"
            lesoes_content += f"  {icon} {inj['player']} - [{status_color}]{inj['status']}[/{status_color}]\n"
    else:
        lesoes_content += f"[bold yellow]✈️  {away}:[/bold yellow] [green]✓ Sem lesões reportadas[/green]"
    
    console.print(Panel(lesoes_content, title="🏥 Relatório de Lesões", box=box.ROUNDED, border_style="red"))
    
    # ==================== ELO & FORMA ====================
    if analise["previsao_elo"]:
        prev = analise["previsao_elo"]
        
        # Records
        record_home_overall = analise.get("record_home_overall", "-")
        record_home_at_home = analise.get("record_home_at_home", "-")
        record_away_overall = analise.get("record_away_overall", "-")
        record_away_on_road = analise.get("record_away_on_road", "-")
        
        elo_content = (
            f"[bold cyan]🏠 {home} (Casa):[/bold cyan]\n"
            f"  • Elo Rating: [bold]{prev['elo_home']:.1f}[/bold]\n"
            f"  • Record Geral: [bold]{record_home_overall}[/bold]\n"
            f"  • Record em Casa: [bold green]{record_home_at_home}[/bold green]\n"
        )
        
        # Ajustes home
        ajustes_home = []
        if prev.get("home_rest_adj", 0) != 0:
            ajustes_home.append(f"Descanso {prev['home_rest_adj']:+.0f}")
        if prev.get("home_injury_adj", 0) != 0:
            ajustes_home.append(f"Lesões {prev['home_injury_adj']:+.0f}")
        
        if ajustes_home:
            elo_content += f"  • Ajustes: [yellow]{', '.join(ajustes_home)}[/yellow]\n"
        
        elo_content += (
            f"\n[bold yellow]✈️  {away} (Visitante):[/bold yellow]\n"
            f"  • Elo Rating: [bold]{prev['elo_away']:.1f}[/bold]\n"
            f"  • Record Geral: [bold]{record_away_overall}[/bold]\n"
            f"  • Record Fora: [bold green]{record_away_on_road}[/bold green]\n"
        )
        
        # Ajustes away
        ajustes_away = []
        if prev.get("away_rest_adj", 0) != 0:
            ajustes_away.append(f"Descanso {prev['away_rest_adj']:+.0f}")
        if prev.get("away_injury_adj", 0) != 0:
            ajustes_away.append(f"Lesões {prev['away_injury_adj']:+.0f}")
        
        if ajustes_away:
            elo_content += f"  • Ajustes: [yellow]{', '.join(ajustes_away)}[/yellow]"
        
        console.print(Panel(elo_content, title="📈 Ratings Elo & Records", box=box.ROUNDED, border_style="green"))
    
    # ==================== COMPARAÇÃO DE JOGADORES ====================
    if not analise["jogadores_home"].empty or not analise["jogadores_away"].empty:
        console.print(Panel(
            f"[bold]Comparação de Plantel Completo[/bold]\n"
            f"[dim]Stats da época 2025-26 • Ordenado por PPG • Jogadores 'Out' removidos[/dim]",
            box=box.ROUNDED,
            border_style="blue"
        ))
        console.print()
        
        # Criar tabelas lado a lado
        table_home = Table(title=f"🏠 {home}", box=box.SIMPLE, show_header=True, header_style="bold cyan")
        table_home.add_column("Jogador", style="cyan", width=18)
        table_home.add_column("GP", justify="right", width=4)
        table_home.add_column("MIN", justify="right", width=5)
        table_home.add_column("PTS", justify="right", width=5, style="bold green")
        table_home.add_column("REB", justify="right", width=5)
        table_home.add_column("AST", justify="right", width=5)
        
        table_away = Table(title=f"✈️  {away}", box=box.SIMPLE, show_header=True, header_style="bold yellow")
        table_away.add_column("Jogador", style="yellow", width=18)
        table_away.add_column("GP", justify="right", width=4)
        table_away.add_column("MIN", justify="right", width=5)
        table_away.add_column("PTS", justify="right", width=5, style="bold green")
        table_away.add_column("REB", justify="right", width=5)
        table_away.add_column("AST", justify="right", width=5)
        
        # Preencher tabela home
        if not analise["jogadores_home"].empty:
            for _, player in analise["jogadores_home"].iterrows():
                table_home.add_row(
                    player.get("PLAYER_NAME", "")[:18],
                    str(int(player.get("GP", 0))),
                    f"{player.get('MIN', 0):.1f}",
                    f"{player.get('PTS', 0):.1f}",
                    f"{player.get('REB', 0):.1f}",
                    f"{player.get('AST', 0):.1f}"
                )
        
        # Preencher tabela away
        if not analise["jogadores_away"].empty:
            for _, player in analise["jogadores_away"].iterrows():
                table_away.add_row(
                    player.get("PLAYER_NAME", "")[:18],
                    str(int(player.get("GP", 0))),
                    f"{player.get('MIN', 0):.1f}",
                    f"{player.get('PTS', 0):.1f}",
                    f"{player.get('REB', 0):.1f}",
                    f"{player.get('AST', 0):.1f}"
                )
        
        # Mostrar lado a lado
        console.print(Columns([table_home, table_away], equal=True, expand=True))
    
    console.print("\n" + "="*80 + "\n")


def listar_e_escolher_jogo(data: str) -> Optional[Tuple[str, str]]:
    """
    Lista jogos de um dia e permite escolher um para análise detalhada.
    
    Returns:
        (home, away) ou None se cancelar
    """
    try:
        jogos_df = calendario_df_espn(data)
        
        if jogos_df.empty:
            console.print(f"[yellow]Nenhum jogo em {data}[/yellow]")
            return None
        
        console.print(f"\n[bold]🏀 Jogos em {data}:[/bold]\n")
        
        table = Table(box=box.ROUNDED)
        table.add_column("#", justify="right", style="cyan", width=3)
        table.add_column("Casa", justify="center", style="bold cyan", width=6)
        table.add_column("vs", justify="center", width=3)
        table.add_column("Visitante", justify="center", style="bold yellow", width=6)
        table.add_column("Horário", justify="center", width=10)
        
        for idx, (_, jogo) in enumerate(jogos_df.iterrows(), 1):
            horario = jogo.get("start_iso", "-")
            if horario and horario != "-":
                try:
                    dt = datetime.fromisoformat(horario.replace("Z", "+00:00"))
                    horario = dt.strftime("%H:%M")
                except Exception:
                    horario = "-"
            
            table.add_row(
                str(idx),
                jogo["home"],
                "vs",
                jogo["away"],
                horario
            )
        
        console.print(table)
        
        escolha = input("\n➤ Escolhe o número do jogo (0 para cancelar): ").strip()
        
        if escolha == "0":
            return None
        
        try:
            idx = int(escolha) - 1
            if 0 <= idx < len(jogos_df):
                jogo = jogos_df.iloc[idx]
                return jogo["home"], jogo["away"]
            else:
                console.print("[red]Número inválido[/red]")
                return None
        except ValueError:
            console.print("[red]Entrada inválida[/red]")
            return None
    
    except Exception as e:
        console.print(f"[red]Erro: {e}[/red]")
        return None