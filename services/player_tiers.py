# services/player_tiers.py - SISTEMA DE TIERS DINÂMICO COMPLETO
"""
Sistema automático de classificação de jogadores em tiers.
Baseado em stats reais de múltiplas épocas.

TIERS:
- SUPERSTAR: Elite da liga (Top 15)
- STAR: All-Star level (Top 16-40)
- STARTER: Titulares sólidos (Top 41-100)
- ROTATION: Rotação regular (Top 101-200)
- BENCH: Suplentes (Resto)

METODOLOGIA:
Usa um score composto baseado em:
- PTS (30%): Pontos por jogo
- EFF (25%): Efficiency rating
- IMPACT (20%): Plus/Minus e Win Shares proxy
- ADVANCED (15%): TS%, USG
- ALL-AROUND (10%): REB + AST + STL + BLK
"""

from typing import Dict, List, Tuple, Optional, Literal
import pandas as pd
import json
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from services.stats import get_player_stats

console = Console()

# Paths
TIERS_DIR = Path("data/tiers")
TIERS_DIR.mkdir(parents=True, exist_ok=True)

# Configuração de tiers
TIER_CONFIG = {
    "SUPERSTAR": {
        "threshold": 15,  # Top 15 jogadores
        "elo_impact": -60,  # Impacto quando ausente
        "color": "bold red",
        "icon": "⭐⭐⭐"
    },
    "STAR": {
        "threshold": 40,  # Top 16-40
        "elo_impact": -40,
        "color": "bold yellow",
        "icon": "⭐⭐"
    },
    "STARTER": {
        "threshold": 100,  # Top 41-100
        "elo_impact": -25,
        "color": "green",
        "icon": "⭐"
    },
    "ROTATION": {
        "threshold": 200,  # Top 101-200
        "elo_impact": -12,
        "color": "blue",
        "icon": "◆"
    },
    "BENCH": {
        "threshold": float('inf'),  # Resto
        "elo_impact": -5,
        "color": "dim",
        "icon": "○"
    }
}

# Pesos para cálculo do score composto
WEIGHTS = {
    "PTS": 0.30,
    "EFF": 0.25,
    "IMPACT": 0.20,
    "ADVANCED": 0.15,
    "ALL_AROUND": 0.10
}


def calculate_player_score(row: pd.Series) -> float:
    """
    Calcula score composto para um jogador.
    
    Score = weighted sum of normalized components
    """
    score = 0.0
    
    # 1. SCORING (30%)
    pts = row.get("PTS", 0)
    score += WEIGHTS["PTS"] * pts
    
    # 2. EFFICIENCY (25%)
    eff = row.get("EFF", 0)
    score += WEIGHTS["EFF"] * (eff / 2.0)  # Normalizar
    
    # 3. IMPACT (20%)
    # Proxy: Plus/Minus é o mais direto, mas também considerar minutes
    plus_minus = row.get("PLUS_MINUS", 0)
    minutes = row.get("MIN", 0)
    impact = plus_minus * (minutes / 36)  # Ajustar por minutos
    score += WEIGHTS["IMPACT"] * impact
    
    # 4. ADVANCED METRICS (15%)
    ts_pct = row.get("TS_PCT", 0)
    usg = row.get("USG_APPROX", 0)
    advanced = (ts_pct * 100) + (usg * 50)  # Normalizar
    score += WEIGHTS["ADVANCED"] * advanced
    
    # 5. ALL-AROUND (10%)
    reb = row.get("REB", 0)
    ast = row.get("AST", 0)
    stl = row.get("STL", 0)
    blk = row.get("BLK", 0)
    all_around = reb + ast + (stl * 2) + (blk * 2)
    score += WEIGHTS["ALL_AROUND"] * all_around
    
    return score


