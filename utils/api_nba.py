from nba_api.stats.endpoints import commonteamroster
import pandas as pd

def get_team_roster(team_id: int, season: str = "2025-26"):
    ct = commonteamroster.CommonTeamRoster(team_id=team_id, season=season, league_id_nullable="00")
    df = ct.get_data_frames()[0]

    return df
