# services/roster.py

from nba_api.stats.endpoints import commonteamroster
from rich.table import Table
from rich.console import Console
import pandas as pd  # se vaires usar pandas


def get_team_roster(team_id: int, season: str = "2025-26"):
    ct = commonteamroster.CommonTeamRoster(team_id=team_id, season=season, league_id_nullable="00")
    df = ct.get_data_frames()[0]
    return df

def height_to_m(height_str: str) -> float:
    try:
        feet, inches = height_str.split('-')
        return int(feet)*0.3048 + int(inches)*0.0254
    except:
        return None

def weight_to_kg(weight_str: str) -> float:
    try:
        return int(weight_str) * 0.453592
    except:
        return None

def ver_plantel(team_id: int, season: str = "2025-26"):
    df = get_team_roster(team_id=team_id, season=season)
    # converter colunas
    df["HEIGHT_M"] = df["HEIGHT"].apply(height_to_m)
    df["WEIGHT_KG"] = df["WEIGHT"].apply(weight_to_kg)

    # ordenar por posição
    pos_order = {"G":0, "G-F":1, "F":2, "F-C":3, "C":4}
    df["pos_rank"] = df["POSITION"].map(lambda x: pos_order.get(x, 99))
    df = df.sort_values(by=["pos_rank", "PLAYER"])

    # Colunas na ordem escolhida mais as novas
    cols = ["SEASON", "PLAYER", "NUM", "POSITION", "HEIGHT_M", "WEIGHT_KG", "AGE", "SCHOOL", "HOW_ACQUIRED"]
    available = [c for c in cols if c in df.columns]
    df2 = df[available]

    # Mostrar tabela com rich
    table = Table(title=f"Plantel da Equipa {team_id} — Época {season}")
    for c in available:
        table.add_column(c)
    console = Console()
    for _, row in df2.iterrows():
        # Formatar valores para visual
        height_fmt = f"{row['HEIGHT_M']:.2f} m" if row.get('HEIGHT_M') is not None else ""
        weight_fmt = f"{row['WEIGHT_KG']:.1f} kg" if row.get('WEIGHT_KG') is not None else ""
        table.add_row(
            str(row["SEASON"]),
            row["PLAYER"],
            str(row["NUM"]),
            row["POSITION"],
            height_fmt,
            weight_fmt,
            str(row["AGE"]),
            row["SCHOOL"],
            row["HOW_ACQUIRED"]
        )
    console.print(table)
