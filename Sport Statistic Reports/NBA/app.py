import ast
import json
import numpy as np
import pandas as pd
from datetime import datetime
import plotly.graph_objects as go
from flask import Flask, render_template
from plotly.utils import PlotlyJSONEncoder

app = Flask(__name__)

"""
Data loading and preprocessing
"""
current_date = datetime.now().strftime("%d-%m-%y")
try :
    def convert_string_to_list(string):
        try:
            return ast.literal_eval(string)
        except ValueError:
            return []
        
    ### If the app is already launched in the current date, load saved data
    data = pd.read_csv("nba_adv_stats_"+current_date+".csv")
    ### Convert list in string format into List object
    data['offensive_rating'] = data.offensive_rating.apply(convert_string_to_list)
    data['defensive_rating'] = data.defensive_rating.apply(convert_string_to_list)
    print("Statistics of",current_date, "loaded.")

except :
    ### Get All teams
    print("**IN**")
    from nba_api.stats.static import teams

    nba_teams = teams.get_teams()

    ### Get games of current season
    from nba_api.stats.endpoints import leaguegamefinder
    games_per_team = []
    for team in nba_teams:
        gamefinder = leaguegamefinder.LeagueGameFinder(team_id_nullable=team['id'])
        games = gamefinder.get_data_frames()[0]
        games.GAME_DATE = pd.to_datetime(games.GAME_DATE)
        ### Here i choose games from the current 2023-2024 Season (without pre-season games)
        games_per_team.append(games[(games.SEASON_ID == '22023') & (games.GAME_DATE >= '2023-10-24')])

    ### Get the Offensive rating, the Defensive rating and other relative stats
    from nba_api.stats.endpoints import boxscoreadvancedv3

    target_stats = []
    for team in games_per_team:
        ### Take number of Win and Losses
        WL = team.WL.value_counts().reset_index()
        W = WL[WL.WL == 'W']['count'].values[0]
        L = WL[WL.WL == 'L']['count'].values[0]
        ### Get classic stats
        target_stats.append({'team_abbreviation':team.TEAM_ABBREVIATION.unique()[0],
                            'team_name':team.TEAM_NAME.unique()[0],
                            'game_date':team.GAME_DATE.to_list(),
                            'W':W,
                            'L':L,
                            'offensive_rating':[], 
                            'defensive_rating':[],
                            'possessions':[] 
                            })
        
        ### Get advanced stats
        for id in team.GAME_ID.to_list():
            stats = boxscoreadvancedv3.BoxScoreAdvancedV3(game_id=id) 
            ### If the team is an away team during the game, you take the stats in the awayTeam key
            if team[team.GAME_ID == id].MATCHUP.values[0][4] == "@":  ### Away Team
                target_stats[-1]['offensive_rating'].append(stats.get_dict()['boxScoreAdvanced']['awayTeam']['statistics']['offensiveRating'])
                target_stats[-1]['defensive_rating'].append(stats.get_dict()['boxScoreAdvanced']['awayTeam']['statistics']['defensiveRating'])
                target_stats[-1]['possessions'].append(stats.get_dict()['boxScoreAdvanced']['awayTeam']['statistics']['possessions'])
            else:
                target_stats[-1]['offensive_rating'].append(stats.get_dict()['boxScoreAdvanced']['homeTeam']['statistics']['offensiveRating'])
                target_stats[-1]['defensive_rating'].append(stats.get_dict()['boxScoreAdvanced']['homeTeam']['statistics']['defensiveRating'])
                target_stats[-1]['possessions'].append(stats.get_dict()['boxScoreAdvanced']['homeTeam']['statistics']['possessions'])

    ### Compute metrics
    data = pd.DataFrame(target_stats)
    data['GP'] = data.W + data.L
    data['PCT_W'] = (data.W / data.GP)*100
    data['PCT_W_rank'] = data.PCT_W.rank(method='min', ascending=False).astype('int64')

    ### Save current date data
    data.to_csv("nba_adv_stats_"+current_date+".csv", index=False)
    print("Statistics of",current_date, "saved.")

