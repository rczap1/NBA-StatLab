# app.py - MENU HIERÁRQUICO OTIMIZADO

# ═══════════════════════════════════════════════════════════════
#                           IMPORTS
# ═══════════════════════════════════════════════════════════════

# Standard Library
import typer
from enum import Enum
from typing import Optional
from pathlib import Path
from datetime import datetime, timezone, timedelta
import json

# Third-party
import pandas as pd
from rich.table import Table
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.columns import Columns
from rich import box

# NBA API
from nba_api.stats.static import teams as teams_static

# Services - Predictions
from services.predictions import (
    prever_vencedor_para_data,
    avaliar_previsoes_para_data,
    atualizar_elos_historico,
    _load_ratings
)

# Services - Data
from services.calendar import ver_calendario_espn, calendario_df_espn
from services.injuries import injuries_por_jogo
from services.roster import ver_plantel
from services.stats import ver_estatisticas_equipa

# Services - Analysis
from services.game_analysis import (
    listar_e_escolher_jogo,
    analisar_jogo_completo,
    mostrar_analise_visual,
)

# Services - Advanced
from services.player_tiers import (
    show_top_players,
    show_tier_distribution,
    update_all_tiers,
    load_tiers
)
from services.team_stats import ver_estatisticas_equipa_detalhado


# ═══════════════════════════════════════════════════════════════
#                       INICIALIZAÇÃO
# ═══════════════════════════════════════════════════════════════

app = typer.Typer(help="🏀 NBA StatLab", add_completion=False)
console = Console()


# ═══════════════════════════════════════════════════════════════
#                    FUNÇÕES AUXILIARES
# ═══════════════════════════════════════════════════════════════

def _load_checkpoint() -> Optional[str]:
    """Carrega último checkpoint de processamento."""
    checkpoint_path = Path("data/elo_checkpoint.json")
    if checkpoint_path.exists():
        try:
            data = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            return data.get("last_processed_date")
        except Exception:
            return None
    return None


def _normaliza_data(s: str) -> str:
    """Normaliza data para formato YYYY-MM-DD."""
    s = s.strip()
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return s
    except ValueError:
        pass
    try:
        dt = datetime.strptime(s, "%d-%m-%Y")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        raise ValueError("Data inválida. Usa YYYY-MM-DD ou DD-MM-YYYY.")


def _pedir_data(prompt: str = "Data", allow_empty: bool = True) -> str:
    """
    Pede data ao utilizador com default = hoje.
    
    Args:
        prompt: Texto do prompt
        allow_empty: Se True, Enter = hoje
    
    Returns:
        Data no formato YYYY-MM-DD
    """
    hoje = datetime.now(timezone.utc).date().isoformat()
    
    if allow_empty:
        data_in = Prompt.ask(
            f"{prompt} (DD-MM-YYYY ou YYYY-MM-DD, Enter=hoje [{hoje}])",
            default=""
        )
    else:
        data_in = Prompt.ask(f"{prompt} (DD-MM-YYYY ou YYYY-MM-DD)")
    
    # Se vazio e permitido, retorna hoje
    if not data_in and allow_empty:
        console.print(f"[dim]→ Usando hoje: {hoje}[/dim]")
        return hoje
    
    # Normalizar data
    try:
        return _normaliza_data(data_in)
    except Exception as e:
        console.print(f"[red]{e}[/red]")
        return _pedir_data(prompt, allow_empty)


def _inicio_epoca_para(data_iso: str) -> str:
    """Define início da época baseado na data."""
    dt = datetime.strptime(data_iso, "%Y-%m-%d").date()
    if dt.month >= 10:
        season_start_year = dt.year
    else:
        season_start_year = dt.year - 1
    return f"{season_start_year}-10-01"


def _get_team_id(team_abbr: str) -> Optional[int]:
    """Obtém team ID da NBA API."""
    all_teams = teams_static.get_teams()
    match = [t for t in all_teams if t["abbreviation"] == team_abbr.upper()]
    return match[0]["id"] if match else None


