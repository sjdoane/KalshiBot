"""Kalshi ticker abbreviation -> the-odds-api full team name maps.

Ticker format: KX{SPORT}-{YY}{MMM}{DD}{TEAM1}{TEAM2}-{WINNER_ABBR}.
Team1+Team2 are concatenated without separator; abbreviation lengths
vary (typically 2-4 chars). Longest-match-first split heuristic.

Maps below are derived from a sample of Becker tickers and verified by
cross-referencing the-odds-api response team names.
"""

from __future__ import annotations


MLB_MAP = {
    "ARI": "Arizona Diamondbacks",
    "AZ": "Arizona Diamondbacks",
    "ATL": "Atlanta Braves",
    "BAL": "Baltimore Orioles",
    "BOS": "Boston Red Sox",
    "CHC": "Chicago Cubs",
    "CWS": "Chicago White Sox",
    "CIN": "Cincinnati Reds",
    "CLE": "Cleveland Guardians",
    "COL": "Colorado Rockies",
    "DET": "Detroit Tigers",
    "HOU": "Houston Astros",
    "KC": "Kansas City Royals",
    "KCG": "Kansas City Royals",
    "LAA": "Los Angeles Angels",
    "LAD": "Los Angeles Dodgers",
    "MIA": "Miami Marlins",
    "MIL": "Milwaukee Brewers",
    "MIN": "Minnesota Twins",
    "NYM": "New York Mets",
    "NYY": "New York Yankees",
    "OAK": "Oakland Athletics",
    "ATH": "Oakland Athletics",
    "PHI": "Philadelphia Phillies",
    "PIT": "Pittsburgh Pirates",
    "SD": "San Diego Padres",
    "SF": "San Francisco Giants",
    "SEA": "Seattle Mariners",
    "STL": "St. Louis Cardinals",
    "TB": "Tampa Bay Rays",
    "TEX": "Texas Rangers",
    "TOR": "Toronto Blue Jays",
    "WSH": "Washington Nationals",
    "WAS": "Washington Nationals",
}


NBA_MAP = {
    "ATL": "Atlanta Hawks",
    "BOS": "Boston Celtics",
    "BKN": "Brooklyn Nets",
    "BRK": "Brooklyn Nets",
    "CHA": "Charlotte Hornets",
    "CHO": "Charlotte Hornets",
    "CHI": "Chicago Bulls",
    "CLE": "Cleveland Cavaliers",
    "DAL": "Dallas Mavericks",
    "DEN": "Denver Nuggets",
    "DET": "Detroit Pistons",
    "GSW": "Golden State Warriors",
    "GS": "Golden State Warriors",
    "HOU": "Houston Rockets",
    "IND": "Indiana Pacers",
    "LAC": "LA Clippers",
    "LAL": "Los Angeles Lakers",
    "MEM": "Memphis Grizzlies",
    "MIA": "Miami Heat",
    "MIL": "Milwaukee Bucks",
    "MIN": "Minnesota Timberwolves",
    "NOP": "New Orleans Pelicans",
    "NO": "New Orleans Pelicans",
    "NYK": "New York Knicks",
    "NY": "New York Knicks",
    "OKC": "Oklahoma City Thunder",
    "ORL": "Orlando Magic",
    "PHI": "Philadelphia 76ers",
    "PHX": "Phoenix Suns",
    "PHO": "Phoenix Suns",
    "POR": "Portland Trail Blazers",
    "SAC": "Sacramento Kings",
    "SAS": "San Antonio Spurs",
    "SA": "San Antonio Spurs",
    "TOR": "Toronto Raptors",
    "UTA": "Utah Jazz",
    "WAS": "Washington Wizards",
    "WSH": "Washington Wizards",
}


NFL_MAP = {
    "ARI": "Arizona Cardinals",
    "ATL": "Atlanta Falcons",
    "BAL": "Baltimore Ravens",
    "BUF": "Buffalo Bills",
    "CAR": "Carolina Panthers",
    "CHI": "Chicago Bears",
    "CIN": "Cincinnati Bengals",
    "CLE": "Cleveland Browns",
    "DAL": "Dallas Cowboys",
    "DEN": "Denver Broncos",
    "DET": "Detroit Lions",
    "GB": "Green Bay Packers",
    "HOU": "Houston Texans",
    "IND": "Indianapolis Colts",
    "JAX": "Jacksonville Jaguars",
    "KC": "Kansas City Chiefs",
    "LV": "Las Vegas Raiders",
    "LAC": "Los Angeles Chargers",
    "LAR": "Los Angeles Rams",
    "MIA": "Miami Dolphins",
    "MIN": "Minnesota Vikings",
    "NE": "New England Patriots",
    "NO": "New Orleans Saints",
    "NYG": "New York Giants",
    "NYJ": "New York Jets",
    "PHI": "Philadelphia Eagles",
    "PIT": "Pittsburgh Steelers",
    "SF": "San Francisco 49ers",
    "SEA": "Seattle Seahawks",
    "TB": "Tampa Bay Buccaneers",
    "TEN": "Tennessee Titans",
    "WAS": "Washington Commanders",
    "WSH": "Washington Commanders",
}


SPORT_MAPS = {
    "KXMLBGAME": MLB_MAP,
    "KXNBAGAME": NBA_MAP,
    "KXNFLGAME": NFL_MAP,
}


def split_team_abbrs(combined: str, sport: str) -> tuple[str, str] | None:
    """Split combined TEAM1+TEAM2 abbreviation into (TEAM1, TEAM2).

    Tries longest-prefix match first. Returns None if no valid split is
    found (caller should drop the event).
    """
    mapping = SPORT_MAPS[sport]
    abbrs_sorted = sorted(mapping.keys(), key=len, reverse=True)
    for abbr1 in abbrs_sorted:
        if combined.startswith(abbr1):
            rest = combined[len(abbr1):]
            if rest in mapping:
                return abbr1, rest
    return None


def map_event_to_team_names(
    event_ticker: str, sport: str
) -> tuple[str, str] | None:
    """Parse a Becker event_ticker into (team1_full, team2_full).

    Event ticker format: KX{SPORT}-{YY}{MMM}{DD}{TEAM1}{TEAM2}.
    Returns None if parsing fails.
    """
    # Strip the sport prefix and dash
    prefix = f"{sport}-"
    if not event_ticker.startswith(prefix):
        return None
    rest = event_ticker[len(prefix):]
    if len(rest) < 7:
        return None
    # First 7 chars are YYMMMDD; team abbrs are after
    teams = rest[7:]
    split = split_team_abbrs(teams, sport)
    if split is None:
        return None
    a, b = split
    mapping = SPORT_MAPS[sport]
    return mapping[a], mapping[b]


def parse_event_date(event_ticker: str, sport: str) -> str | None:
    """Extract YYYY-MM-DD from a Becker event_ticker."""
    prefix = f"{sport}-"
    if not event_ticker.startswith(prefix):
        return None
    rest = event_ticker[len(prefix):]
    if len(rest) < 7:
        return None
    yy, mmm, dd = rest[0:2], rest[2:5], rest[5:7]
    months = {
        "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04",
        "MAY": "05", "JUN": "06", "JUL": "07", "AUG": "08",
        "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
    }
    if mmm not in months:
        return None
    return f"20{yy}-{months[mmm]}-{dd}"