"""
Plotly Dashboard Configuration
"""
### Data preparation for the dashboard
df = data
df.offensive_rating = df.offensive_rating.apply(np.array)
df.defensive_rating = df.defensive_rating.apply(np.array)

df.offensive_rating = df.offensive_rating.apply(np.mean).round(1)
df.defensive_rating = df.defensive_rating.apply(np.mean).round(1)

df['net_rating'] = df.offensive_rating - df.defensive_rating
df.net_rating = df.net_rating.round(1)
df['label'] = df.PCT_W_rank.astype('str') + '-' + df.team_abbreviation.astype('str')
df.sort_values(by='PCT_W_rank', inplace=True)

### Team colors for scatter markers
colors = pd.DataFrame({
    'team_abbreviation':['BOS', 'MIN', 'MIL', 'PHI', 'DEN', 'OKC', 'SAC', 'ORL', 'DAL',
       'LAC', 'MIA', 'NYK', 'CLE', 'NOP', 'HOU', 'LAL', 'GSW', 'IND',
       'PHX', 'BKN', 'CHI', 'ATL', 'UTA', 'TOR', 'MEM', 'CHA', 'POR',
       'WAS', 'SAS', 'DET'],
    'team_color':['#008248','#236192','#00471b','#006bb6','#0d2240','#007ac1','#5b2b82','#0b77bd','#007dc5',
                  '#1d428a','#98002e','#f58426','#6f2633','#b4975a','#ce1141','#552583','#fdb927','#002d62',
                  '#b95915','Black','#ce1141','#e03a3e','#2b5134','#a0a0a3','#5d76a9','#00788c','#cf0a2c',
                  '#002b5c','Black','#1d428a'
                  ]
})

df = df.merge(colors, on='team_abbreviation', how='left')

### Plotly Configuration

### Scatter plot
scatter = go.Scatter(
    x=df['offensive_rating'],
    y=df['defensive_rating'],
    name='team',
    mode='markers+text',
    marker=dict(color=df['team_color'], size=7),
    #marker_symbol='diamond-wide',
    text=df['label'],
    textfont={'color':df['team_color'], 'size':7},
    textposition='top center',
    texttemplate='<b>[%{text}]</b>',
    hovertemplate = '%{text} <br>off_rtg: %{x} </br> def_rtg: %{y}'
)

### Table plot
table = go.Table(
    header=dict(values=list(['Team','rank','GP','W','L','off_r','def_r','net_r']),
                fill_color='lightblue',
                align='left'),
    cells=dict(values=[df['team_abbreviation'],
                       df['PCT_W_rank'],
                       df['GP'],
                       df['W'],
                       df['L'],
                       df['offensive_rating'],
                       df['defensive_rating'],
                       df['net_rating']
                       ],
               fill_color='snow',
               align='center'),
    domain=dict(x=[0.6, 1],
                y=[0, 1])
)

### Merge plots
layout = dict(xaxis1=dict( dict(domain=[0, 0.58], anchor='y1')),
              yaxis1=dict( dict(domain=[0, 1], anchor='x1')),
              margin=dict(l=50, r=30, t=45, b=50)
             )
fig = go.Figure(data = [scatter,table], layout = layout)

### Configuration
fig.add_shape(type="line",
    x0=105, y0=105, x1=125, y1=125,
    line=dict(color="RoyalBlue",width=1)
)
fig['layout']['yaxis']['autorange'] = 'reversed'
fig.update_layout(xaxis_title='Offensive rating', 
                  yaxis_title='Defensive rating',
                  plot_bgcolor='whitesmoke',
                  font_family='Roboto',
                  font=dict(
                    size=11,
                    color='#044575'
                  )
                  )

"""
Route to main page that display our dashboard
"""
@app.route('/')
def index():
    graphJSON = json.dumps(fig, cls=PlotlyJSONEncoder)

    # Render the index.html template, passing the chart data
    return render_template('index.html', graphJSON=graphJSON)

if __name__ == '__main__':
    app.run(debug=False)