def ver_rankings_elo():
    """Mostra rankings Elo atuais de todas as equipas."""
    ratings = _load_ratings()
    
    if not ratings:
        console.print("[yellow]Ainda não há ratings Elo. Calcula o histórico primeiro.[/yellow]")
        return
    
    # Lista de abreviações NBA válidas (30 equipas)
    nba_teams = {
        "ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GSW",
        "HOU", "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NOP", "NYK",
        "OKC", "ORL", "PHI", "PHX", "POR", "SAC", "SAS", "TOR", "UTA", "WAS"
    }
    
    # Filtrar apenas equipas NBA válidas
    nba_ratings = {team: elo for team, elo in ratings.items() if team in nba_teams}
    
    if not nba_ratings:
        console.print("[yellow]Nenhuma equipa NBA encontrada nos ratings.[/yellow]")
        return
    
    sorted_teams = sorted(nba_ratings.items(), key=lambda x: x[1], reverse=True)
    
    table = Table(title="🏆 Rankings Elo NBA", box=box.ROUNDED)
    table.add_column("Rank", justify="right", style="cyan", width=6)
    table.add_column("Equipa", justify="center", style="bold", width=8)
    table.add_column("Elo Rating", justify="right", style="green", width=12)
    table.add_column("vs Média", justify="right", width=10)
    table.add_column("Tier", justify="center", width=12)
    
    elo_medio = 1500.0
    
    for idx, (team, elo) in enumerate(sorted_teams, 1):
        diff = elo - elo_medio
        diff_str = f"+{diff:.0f}" if diff > 0 else f"{diff:.0f}"
        
        # Determinar tier
        if elo >= 1650:
            tier = "Elite 🌟"
            style = "bold green"
        elif elo >= 1550:
            tier = "Forte 💪"
            style = "green"
        elif elo >= 1450:
            tier = "Médio 📊"
            style = "yellow"
        elif elo >= 1350:
            tier = "Fraco 📉"
            style = "orange3"
        else:
            tier = "Rebuild 🏗️"
            style = "red"
        
        table.add_row(
            str(idx),
            f"[{style}]{team}[/{style}]",
            f"[{style}]{elo:.1f}[/{style}]",
            diff_str,
            tier
        )
    
    console.print(table)
    
    # Estatísticas
    console.print(f"\n[bold]📊 Estatísticas:[/bold]")
    console.print(f"  • Melhor: {sorted_teams[0][0]} ({sorted_teams[0][1]:.1f})")
    console.print(f"  • Pior: {sorted_teams[-1][0]} ({sorted_teams[-1][1]:.1f})")
    console.print(f"  • Spread: {sorted_teams[0][1] - sorted_teams[-1][1]:.1f} pontos")
    console.print(f"  • Elite (>1650): {sum(1 for _, elo in sorted_teams if elo >= 1650)}")
    console.print(f"  • Rebuild (<1350): {sum(1 for _, elo in sorted_teams if elo <= 1350)}")


def ver_lesoes_do_dia(data: str):
    """Mostra lesões das equipas que jogam num dia."""
    try:
        injuries = injuries_por_jogo(data)
        
        if injuries.empty:
            console.print(f"[yellow]Nenhuma lesão reportada para {data}[/yellow]")
            return
        
        # Contar por status
        out_count = len(injuries[injuries["status"] == "Out"])
        dtd_count = len(injuries[injuries["status"] == "Day-To-Day"])
        
        console.print(f"\n[bold]🥊 Lesões para {data}[/bold]")
        console.print(f"Total: {len(injuries)} | Out: {out_count} | Day-to-Day: {dtd_count}\n")
        
        # Agrupar por equipa
        for team in sorted(injuries["team_abbr"].unique()):
            team_inj = injuries[injuries["team_abbr"] == team]
            console.print(f"[bold cyan]{team}[/bold cyan] ({len(team_inj)} lesões)")
            
            for _, inj in team_inj.iterrows():
                status_color = "red" if inj["status"] == "Out" else "yellow"
                icon = "❌" if inj["status"] == "Out" else "⚠️"
                console.print(f"  {icon} {inj['player']} - [{status_color}]{inj['status']}[/{status_color}]")
            console.print()
            
    except Exception as e:
        console.print(f"[red]Erro ao obter lesões: {e}[/red]")