def classify_players(
    season: str = "2025-26",
    min_games: int = 5,
    min_minutes: float = 10.0,
    use_multi_season: bool = True
) -> pd.DataFrame:
    """
    Classifica TODOS os jogadores da NBA em tiers.
    
    Args:
        season: Época principal
        min_games: Mínimo de jogos para qualificar
        min_minutes: Minutos mínimos por jogo
        use_multi_season: Usar média de 2 épocas (atual + anterior)?
    
    Returns:
        DataFrame com: PLAYER_NAME, TEAM, SCORE, TIER, ELO_IMPACT
    """
    console.print(f"[cyan]🔍 A classificar jogadores da época {season}...[/cyan]")
    
    # Obter stats da época atual
    df_current = get_player_stats(
        season=season,
        per_mode="PerGame",
        min_games=min_games,
        min_minutes=min_minutes,
        use_cache=False
    )
    
    if df_current.empty:
        console.print("[red]Sem dados disponíveis[/red]")
        return pd.DataFrame()
    
    # Se usar multi-season, obter época anterior também
    if use_multi_season:
        current_year = int(season.split("-")[0])
        prev_season = f"{current_year-1}-{str(current_year)[-2:]}"
        
        console.print(f"[dim]  Incluindo dados de {prev_season} para estabilidade...[/dim]")
        
        df_prev = get_player_stats(
            season=prev_season,
            per_mode="PerGame",
            min_games=10,
            min_minutes=15.0
        )
        
        if not df_prev.empty:
            # Antes do merge, copiar jogadores que não jogaram ainda este ano
            players_current = set(df_current["PLAYER_NAME"])
            players_prev = set(df_prev["PLAYER_NAME"])
            missing_players = players_prev - players_current
            
            if missing_players:
                console.print(f"[dim]  ⚠️ {len(missing_players)} jogadores ainda não jogaram em {season}, a usar dados de {prev_season}[/dim]")
                
                # Adicionar estes jogadores ao df_current com dados da época anterior
                df_missing = df_prev[df_prev["PLAYER_NAME"].isin(missing_players)].copy()
                df_current = pd.concat([df_current, df_missing], ignore_index=True)
            
            # Merge por PLAYER_NAME
            df_merged = df_current.merge(
                df_prev[["PLAYER_NAME", "PTS", "EFF", "PLUS_MINUS", "MIN", "REB", "AST", "STL", "BLK", "TS_PCT"]],
                on="PLAYER_NAME",
                how="left",
                suffixes=("", "_prev")
            )
            
            # Calcular médias ponderadas para métricas key
            for col in ["PTS", "EFF", "PLUS_MINUS", "MIN", "REB", "AST", "STL", "BLK", "TS_PCT"]:
                if f"{col}_prev" in df_merged.columns:
                    # Se tem época anterior: 70% atual + 30% anterior
                    # Se não tem: 100% atual
                    df_merged[col] = df_merged.apply(
                        lambda row: (
                            0.7 * row[col] + 0.3 * row[f"{col}_prev"]
                            if pd.notna(row[f"{col}_prev"]) and pd.notna(row[col])
                            else row[col] if pd.notna(row[col])
                            else row[f"{col}_prev"] if pd.notna(row[f"{col}_prev"])
                            else 0
                        ),
                        axis=1
                    )
            
            df_current = df_merged
            console.print(f"[dim]  ✓ Média ponderada aplicada a {len(df_prev)} jogadores[/dim]")
        else:
            console.print(f"[yellow]  ⚠️ Época anterior sem dados, usando apenas {season}[/yellow]")
    
    # Calcular scores
    df_current["PLAYER_SCORE"] = df_current.apply(calculate_player_score, axis=1)
    
    # Ordenar por score
    df_current = df_current.sort_values("PLAYER_SCORE", ascending=False)
    
    # Atribuir tiers
    tiers = []
    elo_impacts = []
    
    for idx, _ in enumerate(df_current.iterrows(), 1):
        if idx <= TIER_CONFIG["SUPERSTAR"]["threshold"]:
            tier = "SUPERSTAR"
        elif idx <= TIER_CONFIG["STAR"]["threshold"]:
            tier = "STAR"
        elif idx <= TIER_CONFIG["STARTER"]["threshold"]:
            tier = "STARTER"
        elif idx <= TIER_CONFIG["ROTATION"]["threshold"]:
            tier = "ROTATION"
        else:
            tier = "BENCH"
        
        tiers.append(tier)
        elo_impacts.append(TIER_CONFIG[tier]["elo_impact"])
    
    df_current["TIER"] = tiers
    df_current["ELO_IMPACT"] = elo_impacts
    
    # Selecionar colunas finais
    final_cols = [
        "PLAYER_NAME", "TEAM_ABBREVIATION", "GP", "MIN", "PTS", "REB", "AST",
        "EFF", "TS_PCT", "PLUS_MINUS", "PLAYER_SCORE", "TIER", "ELO_IMPACT"
    ]
    
    available_cols = [c for c in final_cols if c in df_current.columns]
    
    result = df_current[available_cols].copy()
    
    console.print(f"[green]✓ {len(result)} jogadores classificados[/green]")
    
    return result


