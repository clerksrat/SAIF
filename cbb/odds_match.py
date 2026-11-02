"""Map The Odds API NCAAB team names ("Texas Tech Red Raiders") to CBBD names ("Texas Tech").

Rule: an Odds API name maps to the CBBD team whose normalized name is the LONGEST prefix of it
(so "Texas Tech Red Raiders" -> "Texas Tech", not "Texas"; "Miami (OH) RedHawks" -> "Miami (OH)").
ALIASES covers schools the two sources spell differently; anything unmapped is printed so it
can be added here.
"""
import re
import unicodedata

# Odds API school spelling (normalized, no mascot) -> CBBD team name
ALIASES = {
    'connecticut': 'UConn', 'uconn': 'UConn', 'miami fl': 'Miami', 'miami oh': 'Miami (OH)',
    'ole miss': 'Ole Miss', 'mississippi': 'Ole Miss', 'pitt': 'Pittsburgh', 'usc': 'USC',
    'southern california': 'USC', 'lsu': 'LSU', 'ucf': 'UCF', 'central florida': 'UCF',
    'smu': 'SMU', 'tcu': 'TCU', 'byu': 'BYU', 'vcu': 'VCU', 'unlv': 'UNLV', 'utep': 'UTEP',
    'utsa': 'UTSA', 'fiu': 'Florida International', 'florida intl': 'Florida International',
    'n carolina': 'North Carolina', 'unc wilmington': 'UNC Wilmington', 'unc greensboro': 'UNC Greensboro',
    'unc asheville': 'UNC Asheville', 'nc state': 'NC State', 'north carolina state': 'NC State',
    'umass': 'Massachusetts', 'umass lowell': 'UMass Lowell', 'umbc': 'UMBC', 'uic': 'UIC',
    'illinois chicago': 'UIC', 'iupui': 'IU Indianapolis', 'iu indy': 'IU Indianapolis',
    'liu': 'Long Island University', 'long island': 'Long Island University',
    'loyola chi': 'Loyola Chicago', 'loyola chicago': 'Loyola Chicago', 'loyola md': 'Loyola Maryland',
    'loyola marymount': 'Loyola Marymount', 'st johns': "St. John's", 'saint johns': "St. John's",
    'st marys': "Saint Mary's", 'saint marys': "Saint Mary's", 'st josephs': "Saint Joseph's",
    'st peters': "Saint Peter's", 'st bonaventure': 'St. Bonaventure', 'st louis': 'Saint Louis',
    'saint louis': 'Saint Louis', 'st thomas mn': 'St. Thomas-Minnesota', 'st thomas': 'St. Thomas-Minnesota',
    'se louisiana': 'SE Louisiana', 'southeastern louisiana': 'SE Louisiana',
    'se missouri st': 'Southeast Missouri State', 'southeast missouri state': 'Southeast Missouri State',
    'texas a m cc': 'Texas A&M-Corpus Christi', 'texas a m corpus christi': 'Texas A&M-Corpus Christi',
    'app state': 'App State', 'appalachian st': 'App State', 'appalachian state': 'App State',
    'cal st fullerton': 'Cal State Fullerton', 'csu fullerton': 'Cal State Fullerton',
    'cal st northridge': 'Cal State Northridge', 'csu northridge': 'Cal State Northridge', 'csun': 'Cal State Northridge',
    'cal st bakersfield': 'Cal State Bakersfield', 'csu bakersfield': 'Cal State Bakersfield',
    'long beach st': 'Long Beach State', 'gw': 'George Washington', 'george washington': 'George Washington',
    'ut martin': 'UT Martin', 'tennessee martin': 'UT Martin', 'ut arlington': 'UT Arlington',
    'ut rio grande valley': 'UT Rio Grande Valley', 'utrgv': 'UT Rio Grande Valley',
    'sfa': 'Stephen F. Austin', 'stephen f austin': 'Stephen F. Austin', 'etsu': 'East Tennessee State',
    'fau': 'Florida Atlantic', 'fgcu': 'Florida Gulf Coast', 'nku': 'Northern Kentucky',
    'siu edwardsville': 'SIU Edwardsville', 'siue': 'SIU Edwardsville', 'southern illinois': 'Southern Illinois',
    'grambling': 'Grambling', 'grambling st': 'Grambling', 'mcneese': 'McNeese', 'mcneese st': 'McNeese',
    'nicholls': 'Nicholls', 'nicholls st': 'Nicholls', 'hawaii': "Hawai'i", 'kansas city': 'Kansas City',
    'umkc': 'Kansas City', 'detroit': 'Detroit Mercy', 'detroit mercy': 'Detroit Mercy',
    'purdue fort wayne': 'Purdue Fort Wayne', 'fort wayne': 'Purdue Fort Wayne',
    'queens': 'Queens University', 'queens nc': 'Queens University',
    'seattle': 'Seattle U', 'seattle u': 'Seattle U', 'albany': 'UAlbany', 'ualbany': 'UAlbany',
    'ul monroe': 'UL Monroe', 'louisiana monroe': 'UL Monroe', 'ul lafayette': 'Louisiana',
    'louisiana lafayette': 'Louisiana', 'arkansas little rock': 'Little Rock', 'ualr': 'Little Rock',
    'nebraska omaha': 'Omaha', 'st francis pa': 'St. Francis (PA)', 'st francis': 'St. Francis (PA)',
    'saint francis': 'St. Francis (PA)', 'mt st marys': "Mount St. Mary's", 'mount st marys': "Mount St. Mary's",
    'southern mississippi': 'Southern Miss', 'cal baptist': 'California Baptist', 'wisc green bay': 'Green Bay',
    'wisconsin green bay': 'Green Bay', 'wisc milwaukee': 'Milwaukee', 'wisconsin milwaukee': 'Milwaukee',
    'tex a m commerce': 'East Texas A&M', 'texas a m commerce': 'East Texas A&M',
}


def norm(s):
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().lower()
    s = s.replace('&', ' ').replace("'", '').replace('.', '')
    s = re.sub(r'[^a-z0-9 ]', ' ', s)
    s = re.sub(r'\bstate\b', 'st', s)          # "Ohio State" / "Ohio St" -> "ohio st"
    return re.sub(r'\s+', ' ', s).strip()


class Matcher:
    def __init__(self, cbbd_teams):
        self.by_norm = {norm(t): t for t in cbbd_teams}
        for a, t in ALIASES.items():
            if t in cbbd_teams:
                self.by_norm.setdefault(norm(a), t)
        self.keys = sorted(self.by_norm, key=len, reverse=True)
        self.cache = {}

    def team(self, odds_name):
        if odds_name not in self.cache:
            o = norm(odds_name)
            hit = next((k for k in self.keys if o == k or o.startswith(k + ' ')), None)
            self.cache[odds_name] = self.by_norm[hit] if hit else None
        return self.cache[odds_name]