def listar_equipas():
    """Lista todas as equipas NBA."""
    all_teams = teams_static.get_teams()
    table = Table(title="🏀 Equipas NBA", box=box.ROUNDED)
    table.add_column("Abrev.", justify="center", style="cyan", width=8)
    table.add_column("Nome Completo", justify="left", style="bold", width=30)
    table.add_column("Cidade", justify="left", width=20)
    
    for t in sorted(all_teams, key=lambda x: x["abbreviation"]):
        table.add_row(
            t["abbreviation"],
            t["full_name"],
            t.get("city", "")
        )
    
    console.print(table)


# ═══════════════════════════════════════════════════════════════
#                        🎨 SISTEMA DE MENUS
# ═══════════════════════════════════════════════════════════════

class MenuContext(Enum):
    """Contextos do menu hierárquico"""
    MAIN = "main"
    GAMES = "games"
    ANALYSIS = "analysis"
    SYSTEM = "system"


class MenuSystem:
    """Sistema de navegação hierárquica"""
    
    def __init__(self):
        self.context = MenuContext.MAIN
        self.breadcrumb = []
    
    def show_header(self):
        """Header consistente com breadcrumb"""
        console.clear()
        
        # Banner principal
        banner = Panel(
            "[bold cyan]🏀 NBA PREDICTION SYSTEM[/bold cyan]\n"
            "[dim]Sistema Elo Avançado com Injury Impact[/dim]",
            box=box.DOUBLE,
            border_style="cyan"
        )
        console.print(banner)
        
        # Breadcrumb
        if self.breadcrumb:
            path = " → ".join(self.breadcrumb)
            console.print(f"[dim]📍 {path}[/dim]\n")
    
    def show_quick_info(self):
        """Info rápida do sistema"""
        try:
            ratings = _load_ratings()
            checkpoint = _load_checkpoint()
            
            info_panels = []
            
            # Status do Sistema
            status_content = (
                f"[green]●[/green] Sistema Online\n"
                f"[cyan]📊 {len(ratings)} equipas[/cyan]\n"
                f"[dim]Update: {checkpoint or 'N/A'}[/dim]"
            )
            info_panels.append(Panel(status_content, title="⚡ Status", border_style="green", box=box.ROUNDED))
            
            # Top 3 Equipas
            if ratings:
                sorted_teams = sorted(ratings.items(), key=lambda x: x[1], reverse=True)[:3]
                top_content = "\n".join([
                    f"[yellow]{i}.[/yellow] {team} - [bold]{elo:.0f}[/bold]"
                    for i, (team, elo) in enumerate(sorted_teams, 1)
                ])
                info_panels.append(Panel(top_content, title="🏆 Top 3", border_style="yellow", box=box.ROUNDED))
            
            # Jogos de Hoje
            hoje = datetime.now(timezone.utc).date().isoformat()
            try:
                jogos_hoje = calendario_df_espn(hoje)
                games_content = f"[bold cyan]{len(jogos_hoje)}[/bold cyan] jogos hoje"
            except:
                games_content = "[dim]A verificar...[/dim]"
            
            info_panels.append(Panel(games_content, title="📅 Hoje", border_style="cyan", box=box.ROUNDED))
            
            console.print(Columns(info_panels, equal=True, expand=True))
            console.print()
            
        except Exception:
            pass
    
    def show_main_menu(self):
        """Menu principal - 4 opções principais"""
        self.show_header()
        self.show_quick_info()
        
        menu_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
        menu_table.add_column(justify="center", width=10)
        menu_table.add_column(justify="left", width=30)
        menu_table.add_column(justify="left", style="dim", width=40)
        
        menu_table.add_row(
            "[bold cyan]1[/bold cyan]",
            "🎯 [bold]Jogos & Previsões[/bold]",
            "Ver jogos, previsões e análises"
        )
        menu_table.add_row(
            "[bold yellow]3[/bold yellow]",
            "📊 [bold]Análise Avançada[/bold]",
            "Rankings, stats, tiers de jogadores"
        )
        menu_table.add_row(
            "[bold blue]4[/bold blue]",
            "⚙️  [bold]Sistema[/bold]",
            "Configurações e manutenção"
        )
        
        console.print(Panel(menu_table, title="📋 Menu Principal", border_style="cyan", box=box.ROUNDED))
        console.print("\n[dim]Digite 'q' para sair | 'h' para ajuda[/dim]")
        
        choice = Prompt.ask("\n[bold cyan]➤[/bold cyan] Escolhe uma opção", choices=["1", "2", "3", "4", "q", "h"])
        
        if choice == "q":
            return self.confirm_exit()
        elif choice == "h":
            self.show_help()
            return True
        elif choice == "1":
            self.breadcrumb = ["Menu Principal", "Jogos & Previsões"]
            return self.show_games_menu()
        elif choice == "2":
            self.breadcrumb = ["Menu Principal", "Análise Avançada"]
            return self.show_analysis_menu()
        elif choice == "3":
            self.breadcrumb = ["Menu Principal", "Sistema"]
            return self.show_system_menu()
        
        return True
    
    def show_games_menu(self):
        """Menu de Jogos & Previsões"""
        self.show_header()
        
        menu_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
        menu_table.add_column(justify="center", width=10)
        menu_table.add_column(justify="left", width=40)
        
        menu_table.add_row("[bold cyan]1[/bold cyan]", "📅 Calendário do Dia")
        menu_table.add_row("[bold cyan]2[/bold cyan]", "🔮 Previsões (Modelo Elo)")
        menu_table.add_row("[bold cyan]3[/bold cyan]", "🎯 Análise Completa de Jogo")
        menu_table.add_row("[bold cyan]4[/bold cyan]", "🏥 Lesões do Dia")
        menu_table.add_row("[bold cyan]5[/bold cyan]", "📊 Avaliar Precisão (dia passado)")
        
        console.print(Panel(menu_table, title="🎯 Jogos & Previsões", border_style="cyan", box=box.ROUNDED))
        console.print("\n[dim]Digite 'b' para voltar | 'q' para sair[/dim]")
        
        choice = Prompt.ask("\n[bold cyan]➤[/bold cyan]", choices=["1", "2", "3", "4", "5", "b", "q"])
        
        if choice == "q":
            return self.confirm_exit()
        elif choice == "b":
            self.breadcrumb = []
            return True
        
        # Processar opções
        data = _pedir_data("📅 Data", allow_empty=True)
        
        if choice == "1":
            ver_calendario_espn(data)
        elif choice == "2":
            self.run_predictions_enhanced(data)
        elif choice == "3":
            self.run_game_analysis_enhanced(data)
        elif choice == "4":
            ver_lesoes_do_dia(data)
        elif choice == "5":
            self.avaliar_previsoes_enhanced(data)
        
        Prompt.ask("\n[dim]Pressiona Enter para continuar[/dim]")
        return self.show_games_menu()
    
    def show_analysis_menu(self):
        """Menu de Análise Avançada"""
        self.show_header()
        
        menu_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
        menu_table.add_column(justify="center", width=10)
        menu_table.add_column(justify="left", width=40)
        
        menu_table.add_row("[bold yellow]1[/bold yellow]", "🏆 Rankings Elo")
        menu_table.add_row("[bold yellow]2[/bold yellow]", "⭐ Top 50 Jogadores")
        menu_table.add_row("[bold yellow]3[/bold yellow]", "📊 Distribuição de Tiers")
        menu_table.add_row("[bold yellow]4[/bold yellow]", "👥 Ver Plantel de Equipa")
        menu_table.add_row("[bold yellow]5[/bold yellow]", "📈 Stats Detalhadas de Equipa")
        menu_table.add_row("[bold yellow]6[/bold yellow]", "🔍 Pesquisar Jogador")
        
        console.print(Panel(menu_table, title="📊 Análise Avançada", border_style="yellow", box=box.ROUNDED))
        console.print("\n[dim]Digite 'b' para voltar | 'q' para sair[/dim]")
        
        choice = Prompt.ask("\n[bold yellow]➤[/bold yellow]", choices=["1", "2", "3", "4", "5", "6", "b", "q"])
        
        if choice == "q":
            return self.confirm_exit()
        elif choice == "b":
            self.breadcrumb = []
            return True
        
        if choice == "1":
            ver_rankings_elo()
        elif choice == "2":
            season = Prompt.ask("📅 Época", default="2025-26")
            show_top_players(season, top_n=50)
        elif choice == "3":
            season = Prompt.ask("📅 Época", default="2025-26")
            show_tier_distribution(season)
        elif choice == "4":
            team = Prompt.ask("🏀 Equipa (ex: BOS)").upper()
            season = Prompt.ask("📅 Época", default="2025-26")
            self.show_team_roster_enhanced(team, season)
        elif choice == "5":
            team = Prompt.ask("🏀 Equipa (ex: BOS)").upper()
            season = Prompt.ask("📅 Época", default="2025-26")
            compare = Confirm.ask("Comparar com época anterior?", default=True)
            ver_estatisticas_equipa_detalhado(team, season, compare)
        elif choice == "6":
            self.search_player()
        
        Prompt.ask("\n[dim]Pressiona Enter para continuar[/dim]")
        return self.show_analysis_menu()
    
    def show_system_menu(self):
        """Menu de Sistema"""
        self.show_header()
    
        menu_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
        menu_table.add_column(justify="center", width=10)
        menu_table.add_column(justify="left", width=40)
    
        menu_table.add_row("[bold blue]1[/bold blue]", "🔄 Atualizar Histórico Elo")
        menu_table.add_row("[bold blue]2[/bold blue]", "⭐ Atualizar Player Tiers")
        menu_table.add_row("[bold blue]3[/bold blue]", "📋 Listar Todas as Equipas")
        menu_table.add_row("[bold blue]4[/bold blue]", "🗑️  Limpar Cache")
        menu_table.add_row("[bold blue]5[/bold blue]", "📊 Estatísticas do Sistema")
    
        console.print(Panel(menu_table, title="⚙️  Sistema", border_style="blue", box=box.ROUNDED))
        console.print("\n[dim]Digite 'b' para voltar | 'q' para sair[/dim]")
    
        choice = Prompt.ask("\n[bold blue]➤[/bold blue]", choices=["1", "2", "3", "4", "5", "b", "q"])
    
        if choice == "q":
            return self.confirm_exit()
        elif choice == "b":
            self.breadcrumb.pop() 
            return True
    
        if choice == "1":
            self.update_elo_interactive()
        elif choice == "2":
            self.update_tiers_interactive()
        elif choice == "3":
            listar_equipas()
        elif choice == "4":
            self.clear_cache()
        elif choice == "5":
            self.show_system_stats()
    
        Prompt.ask("\n[dim]Pressiona Enter para continuar[/dim]")
        return self.show_system_menu()
    
    def show_main_menu(self):
        """Menu principal - 3 opções principais"""
        self.show_header()
        self.show_quick_info()
    
        menu_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
        menu_table.add_column(justify="center", width=10)
        menu_table.add_column(justify="left", width=30)
        menu_table.add_column(justify="left", style="dim", width=40)
    
        menu_table.add_row(
            "[bold cyan]1[/bold cyan]",
            "🎯 [bold]Jogos & Previsões[/bold]",
            "Ver jogos, previsões e análises"
        )
        menu_table.add_row(
            "[bold yellow]2[/bold yellow]",
            "📊 [bold]Análise Estatística[/bold]",
            "Rankings, stats, análises detalhadas"
        )
        menu_table.add_row(
            "[bold blue]3[/bold blue]",
            "⚙️  [bold]Sistema[/bold]",
            "Configurações e manutenção"
        )
    
        console.print(Panel(menu_table, title="📋 Menu Principal", border_style="cyan", box=box.ROUNDED))
        console.print("\n[dim]Digite 'q' para sair | 'h' para ajuda[/dim]")
    
        choice = Prompt.ask("\n[bold cyan]➤[/bold cyan] Escolhe uma opção", choices=["1", "2", "3", "q", "h"])
    
        if choice == "q":
            return self.confirm_exit()
        elif choice == "h":
            self.show_help()
            return True
        elif choice == "1":
            self.breadcrumb = ["Menu Principal", "Jogos & Previsões"]
            return self.show_games_menu()
        elif choice == "2":
            self.breadcrumb = ["Menu Principal", "Análise Estatística"]
            return self.show_analysis_menu()
        elif choice == "3":
            self.breadcrumb = ["Menu Principal", "Sistema"]
            return self.show_system_menu()
    
        return True
    
    # ═══════════════════════════════════════════════════════════════
    #                    🔧 FUNÇÕES MELHORADAS
    # ═══════════════════════════════════════════════════════════════
    
    def run_predictions_enhanced(self, data: str):
        """Previsões com loading e formatação melhorada"""
        with console.status(f"[cyan]🔮 A gerar previsões para {data}...", spinner="dots"):
            # Auto-update Elo
            try:
                ontem = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
                inicio_epoca = _inicio_epoca_para(data)
                atualizar_elos_historico(inicio_epoca, ontem, force_full=False)
            except Exception:
                pass
            
            jogos_df = calendario_df_espn(data)
        
        if jogos_df.empty:
            console.print(f"\n[yellow]📅 Nenhum jogo em {data}[/yellow]")
            return
        
        resultados_df = prever_vencedor_para_data(jogos_df)
        
        # Tabela melhorada
        self._show_predictions_table(resultados_df, data)
    
    def _show_predictions_table(self, df: pd.DataFrame, data: str):
        """Tabela de previsões otimizada"""
        table = Table(
            title=f"🔮 Previsões NBA — {data}",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan",
            title_style="bold cyan"
        )
        
        table.add_column("Jogo", style="bold", width=20)
        table.add_column("Previsto", justify="center", style="bold green", width=8)
        table.add_column("Prob.", justify="center", width=8)
        table.add_column("Conf.", justify="center", width=10)
        table.add_column("Fatores", justify="left", width=25)
        
        stats = {"total": len(df), "high_conf": 0, "b2b": 0, "injuries": 0}
        
        for _, row in df.iterrows():
            # Calcular confiança
            max_prob = max(row['prob_home'], row['prob_away'])
            if max_prob >= 0.70:
                conf = "🔥 Alta"
                stats["high_conf"] += 1
            elif max_prob >= 0.60:
                conf = "✓ Média"
            else:
                conf = "⚠️  Baixa"
            
            # Fatores ativos
            fatores = []
            if row.get('home_rest_adj', 0) != 0 or row.get('away_rest_adj', 0) != 0:
                fatores.append("🔴 B2B")
                stats["b2b"] += 1
            if row.get('home_injury_adj', 0) != 0 or row.get('away_injury_adj', 0) != 0:
                fatores.append("🏥 Lesões")
                stats["injuries"] += 1
            if abs(row['elo_home'] - row['elo_away']) > 100:
                fatores.append("⚡ Disparidade Elo")
            
            fatores_str = " ".join(fatores) if fatores else "[dim]—[/dim]"
            
            # Linha da tabela
            jogo = f"{row['home']} vs {row['away']}"
            previsto = row['vencedor_previsto']
            prob = f"{max_prob:.1%}"
            
            table.add_row(jogo, previsto, prob, conf, fatores_str)
        
        console.print(table)
        
        # Summary footer
        summary = (
            f"\n[dim]📊 {stats['total']} jogos | "
            f"🔥 {stats['high_conf']} alta confiança | "
            f"🔴 {stats['b2b']} B2B | "
            f"🏥 {stats['injuries']} com lesões[/dim]"
        )
        console.print(summary)
    
    def run_game_analysis_enhanced(self, data: str):
        """Análise de jogo melhorada"""
        resultado = listar_e_escolher_jogo(data)
        
        if not resultado:
            return
        
        home, away = resultado
        
        with console.status(f"[cyan]🔍 A analisar {home} vs {away}...", spinner="dots"):
            analise = analisar_jogo_completo(home, away, data)
        
        mostrar_analise_visual(analise)
    
    def show_team_roster_enhanced(self, team: str, season: str):
        """Plantel com destaque para lesões"""
        team_id = _get_team_id(team)
        if not team_id:
            console.print(f"[red]❌ Equipa '{team}' não encontrada[/red]")
            return
        
        ver_plantel(team_id, season)
    
    def update_elo_interactive(self):
        """Update Elo interativo melhorado"""
        console.print("\n[bold blue]🔄 Atualização de Histórico Elo[/bold blue]\n")
        
        mode_table = Table(show_header=False, box=box.SIMPLE)
        mode_table.add_column(width=5)
        mode_table.add_column(width=50)
        mode_table.add_row("[1]", "⚡ Incremental (rápido - recomendado)")
        mode_table.add_row("[2]", "🔄 Recalcular tudo (lento)")
        
        console.print(mode_table)
        
        mode = Prompt.ask("\n[bold blue]➤[/bold blue] Modo", choices=["1", "2"], default="1")
        force_full = (mode == "2")
        
        if force_full and not Confirm.ask("\n[yellow]⚠️  Recalcular apaga o progresso. Confirma?[/yellow]"):
            return
        
        inicio = Prompt.ask("📅 Data início (YYYY-MM-DD)")
        fim = Prompt.ask("📅 Data fim (YYYY-MM-DD)")
        
        with console.status("[cyan]🔄 A processar histórico...", spinner="dots"):
            atualizar_elos_historico(inicio, fim, force_full=force_full)
        
        console.print("\n[bold green]✅ Histórico atualizado com sucesso![/bold green]")
    
    def update_tiers_interactive(self):
        """Update tiers interativo"""
        console.print("\n[bold yellow]⭐ Atualização de Player Tiers[/bold yellow]")
        console.print("[dim]Este processo pode demorar alguns minutos...[/dim]\n")
        
        seasons_input = Prompt.ask(
            "📅 Épocas (separadas por vírgula)",
            default="2024-25,2025-26"
        )
        
        seasons = [s.strip() for s in seasons_input.split(",")]
        
        with console.status("[yellow]⭐ A atualizar tiers...", spinner="dots"):
            update_all_tiers(seasons)
        
        console.print("\n[bold green]✅ Tiers atualizados![/bold green]")
    
    def avaliar_previsoes_enhanced(self, data: str):
        """Avaliação com visualização melhorada"""
        console.print(f"\n[cyan]📊 A avaliar previsões de {data}...[/cyan]\n")
        
        stats = avaliar_previsoes_para_data(data)
        
        if not stats or stats.get("jogos", 0) == 0:
            console.print(f"[yellow]Sem jogos finalizados em {data}[/yellow]")
            return
        
        # Painel de resultados
        accuracy_color = "green" if stats['acerto'] >= 0.65 else "yellow" if stats['acerto'] >= 0.55 else "red"
        
        panel_content = (
            f"[bold]Jogos Avaliados:[/bold] {stats['jogos']}\n\n"
            f"[bold {accuracy_color}]Precisão:[/bold {accuracy_color}] {stats['acerto']:.1%}\n"
            f"[bold blue]Brier Score:[/bold blue] {stats['brier']:.4f}\n\n"
            f"[dim]Contexto:[/dim]\n"
            f"  • Back-to-backs: {stats.get('back_to_backs', 0)}\n"
            f"  • Jogos com lesões: {stats.get('injuries_impact', 0)}\n"
            f"  • K-factor usado: {stats.get('k_factor', 20)}"
        )
        
        console.print(Panel(
            panel_content,
            title=f"📊 Avaliação — {data}",
            border_style=accuracy_color,
            box=box.ROUNDED
        ))
    
    def show_help(self):
        """Sistema de ajuda"""
        self.show_header()
        
        help_content = """
[bold cyan]🏀 GUIA RÁPIDO[/bold cyan]

[bold]Navegação:[/bold]
  • Números (1-6) - Selecionar opção
  • 'b' - Voltar ao menu anterior
  • 'q' - Sair do programa
  • 'h' - Mostrar esta ajuda

[bold]Previsões:[/bold]
  Sistema Elo com ajustes de:
  • MOV (Margin of Victory)
  • Rest (Back-to-backs, fadiga)
  • Injuries (baseado em tiers)
  • Home court advantage

[bold]Datas:[/bold]
  • Enter = hoje
  • Formato: YYYY-MM-DD ou DD-MM-YYYY
  • Exemplo: 2025-12-25 ou 25-12-2025

[bold]Suporte:[/bold]
  GitHub: [link]seu_repo[/link]
        """
        
        console.print(Panel(help_content, title="❓ Ajuda", border_style="cyan", box=box.ROUNDED))
    
    def search_player(self):
        """Pesquisa de jogador (placeholder)"""
        player = Prompt.ask("🔍 Nome do jogador")
        console.print(f"\n[yellow]🚧 Pesquisa por '{player}' em desenvolvimento[/yellow]")
    
    def clear_cache(self):
        """Limpar cache"""
        if Confirm.ask("\n[yellow]Limpar todo o cache?[/yellow]"):
            import shutil
            cache_dir = Path("data/cache")
            if cache_dir.exists():
                shutil.rmtree(cache_dir)
                cache_dir.mkdir()
                console.print("[green]✅ Cache limpo![/green]")
    
    def show_system_stats(self):
        """Estatísticas do sistema"""
        console.print("\n[bold]📊 Estatísticas do Sistema[/bold]\n")
        console.print("[dim]Loading...[/dim]")
    
    def show_settings(self):
        """Configurações (placeholder)"""
        console.print("\n[yellow]🚧 Configurações em desenvolvimento[/yellow]")
    
    def confirm_exit(self):
        """Confirmação de saída"""
        if Confirm.ask("\n[yellow]Tens a certeza que queres sair?[/yellow]"):
            console.print("\n[bold green]👋 Até já! Boas apostas! 🍀[/bold green]\n")
            return False
        return True
    
    def run(self):
        """Loop principal"""
        while True:
            try:
                if not self.show_main_menu():
                    break
            except KeyboardInterrupt:
                console.print("\n[yellow]⚠️  Operação cancelada[/yellow]")
                Prompt.ask("[dim]Enter para continuar[/dim]")
            except Exception as e:
                console.print(f"\n[red]❌ Erro: {e}[/red]")
                if Confirm.ask("Ver detalhes?"):
                    import traceback
                    console.print(f"[dim]{traceback.format_exc()}[/dim]")
                Prompt.ask("[dim]Enter para continuar[/dim]")


# ═══════════════════════════════════════════════════════════════
#                        🚀 ENTRY POINT
# ═══════════════════════════════════════════════════════════════

@app.command("listar-equipas")
def listar_equipas_cmd():
    """Listar todas as equipas NBA"""
    listar_equipas()


@app.command()
def menu():
    """Iniciar o menu interativo"""
    menu_system = MenuSystem()
    menu_system.run()


if __name__ == "__main__":
    app()