def save_tiers(df: pd.DataFrame, season: str) -> None:
    """Guarda classificação de tiers em JSON."""
    output_file = TIERS_DIR / f"player_tiers_{season.replace('-', '_')}.json"
    
    # Converter para formato dict mais limpo
    tiers_dict = {}
    seen_players = set()
    
    for _, row in df.iterrows():
        player_name = row["PLAYER_NAME"]
        
        # Normalizar nome (remover acentos, espaços extras)
        import unicodedata
        normalized_name = unicodedata.normalize('NFKD', player_name).encode('ASCII', 'ignore').decode('ASCII')
        normalized_name = ' '.join(normalized_name.split())
        
        # Se já existe, manter o melhor (maior score)
        if normalized_name in tiers_dict:
            existing_score = tiers_dict[normalized_name]["score"]
            new_score = float(row["PLAYER_SCORE"])
            
            if new_score > existing_score:
                console.print(f"[dim]⚠️ Duplicado: {player_name} (score {new_score:.1f} > {existing_score:.1f}), a usar novo[/dim]")
                tiers_dict[normalized_name] = {
                    "tier": row["TIER"],
                    "elo_impact": int(row["ELO_IMPACT"]),
                    "score": new_score,
                    "team": row.get("TEAM_ABBREVIATION", ""),
                    "ppg": float(row.get("PTS", 0))
                }
            else:
                console.print(f"[dim]⚠️ Duplicado: {player_name} (score {new_score:.1f} < {existing_score:.1f}), a manter existente[/dim]")
        else:
            tiers_dict[normalized_name] = {
                "tier": row["TIER"],
                "elo_impact": int(row["ELO_IMPACT"]),
                "score": float(row["PLAYER_SCORE"]),
                "team": row.get("TEAM_ABBREVIATION", ""),
                "ppg": float(row.get("PTS", 0))
            }
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(tiers_dict, f, indent=2, ensure_ascii=False)
    
    console.print(f"[green]✓ Tiers guardados em {output_file}[/green]")


def load_tiers(season: str = "2025-26") -> Dict:
    """
    Carrega tiers guardados.
    IMPORTANTE: Normaliza nomes das keys para matching consistente.
    """
    tier_file = TIERS_DIR / f"player_tiers_{season.replace('-', '_')}.json"
    
    if not tier_file.exists():
        console.print(f"[yellow]⚠️  Tiers de {season} não encontrados. A gerar...[/yellow]")
        df = classify_players(season)
        save_tiers(df, season)
        return load_tiers(season)
    
    with open(tier_file, "r", encoding="utf-8") as f:
        raw_tiers = json.load(f)
    
    # Criar versão com keys normalizadas para lookup rápido
    normalized_tiers = {}
    for name, data in raw_tiers.items():
        normalized_name = _normalize_player_name(name)
        normalized_tiers[normalized_name] = data
    
    return normalized_tiers


def get_player_tier(player_name: str, season: str = "2025-26") -> Optional[str]:
    """Obtém tier de um jogador específico."""
    tiers = load_tiers(season)
    normalized_name = _normalize_player_name(player_name)
    return tiers.get(normalized_name, {}).get("tier")


def _normalize_player_name(name: str) -> str:
    """
    Normaliza nome de jogador para matching consistente.
    Remove acentos, espaços extras, etc.
    """
    import unicodedata
    # Remover acentos
    normalized = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('ASCII')
    # Remover espaços extras
    normalized = ' '.join(normalized.split())
    return normalized


def get_player_elo_impact(player_name: str, season: str = "2025-26", silent: bool = False) -> int:
    """
    Obtém impacto Elo de um jogador.
    
    Com fallback: se não encontrar na época atual, procura na anterior.
    
    Args:
        player_name: Nome do jogador
        season: Época (ex: "2025-26")
        silent: Se True, não mostra avisos de fallback
    """
    tiers = load_tiers(season)
    normalized_name = _normalize_player_name(player_name)
    impact = tiers.get(normalized_name, {}).get("elo_impact")
    
    if impact is not None:
        return impact
    
    # FALLBACK: Tentar época anterior
    current_year = int(season.split("-")[0])
    prev_season = f"{current_year-1}-{str(current_year)[-2:]}"
    
    try:
        prev_tiers = load_tiers(prev_season)
        prev_impact = prev_tiers.get(normalized_name, {}).get("elo_impact")
        
        if prev_impact is not None:
            # Só avisar se for jogador importante (STAR ou melhor) e não silent
            if not silent and prev_impact <= -40:
                console.print(f"[dim]⚠️ {player_name}: usando tier de {prev_season} ({prev_impact})[/dim]")
            return prev_impact
    except Exception:
        pass
    
    # Default: bench player
    return -5


def update_all_tiers(seasons: List[str] = None) -> None:
    """
    Atualiza tiers para múltiplas épocas.
    
    Args:
        seasons: Lista de épocas (None = atual + anterior)
    """
    if seasons is None:
        current_year = datetime.now().year
        seasons = [
            f"{current_year-1}-{str(current_year)[-2:]}",  # Época atual
            f"{current_year-2}-{str(current_year-1)[-2:]}"  # Época anterior
        ]
    
    console.print(f"\n[bold cyan]🔄 A atualizar tiers para {len(seasons)} épocas...[/bold cyan]\n")
    
    for season in seasons:
        console.print(f"[yellow]📅 Época {season}[/yellow]")
        
        # Usar multi-season para épocas em curso
        current_year = datetime.now().year
        season_year = int(season.split("-")[0])
        
        # Se é época atual/recente (< 20 jogos), usar dados da época anterior também
        use_multi = (current_year - season_year <= 1)
        
        if use_multi:
            console.print(f"[dim]  Usando média ponderada com época anterior (70% atual / 30% anterior)[/dim]")
        
        # Tentar com filtros relaxados primeiro
        df = classify_players(season, min_games=1, min_minutes=5.0, use_multi_season=use_multi)
        
        if df.empty:
            console.print(f"[red]  ❌ Sem dados para {season} (a época pode não ter começado)[/red]\n")
            continue
        
        save_tiers(df, season)
        
        # Stats resumidas
        tier_counts = df["TIER"].value_counts()
        console.print(f"[dim]  SUPERSTAR: {tier_counts.get('SUPERSTAR', 0)} | "
                     f"STAR: {tier_counts.get('STAR', 0)} | "
                     f"STARTER: {tier_counts.get('STARTER', 0)}[/dim]\n")


def show_tier_distribution(season: str = "2025-26") -> None:
    """Mostra distribuição visual de tiers."""
    df = classify_players(season)
    
    if df.empty:
        return
    
    console.print(f"\n[bold]📊 DISTRIBUIÇÃO DE TIERS — {season}[/bold]\n")
    
    for tier_name, config in TIER_CONFIG.items():
        tier_df = df[df["TIER"] == tier_name]
        count = len(tier_df)
        
        if count == 0:
            continue
        
        # Stats médias do tier
        avg_ppg = tier_df["PTS"].mean() if "PTS" in tier_df.columns else 0
        avg_eff = tier_df["EFF"].mean() if "EFF" in tier_df.columns else 0
        
        panel_content = (
            f"[{config['color']}]Jogadores: {count}[/{config['color']}]\n"
            f"Impacto Elo: {config['elo_impact']} pontos\n"
            f"Média PPG: {avg_ppg:.1f} | Média EFF: {avg_eff:.1f}"
        )
        
        console.print(Panel(
            panel_content,
            title=f"{config['icon']} {tier_name}",
            box=box.ROUNDED,
            border_style=config['color'].replace('bold ', '')
        ))


def show_top_players(season: str = "2025-26", top_n: int = 50) -> None:
    """Mostra top N jogadores com seus tiers."""
    df = classify_players(season)
    
    if df.empty:
        return
    
    console.print(f"\n[bold cyan]🏆 TOP {top_n} JOGADORES — {season}[/bold cyan]\n")
    
    table = Table(box=box.ROUNDED, show_header=True)
    table.add_column("#", justify="right", style="cyan", width=4)
    table.add_column("Jogador", style="bold", width=20)
    table.add_column("Equipa", justify="center", width=6)
    table.add_column("Tier", justify="center", width=12)
    table.add_column("PPG", justify="right", width=6)
    table.add_column("EFF", justify="right", width=6)
    table.add_column("Score", justify="right", width=8)
    table.add_column("Elo Δ", justify="right", width=7)
    
    for idx, (_, row) in enumerate(df.head(top_n).iterrows(), 1):
        tier = row["TIER"]
        config = TIER_CONFIG[tier]
        
        table.add_row(
            str(idx),
            row["PLAYER_NAME"][:20],
            row.get("TEAM_ABBREVIATION", "")[:6],
            f"[{config['color']}]{config['icon']} {tier}[/{config['color']}]",
            f"{row.get('PTS', 0):.1f}",
            f"{row.get('EFF', 0):.1f}",
            f"{row.get('PLAYER_SCORE', 0):.1f}",
            f"{row['ELO_IMPACT']:+d}"
        )
    
    console.print(table)


def compare_player_tiers(
    player_names: List[str],
    season: str = "2025-26"
) -> None:
    """Compara tiers de múltiplos jogadores."""
    tiers = load_tiers(season)
    
    console.print(f"\n[bold]⚖️ COMPARAÇÃO DE JOGADORES — {season}[/bold]\n")
    
    table = Table(box=box.SIMPLE)
    table.add_column("Jogador", style="bold cyan")
    table.add_column("Tier", justify="center")
    table.add_column("PPG", justify="right")
    table.add_column("Score", justify="right")
    table.add_column("Elo Impact", justify="right", style="bold red")
    
    for name in player_names:
        # Tentar nome original e normalizado
        normalized = _normalize_player_name(name)
        player_data = tiers.get(name) or tiers.get(normalized)
        
        if player_data:
            tier = player_data["tier"]
            config = TIER_CONFIG[tier]
            
            table.add_row(
                name,
                f"[{config['color']}]{config['icon']} {tier}[/{config['color']}]",
                f"{player_data['ppg']:.1f}",
                f"{player_data['score']:.1f}",
                f"{player_data['elo_impact']:+d}"
            )
        else:
            table.add_row(name, "[dim]Não encontrado[/dim]", "-", "-", "-")
    
    console.print(table)


def find_duplicate_players(season: str = "2025-26") -> None:
    """
    Encontra jogadores duplicados no sistema.
    Útil para debug de trades/mudanças de equipa.
    """
    tiers = load_tiers(season)
    
    # Agrupar por nome normalizado
    from collections import defaultdict
    grouped = defaultdict(list)
    
    for name, data in tiers.items():
        normalized = _normalize_player_name(name)
        grouped[normalized].append((name, data))
    
    # Encontrar duplicados
    duplicates = {k: v for k, v in grouped.items() if len(v) > 1}
    
    if not duplicates:
        console.print(f"[green]✓ Sem duplicados encontrados em {season}[/green]")
        return
    
    console.print(f"\n[yellow]⚠️ {len(duplicates)} jogadores duplicados encontrados:[/yellow]\n")
    
    for norm_name, entries in duplicates.items():
        console.print(f"[bold]{norm_name}:[/bold]")
        for orig_name, data in entries:
            console.print(f"  • {orig_name}: {data['tier']} ({data['elo_impact']}) - {data['team']} - Score: {data['score']:.1f}")
        console.print()